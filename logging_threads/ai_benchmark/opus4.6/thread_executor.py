"""Thread-safe keyword and logging execution for Robot Framework.

Provides a Robot Framework library that allows running Python callables
in parallel threads while correctly capturing all logs, keyword executions,
and nested control structures (FOR, IF, TRY-EXCEPT) into output.xml / log.html.

Architecture:
    - Each worker thread gets an isolated execution context with its own
      output capture (ThreadOutput) so logs never interleave.
    - Monkey-patches are applied ONLY during threaded execution and fully
      reverted afterward (reversibility guarantee).
    - After threads complete, captured result trees are replayed through
      the real XmlLogger via the visitor pattern, preserving native XML tags
      for all control structures.

Usage from Robot:
    *** Settings ***
    Library    thread_executor.py

    *** Test Cases ***
    Example
        ${threads}=    Create Dictionary
        ...    worker1=some_module.my_func
        ...    worker2=some_module.other_func
        Run In Threads    &{threads}
"""

import threading
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from robot.api.deco import keyword
from robot.output import LOGGER
from robot.output.loggerapi import LoggerApi
from robot.output.loggerhelper import AbstractLogger, Message
from robot.output import librarylogger
from robot.running.context import EXECUTION_CONTEXTS, _ExecutionContext, Asynchronous
from robot.running.model import Keyword as KeywordData
from robot.result import model as result_model


# ---------------------------------------------------------------------------
# ThreadOutput — per-thread output replacement that captures events into
#                an in-memory result model tree.
# ---------------------------------------------------------------------------

class ThreadOutput(AbstractLogger, LoggerApi):
    """Per-thread output that captures all execution events into a result tree.

    Replaces the real ``Output`` for worker threads so that every log message
    and keyword start/end is recorded in a thread-local ``Keyword`` result
    node without touching the shared LOGGER or XmlLogger.
    """

    def __init__(self, thread_name: str):
        self.thread_name = thread_name
        self.root = result_model.Keyword(
            name=f'Thread: {thread_name}',
            owner='ThreadExecutor',
            type='KEYWORD',
            status='PASS',
            start_time=datetime.now(),
        )
        self._message_parents: list = [self.root]
        self._current_parent = self.root

    # ---- helpers ----------------------------------------------------------

    @property
    def _parent(self):
        return self._message_parents[-1] if self._message_parents else self.root

    def _push(self, result):
        self._message_parents.append(result)

    def _pop(self):
        if len(self._message_parents) > 1:
            self._message_parents.pop()

    # ---- AbstractLogger interface (trace/debug/info/warn/error/fail) ------

    def message(self, msg):
        if isinstance(msg, Message):
            if not msg.timestamp:
                msg.timestamp = datetime.now()
            # Resolve callable messages before storing
            msg.resolve_delayed_message()
            if msg.message is None:
                return  # Listener removed this message
            self._parent.body.append(
                result_model.Message(
                    message=str(msg.message),
                    level=msg.level,
                    html=msg.html,
                    timestamp=msg.timestamp,
                )
            )
        else:
            self._parent.body.append(
                result_model.Message(
                    message=str(msg),
                    level='INFO',
                    timestamp=datetime.now(),
                )
            )

    def write(self, message, level, html=False):
        self.message(Message(message, level, html))

    # ---- LoggerApi start/end pairs ----------------------------------------
    # Each start_* pushes the result onto the message parents stack,
    # each end_* pops it.  This mirrors what LOGGER does with
    # _log_message_parents.

    def start_suite(self, data, result):
        self._push(result)

    def end_suite(self, data, result):
        self._pop()

    def start_test(self, data, result):
        self._push(result)

    def end_test(self, data, result):
        self._pop()

    # -- keywords -----------------------------------------------------------

    def start_keyword(self, data, result):
        self._push(result)

    def end_keyword(self, data, result):
        self._pop()

    def start_user_keyword(self, data, implementation, result):
        self._push(result)

    def end_user_keyword(self, data, implementation, result):
        self._pop()

    def start_library_keyword(self, data, implementation, result):
        self._push(result)

    def end_library_keyword(self, data, implementation, result):
        self._pop()

    def start_invalid_keyword(self, data, implementation, result):
        self._push(result)

    def end_invalid_keyword(self, data, implementation, result):
        self._pop()

    # -- control structures -------------------------------------------------

    def start_for(self, data, result):
        self._push(result)

    def end_for(self, data, result):
        self._pop()

    def start_for_iteration(self, data, result):
        self._push(result)

    def end_for_iteration(self, data, result):
        self._pop()

    def start_while(self, data, result):
        self._push(result)

    def end_while(self, data, result):
        self._pop()

    def start_while_iteration(self, data, result):
        self._push(result)

    def end_while_iteration(self, data, result):
        self._pop()

    def start_if(self, data, result):
        self._push(result)

    def end_if(self, data, result):
        self._pop()

    def start_if_branch(self, data, result):
        self._push(result)

    def end_if_branch(self, data, result):
        self._pop()

    def start_try(self, data, result):
        self._push(result)

    def end_try(self, data, result):
        self._pop()

    def start_try_branch(self, data, result):
        self._push(result)

    def end_try_branch(self, data, result):
        self._pop()

    def start_group(self, data, result):
        self._push(result)

    def end_group(self, data, result):
        self._pop()

    def start_var(self, data, result):
        self._push(result)

    def end_var(self, data, result):
        self._pop()

    def start_break(self, data, result):
        self._push(result)

    def end_break(self, data, result):
        self._pop()

    def start_continue(self, data, result):
        self._push(result)

    def end_continue(self, data, result):
        self._pop()

    def start_return(self, data, result):
        self._push(result)

    def end_return(self, data, result):
        self._pop()

    def start_error(self, data, result):
        self._push(result)

    def end_error(self, data, result):
        self._pop()

    # -- message routing ----------------------------------------------------

    def log_message(self, msg):
        self.message(msg)

    # -- required by Output interface (no-op for threads) -------------------

    @property
    @contextmanager
    def delayed_logging(self):
        yield

    @property
    @contextmanager
    def delayed_logging_paused(self):
        yield

    def set_log_level(self, level):
        return 'INFO'

    def register_error_listener(self, listener):
        pass

    def close(self, result=None):
        pass

    def library_import(self, library, importer):
        pass

    def resource_import(self, resource, importer):
        pass

    def variables_import(self, variables, importer):
        pass

    def trace(self, msg, write_if_flat=True):
        # msg can be a callable (lazy evaluation) — pass it to Message
        # which will resolve it via resolve_delayed_message()
        self.write(msg, 'TRACE')

    def debug(self, msg):
        self.write(msg, 'DEBUG')

    def info(self, msg):
        self.write(msg, 'INFO')

    def warn(self, msg):
        self.write(msg, 'WARN')

    def fail(self, msg):
        self.write(str(msg), 'FAIL')

    def skip(self, msg):
        self.write(str(msg), 'SKIP')

    def finalize(self):
        self.root.elapsed_time = datetime.now() - self.root.start_time


# ---------------------------------------------------------------------------
# PatchManager — installs/uninstalls monkey-patches on RF internals.
# ---------------------------------------------------------------------------

_thread_local = threading.local()


class PatchManager:
    """Temporarily patches RF internals to support threaded execution.

    Patches are active ONLY while worker threads run and are fully reverted
    afterward.
    """

    def __init__(self):
        self._originals: Dict[str, Any] = {}
        self._installed = False

    def install(self, thread_contexts: Dict[int, '_ExecutionContext']):
        """Install thread-aware patches.

        ``thread_contexts`` maps ``threading.get_ident()`` → context.
        """
        if self._installed:
            return
        self._thread_contexts = thread_contexts

        # 1. Save originals
        self._originals['librarylogger_write'] = librarylogger.write
        self._originals['LOGGER_log_message'] = LOGGER.log_message
        # Save the property object from the class
        self._originals['EC_current_property'] = type(EXECUTION_CONTEXTS).__dict__['current']

        # 2. Create patched versions
        original_write = librarylogger.write
        original_log_message = LOGGER.log_message
        thread_ctxs = self._thread_contexts

        def patched_write(msg, level='INFO', html=False, console=None):
            tid = threading.get_ident()
            if tid in thread_ctxs:
                ctx = thread_ctxs[tid]
                if not isinstance(msg, str):
                    from robot.utils import safe_str
                    msg = safe_str(msg)
                if level == 'FAIL':
                    raise ValueError(f"Invalid log level '{level}'.")
                m = Message(msg, level, html=html, console=console)
                ctx.output.message(m)
            else:
                original_write(msg, level, html, console)

        def patched_log_message(msg):
            tid = threading.get_ident()
            if tid in thread_ctxs:
                ctx = thread_ctxs[tid]
                ctx.output.message(msg)
            else:
                original_log_message(msg)

        def patched_current_getter(self_ec):
            tid = threading.get_ident()
            if tid in thread_ctxs:
                return thread_ctxs[tid]
            # Fall back to original behavior
            return self_ec._contexts[-1] if self_ec._contexts else None

        # 3. Apply patches
        librarylogger.write = patched_write
        LOGGER.log_message = patched_log_message
        type(EXECUTION_CONTEXTS).current = property(patched_current_getter)

        self._installed = True

    def uninstall(self):
        """Revert all patches to original state."""
        if not self._installed:
            return

        librarylogger.write = self._originals['librarylogger_write']
        LOGGER.log_message = self._originals['LOGGER_log_message']
        type(EXECUTION_CONTEXTS).current = self._originals['EC_current_property']

        self._thread_contexts = {}
        self._originals.clear()
        self._installed = False


# ---------------------------------------------------------------------------
# Thread worker wrapper
# ---------------------------------------------------------------------------

class _ThreadResult:
    """Holds the outcome of a single worker thread."""
    __slots__ = ('thread_name', 'output', 'error', 'traceback_str')

    def __init__(self, thread_name: str):
        self.thread_name = thread_name
        self.output: Optional[ThreadOutput] = None
        self.error: Optional[BaseException] = None
        self.traceback_str: Optional[str] = None


def _thread_worker(
    func: Callable,
    args: tuple,
    kwargs: dict,
    thread_result: _ThreadResult,
    thread_output: ThreadOutput,
    context: _ExecutionContext,
    ready_event: threading.Event,
):
    """Wrapper executed inside each worker thread."""
    # Push synthetic step so that BuiltIn.run_keyword() can find a parent
    # result for creating child keyword results.  This makes keywords
    # executed via BuiltIn().run_keyword("Name", ...) appear as nested
    # <kw> elements in the thread's result tree.
    fake_data = KeywordData(name=f'Thread: {thread_result.thread_name}')
    context.steps.append((fake_data, thread_output.root, None))
    try:
        ready_event.wait()  # wait until all threads + patches are ready
        func(*args, **kwargs)
    except Exception as exc:
        thread_result.error = exc
        thread_result.traceback_str = traceback.format_exc()
        thread_output.root.status = 'FAIL'
        thread_output.root.message = str(exc)
        thread_output.message(
            Message(
                f'Thread {thread_result.thread_name} failed:\n'
                f'{thread_result.traceback_str}',
                'ERROR',
            )
        )
    finally:
        context.steps.pop()
        thread_output.finalize()
        thread_result.output = thread_output


# ---------------------------------------------------------------------------
# Result merger — replays thread results into XmlLogger & main result model
# ---------------------------------------------------------------------------

def _merge_thread_results(
    thread_results: List[_ThreadResult],
    main_result_parent,
    xml_logger,
):
    """Replay each thread's captured result tree through XmlLogger
    and append to the main result model body.
    """
    for tr in thread_results:
        if tr.output is None:
            continue
        root = tr.output.root
        # Append the thread's root keyword to the main result model body
        # so it appears in the correct location in the result tree
        main_result_parent.body.append(root)
        # Write to XmlLogger via visitor pattern — this writes complete
        # nested XML with native tags for all control structures
        root.visit(xml_logger)


# ---------------------------------------------------------------------------
# ThreadExecutor — Robot Framework library
# ---------------------------------------------------------------------------

class thread_executor:
    """Robot Framework library for running callables in parallel threads
    with full logging and keyword execution support.

    All logs from threads are captured per-thread and merged into the
    output.xml / log.html after threads complete. Control structures
    (FOR, IF, TRY-EXCEPT) executed in threads preserve their native
    XML representation.

    Example usage::

        *** Settings ***
        Library    thread_executor.py

        *** Test Cases ***
        Run Functions In Parallel
            &{threads}=    Create Dictionary    w1=mylib.func1    w2=mylib.func2
            Run In Threads    &{threads}
    """

    ROBOT_LIBRARY_SCOPE = 'GLOBAL'

    @keyword('Run In Threads')
    def run_in_threads(self, **thread_specs: Callable):
        """Run callables in parallel threads with isolated logging.

        Each keyword argument is ``thread_name=callable``.  The callable
        can be a Python function reference, an already-resolved callable,
        or a ``module.function`` string that will be imported.

        After all threads complete, their logs are merged into the current
        test's output.  If any thread raised an exception, the keyword fails
        with a summary of all errors.

        Example::

            Run In Threads    worker1=${func1}    worker2=${func2}
        """
        if not thread_specs:
            raise ValueError("At least one thread must be specified.")

        # Resolve callables
        resolved: Dict[str, Callable] = {}
        for name, func in thread_specs.items():
            if isinstance(func, str):
                func = self._import_callable(func)
            if not callable(func):
                raise TypeError(f"Thread '{name}': expected callable, got {type(func).__name__}")
            resolved[name] = func

        # Get references to main context internals
        main_ctx = EXECUTION_CONTEXTS.current
        if main_ctx is None:
            raise RuntimeError("ThreadExecutor must be used during Robot Framework execution.")
        namespace = main_ctx.namespace
        suite = main_ctx.suite
        test = main_ctx.test

        # Get the main result parent (current keyword/test body target)
        main_result_parent = LOGGER._log_message_parents[-1] if LOGGER._log_message_parents else None
        if main_result_parent is None:
            raise RuntimeError("Cannot determine current result parent for log merging.")

        # Get XmlLogger for replay
        xml_logger = None
        if LOGGER._output_file and hasattr(LOGGER._output_file, 'real_logger'):
            xml_logger = LOGGER._output_file.real_logger

        # Prepare per-thread contexts and outputs
        thread_contexts: Dict[int, _ExecutionContext] = {}
        thread_objects: List[Tuple[threading.Thread, _ThreadResult, ThreadOutput, _ExecutionContext]] = []
        ready_event = threading.Event()

        for thread_name, func in resolved.items():
            t_output = ThreadOutput(thread_name)
            t_ctx = _ExecutionContext(
                suite=suite,
                namespace=namespace,
                output=t_output,
                dry_run=main_ctx.dry_run,
                asynchronous=Asynchronous(),
            )
            # Copy test reference so BuiltIn._context.test is available
            t_ctx.test = test
            t_result = _ThreadResult(thread_name)
            t = threading.Thread(
                target=_thread_worker,
                args=(func, (), {}, t_result, t_output, t_ctx, ready_event),
                name=f'RF-Thread-{thread_name}',
                daemon=True,
            )
            thread_objects.append((t, t_result, t_output, t_ctx))

        # Start all threads first (they block on ready_event)
        for t, _, _, _ in thread_objects:
            t.start()

        # Register thread idents now that threads have started
        # Small sleep to ensure threads are alive and have idents
        import time
        time.sleep(0.01)
        for t, _, _, t_ctx in thread_objects:
            thread_contexts[t.ident] = t_ctx

        # Install patches and release threads
        patch_mgr = PatchManager()
        patch_mgr.install(thread_contexts)

        try:
            ready_event.set()  # unblock all worker threads

            # Wait for all threads to complete
            for t, _, _, _ in thread_objects:
                t.join()
        finally:
            # ALWAYS uninstall patches — reversibility guarantee
            patch_mgr.uninstall()

        # Collect results
        results = [tr for _, tr, _, _ in thread_objects]

        # Merge into output
        if xml_logger is not None:
            _merge_thread_results(results, main_result_parent, xml_logger)
        else:
            # No XML logger — just append to result model
            for tr in results:
                if tr.output:
                    main_result_parent.body.append(tr.output.root)

        # Check for errors
        errors = [(tr.thread_name, tr.error, tr.traceback_str)
                   for tr in results if tr.error is not None]
        if errors:
            msg_parts = [f"Thread '{name}' failed: {err}" for name, err, _ in errors]
            raise AssertionError(
                f"{len(errors)} thread(s) failed:\n" + "\n".join(msg_parts)
            )

    @keyword('Run In Threads With Args')
    def run_in_threads_with_args(self, *thread_defs):
        """Run callables with arguments in parallel threads.

        Each argument is a list/tuple of ``[thread_name, callable, *args]``.

        Example::

            @{t1}=    Create List    worker1    ${func1}    arg1    arg2
            @{t2}=    Create List    worker2    ${func2}    arg3
            Run In Threads With Args    ${t1}    ${t2}
        """
        if not thread_defs:
            raise ValueError("At least one thread definition must be specified.")

        main_ctx = EXECUTION_CONTEXTS.current
        if main_ctx is None:
            raise RuntimeError("ThreadExecutor must be used during Robot Framework execution.")
        namespace = main_ctx.namespace
        suite = main_ctx.suite
        test = main_ctx.test

        main_result_parent = LOGGER._log_message_parents[-1] if LOGGER._log_message_parents else None
        if main_result_parent is None:
            raise RuntimeError("Cannot determine current result parent for log merging.")

        xml_logger = None
        if LOGGER._output_file and hasattr(LOGGER._output_file, 'real_logger'):
            xml_logger = LOGGER._output_file.real_logger

        thread_contexts: Dict[int, _ExecutionContext] = {}
        thread_objects = []
        ready_event = threading.Event()

        for thread_def in thread_defs:
            if not isinstance(thread_def, (list, tuple)) or len(thread_def) < 2:
                raise ValueError(
                    f"Each thread definition must be [name, callable, *args], got: {thread_def}"
                )
            thread_name = str(thread_def[0])
            func = thread_def[1]
            args = tuple(thread_def[2:]) if len(thread_def) > 2 else ()

            if isinstance(func, str):
                func = self._import_callable(func)
            if not callable(func):
                raise TypeError(f"Thread '{thread_name}': expected callable, got {type(func).__name__}")

            t_output = ThreadOutput(thread_name)
            t_ctx = _ExecutionContext(
                suite=suite,
                namespace=namespace,
                output=t_output,
                dry_run=main_ctx.dry_run,
                asynchronous=Asynchronous(),
            )
            t_ctx.test = test
            t_result = _ThreadResult(thread_name)
            t = threading.Thread(
                target=_thread_worker,
                args=(func, args, {}, t_result, t_output, t_ctx, ready_event),
                name=f'RF-Thread-{thread_name}',
                daemon=True,
            )
            thread_objects.append((t, t_result, t_output, t_ctx))

        for t, _, _, _ in thread_objects:
            t.start()

        import time
        time.sleep(0.01)
        for t, _, _, t_ctx in thread_objects:
            thread_contexts[t.ident] = t_ctx

        patch_mgr = PatchManager()
        patch_mgr.install(thread_contexts)

        try:
            ready_event.set()
            for t, _, _, _ in thread_objects:
                t.join()
        finally:
            patch_mgr.uninstall()

        results = [tr for _, tr, _, _ in thread_objects]

        if xml_logger is not None:
            _merge_thread_results(results, main_result_parent, xml_logger)
        else:
            for tr in results:
                if tr.output:
                    main_result_parent.body.append(tr.output.root)

        errors = [(tr.thread_name, tr.error, tr.traceback_str)
                   for tr in results if tr.error is not None]
        if errors:
            msg_parts = [f"Thread '{name}' failed: {err}" for name, err, _ in errors]
            raise AssertionError(
                f"{len(errors)} thread(s) failed:\n" + "\n".join(msg_parts)
            )

    @staticmethod
    def _import_callable(dotted_name: str) -> Callable:
        """Import a callable from a dotted module path like 'module.func'."""
        parts = dotted_name.rsplit('.', 1)
        if len(parts) != 2:
            raise ValueError(
                f"Cannot import '{dotted_name}': expected 'module.function' format."
            )
        module_name, func_name = parts
        import importlib
        module = importlib.import_module(module_name)
        func = getattr(module, func_name, None)
        if func is None:
            raise AttributeError(f"Module '{module_name}' has no attribute '{func_name}'")
        return func
