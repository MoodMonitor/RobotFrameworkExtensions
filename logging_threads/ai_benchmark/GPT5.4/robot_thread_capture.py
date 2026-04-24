from __future__ import annotations

import threading
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from robot.api.deco import keyword, library
from robot.output import librarylogger
from robot.output.logger import Logger as RobotLogger
from robot.output.loggerhelper import AbstractLogger, Message as LogMessage
from robot.output.stdoutlogsplitter import StdoutLogSplitter
from robot.result import (
    Break as ResultBreak,
    Continue as ResultContinue,
    Error as ResultError,
    For as ResultFor,
    ForIteration as ResultForIteration,
    Group as ResultGroup,
    If as ResultIf,
    IfBranch as ResultIfBranch,
    Keyword as ResultKeyword,
    Message as ResultMessage,
    Return as ResultReturn,
    Try as ResultTry,
    TryBranch as ResultTryBranch,
    Var as ResultVar,
    While as ResultWhile,
    WhileIteration as ResultWhileIteration,
)
from robot.running import model as running_model
from robot.running.context import EXECUTION_CONTEXTS, ExecutionContexts, _ExecutionContext
from robot.utils import safe_str


def _now() -> datetime:
    return datetime.now()


def _status_of(item: Any) -> str | None:
    return getattr(item, "status", None)


def _iter_failed_messages(body: Any):
    for item in body:
        status = _status_of(item)
        if status == "FAIL":
            yield getattr(item, "message", "") or ""
        child_body = getattr(item, "body", None)
        if child_body:
            yield from _iter_failed_messages(child_body)


class ThreadBufferedOutput(AbstractLogger):
    def __init__(self, parent_output: Any, root_group: ResultGroup):
        self._parent_output = parent_output
        self._parents = [root_group]
        self.library_listeners = getattr(parent_output, "library_listeners", None)

    @property
    def initial_log_level(self):
        return self._parent_output.initial_log_level

    def trace(self, msg, write_if_flat=True):
        self.write(msg, "TRACE")

    @property
    @contextmanager
    def delayed_logging(self):
        yield

    @property
    @contextmanager
    def delayed_logging_paused(self):
        yield

    def __getattr__(self, name: str):
        return getattr(self._parent_output, name)

    def _current_parent(self):
        return self._parents[-1]

    def _append_message(self, msg: LogMessage):
        parent = self._current_parent()
        parent.body.append(msg)

    def message(self, msg: LogMessage):
        self._append_message(msg)

    def log_message(self, msg: LogMessage):
        if self._parent_output.output_file.is_logged(msg):
            self._append_message(msg)

    def log_output(self, output: str):
        for msg in StdoutLogSplitter(output):
            self.log_message(msg)


def _make_start_method(name: str):
    def method(self, *args):
        self._parents.append(args[-1])

    method.__name__ = name
    return method


def _make_end_method(name: str):
    def method(self, *args):
        self._parents.pop()

    method.__name__ = name
    return method


for _name in (
    "start_keyword",
    "start_user_keyword",
    "start_library_keyword",
    "start_invalid_keyword",
    "start_for",
    "start_for_iteration",
    "start_while",
    "start_while_iteration",
    "start_group",
    "start_if",
    "start_if_branch",
    "start_try",
    "start_try_branch",
    "start_var",
    "start_break",
    "start_continue",
    "start_return",
    "start_error",
):
    setattr(ThreadBufferedOutput, _name, _make_start_method(_name))

for _name in (
    "end_keyword",
    "end_user_keyword",
    "end_library_keyword",
    "end_invalid_keyword",
    "end_for",
    "end_for_iteration",
    "end_while",
    "end_while_iteration",
    "end_group",
    "end_if",
    "end_if_branch",
    "end_try",
    "end_try_branch",
    "end_var",
    "end_break",
    "end_continue",
    "end_return",
    "end_error",
):
    setattr(ThreadBufferedOutput, _name, _make_end_method(_name))


@dataclass
class ThreadSession:
    thread: threading.Thread
    owner_test: Any
    root_data: Any
    root_result: ResultGroup
    output: ThreadBufferedOutput
    context: _ExecutionContext
    started_at: datetime | None = None
    ended_at: datetime | None = None
    attached: bool = False
    completed: bool = False
    exception: BaseException | None = None

    def start(self):
        self.started_at = _now()
        self.root_result.start_time = self.started_at

    def finish(self):
        self.completed = True
        self.ended_at = _now()
        self.root_result.end_time = self.ended_at
        self.root_result.elapsed_time = self.ended_at - (self.started_at or self.ended_at)
        self._finalize_status()

    def _finalize_status(self):
        if self.exception is not None:
            self.root_result.status = self.root_result.FAIL
            self.root_result.message = str(self.exception)
            return
        failed_messages = [msg for msg in _iter_failed_messages(self.root_result.body) if msg]
        if failed_messages:
            self.root_result.status = self.root_result.FAIL
            self.root_result.message = failed_messages[0]
        else:
            self.root_result.status = self.root_result.PASS
            self.root_result.message = ""

class RobotThreadCaptureManager:
    _instance: "RobotThreadCaptureManager | None" = None

    def __init__(self):
        self._patch_lock = threading.RLock()
        self._session_local = threading.local()
        self._enabled = False
        self._sessions: list[ThreadSession] = []
        self._session_by_thread: dict[threading.Thread, ThreadSession] = {}
        self._current_test = None
        self._patches_installed = False
        self._orig_thread_start: Callable[..., Any] | None = None
        self._orig_thread_join: Callable[..., Any] | None = None
        self._orig_librarylogger_write: Callable[..., Any] | None = None
        self._orig_logger_log_message: Callable[..., Any] | None = None
        self._orig_logger_message: Callable[..., Any] | None = None
        self._orig_logger_log_output: Callable[..., Any] | None = None
        self._orig_output_close: Callable[..., Any] | None = None
        self._orig_current_property = None
        self._orig_top_property = None

    @classmethod
    def instance(cls) -> "RobotThreadCaptureManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _current_session(self) -> ThreadSession | None:
        return getattr(self._session_local, "session", None)

    def _current_context(self):
        session = self._current_session()
        if session is not None:
            return session.context
        return self._orig_current_property.fget(EXECUTION_CONTEXTS)

    def _top_context(self):
        session = self._current_session()
        if session is not None:
            return session.context
        return self._orig_top_property.fget(EXECUTION_CONTEXTS)

    def enable(self):
        with self._patch_lock:
            self._install_patches()
            self._enabled = True
            self._current_test = self._current_context().test if self._current_context() else None

    def disable(self):
        self._enabled = False
        self._current_test = None

    def end_test(self, result):
        self._flush_completed(owner_test=result)
        self._warn_on_alive_threads(owner_test=result)
        self.disable()

    def end_suite(self, result):
        self._flush_completed(owner_test=None)
        self._warn_on_alive_threads(owner_test=None)

    def _warn_on_alive_threads(self, owner_test):
        sessions = self._matching_sessions(owner_test)
        alive = [session.thread.name for session in sessions if session.thread.is_alive()]
        if alive:
            current_context = self._current_context()
            parent, _ = self._get_parent_items(current_context) if current_context else (None, None)
            if parent:
                parent.body.create_message(
                    message=(
                        "Thread capture finished before these threads stopped: "
                        + ", ".join(alive)
                    ),
                    level="WARN",
                    timestamp=_now(),
                )

    def _matching_sessions(self, owner_test):
        if owner_test is None:
            return list(self._sessions)
        return [session for session in self._sessions if session.owner_test is owner_test]

    def _flush_completed(self, owner_test):
        for session in self._matching_sessions(owner_test):
            if session.completed:
                self._flush_session(session, self._current_context())

    def _install_patches(self):
        if self._patches_installed:
            return
        self._orig_thread_start = threading.Thread.start
        self._orig_thread_join = threading.Thread.join
        self._orig_librarylogger_write = librarylogger.write
        self._orig_logger_log_message = RobotLogger.log_message
        self._orig_logger_message = RobotLogger.message
        self._orig_logger_log_output = RobotLogger.log_output

        from robot.output.output import Output

        self._orig_output_close = Output.close
        self._orig_current_property = ExecutionContexts.current
        self._orig_top_property = ExecutionContexts.top

        manager = self

        def patched_start(thread: threading.Thread, *args, **kwargs):
            manager._prepare_thread(thread)
            return manager._orig_thread_start(thread, *args, **kwargs)

        def patched_join(thread: threading.Thread, *args, **kwargs):
            result = manager._orig_thread_join(thread, *args, **kwargs)
            session = manager._session_by_thread.get(thread)
            if session and not thread.is_alive() and session.completed:
                manager._flush_session(session, manager._current_context())
            return result

        def patched_write(msg, level="INFO", html=False, console=None):
            session = manager._current_session()
            if session is None:
                return manager._orig_librarylogger_write(msg, level, html, console)
            if not isinstance(msg, str):
                msg = safe_str(msg)
            if level == "FAIL":
                raise ValueError(f"Invalid log level '{level}'.")
            session.output.log_message(LogMessage(msg, level, html=html, console=console))

        def patched_log_message(logger, msg):
            session = manager._current_session()
            if session is None:
                return manager._orig_logger_log_message(logger, msg)
            session.output.log_message(msg)

        def patched_message(logger, msg):
            session = manager._current_session()
            if session is None:
                return manager._orig_logger_message(logger, msg)
            session.output.message(msg)

        def patched_log_output(logger, output):
            session = manager._current_session()
            if session is None:
                return manager._orig_logger_log_output(logger, output)
            session.output.log_output(output)

        def patched_output_close(output, result):
            try:
                manager._flush_completed(owner_test=None)
                return manager._orig_output_close(output, result)
            finally:
                manager._restore_patches()

        def current_property(instance):
            return manager._current_context()

        def top_property(instance):
            return manager._top_context()

        threading.Thread.start = patched_start
        threading.Thread.join = patched_join
        librarylogger.write = patched_write
        RobotLogger.log_message = patched_log_message
        RobotLogger.message = patched_message
        RobotLogger.log_output = patched_log_output
        Output.close = patched_output_close
        ExecutionContexts.current = property(current_property)
        ExecutionContexts.top = property(top_property)
        self._patches_installed = True

    def _restore_patches(self):
        if not self._patches_installed:
            return
        from robot.output.output import Output

        threading.Thread.start = self._orig_thread_start
        threading.Thread.join = self._orig_thread_join
        librarylogger.write = self._orig_librarylogger_write
        RobotLogger.log_message = self._orig_logger_log_message
        RobotLogger.message = self._orig_logger_message
        RobotLogger.log_output = self._orig_logger_log_output
        Output.close = self._orig_output_close
        ExecutionContexts.current = self._orig_current_property
        ExecutionContexts.top = self._orig_top_property
        self._enabled = False
        self._current_test = None
        self._sessions.clear()
        self._session_by_thread.clear()
        self._session_local = threading.local()
        self._patches_installed = False

    def _prepare_thread(self, thread: threading.Thread):
        if not self._enabled or thread in self._session_by_thread:
            return
        parent_context = self._current_context()
        if parent_context is None:
            return
        _, parent_data = self._get_parent_items(parent_context)
        root_data = running_model.Group(name=f"Thread {thread.name}", parent=parent_data)
        root_result = ResultGroup(name=f"Thread {thread.name}")
        output = ThreadBufferedOutput(parent_context.output, root_result)
        context = _ExecutionContext(
            parent_context.suite,
            parent_context.namespace,
            output,
            parent_context.dry_run,
            parent_context.asynchronous,
        )
        context.test = parent_context.test
        context.in_suite_teardown = parent_context.in_suite_teardown
        context.in_test_teardown = parent_context.in_test_teardown
        context.steps = [(root_data, root_result, None)]
        session = ThreadSession(
            thread=thread,
            owner_test=parent_context.test,
            root_data=root_data,
            root_result=root_result,
            output=output,
            context=context,
        )
        original_run = thread.run

        def run_with_capture():
            self._session_local.session = session
            session.start()
            try:
                return original_run()
            except Exception as err:
                session.exception = err
                session.output.log_message(
                    LogMessage(
                        f"Unhandled exception in thread '{thread.name}': {safe_str(err)}",
                        level="ERROR",
                        timestamp=_now(),
                    )
                )
                session.output.log_message(
                    LogMessage(
                        "".join(traceback.format_exception(type(err), err, err.__traceback__)),
                        level="DEBUG",
                        timestamp=_now(),
                    )
                )
                return None
            finally:
                session.finish()
                self._session_local.session = None

        thread.run = run_with_capture
        self._session_by_thread[thread] = session
        self._sessions.append(session)

    def _get_parent_items(self, context):
        if context.steps:
            data, result, _ = context.steps[-1]
            return result, data
        if context.test:
            return context.test, None
        if not context.suite.has_tests:
            return context.suite.setup, None
        return context.suite.teardown, None

    def _flush_session(self, session: ThreadSession, current_context):
        if session.attached or current_context is None:
            return
        parent_result, _ = self._get_parent_items(current_context)
        if not parent_result or not hasattr(parent_result, "body"):
            return
        parent_result.body.append(session.root_result)
        self._write_body_item(current_context.output.output_file, session.root_result)
        session.attached = True

    def _write_body_item(self, output_file, item):
        if isinstance(item, ResultMessage):
            if item.level in ("WARN", "ERROR"):
                output_file.message(item)
            output_file.log_message(item)
            return
        if isinstance(item, ResultKeyword):
            output_file.start_keyword(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_keyword(None, item)
            return
        if isinstance(item, ResultFor):
            output_file.start_for(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_for(None, item)
            return
        if isinstance(item, ResultForIteration):
            output_file.start_for_iteration(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_for_iteration(None, item)
            return
        if isinstance(item, ResultWhile):
            output_file.start_while(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_while(None, item)
            return
        if isinstance(item, ResultWhileIteration):
            output_file.start_while_iteration(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_while_iteration(None, item)
            return
        if isinstance(item, ResultGroup):
            output_file.start_group(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_group(None, item)
            return
        if isinstance(item, ResultIf):
            output_file.start_if(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_if(None, item)
            return
        if isinstance(item, ResultIfBranch):
            output_file.start_if_branch(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_if_branch(None, item)
            return
        if isinstance(item, ResultTry):
            output_file.start_try(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_try(None, item)
            return
        if isinstance(item, ResultTryBranch):
            output_file.start_try_branch(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_try_branch(None, item)
            return
        if isinstance(item, ResultVar):
            output_file.start_var(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_var(None, item)
            return
        if isinstance(item, ResultReturn):
            output_file.start_return(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_return(None, item)
            return
        if isinstance(item, ResultContinue):
            output_file.start_continue(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_continue(None, item)
            return
        if isinstance(item, ResultBreak):
            output_file.start_break(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_break(None, item)
            return
        if isinstance(item, ResultError):
            output_file.start_error(None, item)
            for child in item.body:
                self._write_body_item(output_file, child)
            output_file.end_error(None, item)


@library(scope="GLOBAL", auto_keywords=False)
class RobotThreadCapture:
    ROBOT_LIBRARY_LISTENER = None
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self):
        self._manager = RobotThreadCaptureManager.instance()
        self.ROBOT_LIBRARY_LISTENER = self

    @keyword("Enable Thread Logging Capture")
    def enable_thread_logging_capture(self):
        self._manager.enable()

    @keyword("Disable Thread Logging Capture")
    def disable_thread_logging_capture(self):
        self._manager.disable()

    def end_test(self, data, result):
        self._manager.end_test(result)

    def end_suite(self, data, result):
        self._manager.end_suite(result)
