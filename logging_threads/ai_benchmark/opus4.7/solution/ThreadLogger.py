"""ThreadLogger - thread-safe logging for Robot Framework 7.4.

This library allows Python threads launched from a test library (via
``threading.Thread``) to emit log messages and structured execution events
that appear correctly in ``output.xml`` / ``log.html`` under their own
per-thread grouping.

Root cause of the out-of-the-box problem
----------------------------------------
``robot.output.librarylogger.write`` silently drops every message coming
from a thread whose name is not ``MainThread`` or
``RobotFrameworkTimeoutThread`` (see ``LOGGING_THREADS``). In addition,
the global ``Logger`` singleton and its streaming ``XmlLogger`` (which
writes ``output.xml`` live) are not thread-safe: simultaneous
``start_keyword`` / ``log_message`` calls from several threads corrupt
the XML tree.

Solution (outline)
------------------
* A runtime patch (installed only while threads are active and fully
  removed afterwards) makes ``librarylogger.write`` **thread-aware**.
* Per-thread events are captured into an isolated tree of
  ``robot.result`` model objects (Keyword / Message / For / If / Try ...)
  with their original timestamps.
* When the main test thread joins its workers, each thread's tree is
  attached, as a single ``Keyword`` subtree named ``Thread 'xxx'``, to
  whatever body item is currently active on the main thread. All
  original structure (FOR / IF / TRY) is preserved.
* User code running inside a thread does NOT need to change - the
  regular ``from robot.api import logger; logger.info(...)`` API just
  works. Library keywords can additionally use the context managers and
  ``run_keyword`` helper exposed on this module to produce structured
  nested events.

Constraints honoured
--------------------
* Only Robot Framework public / internal API is used - no third-party
  dependencies.
* The framework's internals are restored to their original state when
  the last worker thread joins (:class:`_Patcher.deactivate`).
* Nested structures emitted inside a thread keep their native tags
  (``<kw>``, ``<for>``, ``<iter>``, ``<if>``, ``<branch>``, ``<try>``)
  in ``output.xml``.
* Works safely with arbitrary numbers of parallel threads.
"""

from __future__ import annotations

import threading
import traceback
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Optional

from robot.api import logger as rf_logger
from robot.libraries.BuiltIn import BuiltIn
from robot.output import librarylogger as _librarylogger
from robot.output.logger import LOGGER as _LOGGER
from robot.output.loggerhelper import Message as _LogMessage
from robot.result import (
    Break as _BreakResult,
    Continue as _ContinueResult,
    Error as _ErrorResult,
    For as _ForResult,
    ForIteration as _ForIterationResult,
    Group as _GroupResult,
    If as _IfResult,
    IfBranch as _IfBranchResult,
    Keyword as _KeywordResult,
    Return as _ReturnResult,
    Try as _TryResult,
    TryBranch as _TryBranchResult,
    Var as _VarResult,
    While as _WhileResult,
    WhileIteration as _WhileIterationResult,
)
from robot.running.context import EXECUTION_CONTEXTS

__all__ = [
    "ThreadLogger",
    "thread_group",
    "thread_for",
    "thread_if",
    "thread_try",
    "run_keyword",
]


# ---------------------------------------------------------------------------
# Per-thread state
# ---------------------------------------------------------------------------


class _ThreadRecord:
    """Isolated log tree collected by a single worker thread.

    Every worker thread has its own ``_ThreadRecord`` holding a root
    ``Keyword`` result item whose body is populated by the thread. The
    ``parents`` stack mirrors Robot Framework's ``_log_message_parents``
    but is completely private to the thread, so no race conditions occur
    on the shared global one.
    """

    __slots__ = ("name", "root", "parents", "error", "start_time", "end_time")

    def __init__(self, name: str) -> None:
        self.name = name
        self.root = _KeywordResult(
            name=f"Thread '{name}'",
            owner="ThreadLogger",
            type="KEYWORD",
            status="PASS",
            start_time=datetime.now(),
        )
        self.parents: list[Any] = [self.root]
        self.error: Optional[BaseException] = None
        self.start_time: datetime = self.root.start_time
        self.end_time: Optional[datetime] = None

    def append_message(self, msg: _LogMessage) -> None:
        self.parents[-1].body.append(msg)

    def push(self, item: Any) -> None:
        self.parents[-1].body.append(item)
        self.parents.append(item)

    def pop(self) -> None:
        self.parents.pop()

    def finalize(self, error: Optional[BaseException]) -> None:
        self.error = error
        self.end_time = datetime.now()
        self.root.end_time = self.end_time
        if error is not None:
            self.root.status = "FAIL"
            self.root.message = f"{type(error).__name__}: {error}"
            # Attach traceback as a final DEBUG message for analysis.
            tb_text = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ).strip()
            # Attach at INFO level so the traceback appears at the
            # default RF log level.
            tb_msg = _LogMessage(
                message=tb_text,
                level="INFO",
                html=False,
                timestamp=self.end_time,
            )
            self.root.body.append(tb_msg)
        else:
            self.root.status = "PASS"


# ---------------------------------------------------------------------------
# Thread registry and runtime patch
# ---------------------------------------------------------------------------


class _Registry:
    """Tracks all tracked threads and their per-thread records.

    Keys are the OS thread identifier (``threading.get_ident()``). Those
    identifiers are only assigned once the thread is actually running,
    so workers publish themselves on entry instead of being pre-registered
    by the parent. A preliminary registration (before start) would not
    work because ``Thread.ident`` is ``None`` until the worker is
    started.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[int, _ThreadRecord] = {}
        self._threads: dict[int, threading.Thread] = {}
        self._order: list[int] = []
        # Threads that have been started but have not yet registered
        # themselves. Used so that activate/deactivate accounting stays
        # correct even if a thread dies very early.
        self._pending: list[tuple[threading.Thread, _ThreadRecord]] = []

    def declare(self, thread: threading.Thread, record: _ThreadRecord) -> None:
        """Announce a thread before it starts running."""
        with self._lock:
            self._pending.append((thread, record))

    def attach_current(self, record: _ThreadRecord) -> None:
        """Called from within the worker thread, on entry."""
        tid = threading.get_ident()
        with self._lock:
            thread = threading.current_thread()
            self._records[tid] = record
            self._threads[tid] = thread
            self._order.append(tid)
            self._pending = [(t, r) for (t, r) in self._pending if r is not record]

    def record_for_current(self) -> Optional[_ThreadRecord]:
        tid = threading.get_ident()
        return self._records.get(tid)

    def has_records(self) -> bool:
        with self._lock:
            return bool(self._records) or bool(self._pending)

    def drain(self) -> list[tuple[threading.Thread, _ThreadRecord]]:
        with self._lock:
            out = [
                (self._threads[tid], self._records[tid])
                for tid in self._order
                if tid in self._records
            ]
            self._records.clear()
            self._threads.clear()
            self._order.clear()
            self._pending.clear()
            return out


_REGISTRY = _Registry()


class _Patcher:
    """Installs and removes the runtime patches.

    The patches are active only while at least one worker thread is
    alive. They are fully reversible.
    """

    def __init__(self) -> None:
        self._active = 0
        self._lock = threading.RLock()
        self._orig_write: Optional[Callable[..., None]] = None

    def activate(self) -> None:
        with self._lock:
            self._active += 1
            if self._active > 1:
                return
            # Patch 1 - thread-aware librarylogger.write
            self._orig_write = _librarylogger.write
            _librarylogger.write = self._thread_aware_write

    def deactivate(self) -> None:
        with self._lock:
            self._active -= 1
            if self._active > 0:
                return
            assert self._orig_write is not None
            _librarylogger.write = self._orig_write
            self._orig_write = None

    # -----------------------------------------------------------------
    # Patched librarylogger.write
    # -----------------------------------------------------------------

    def _thread_aware_write(
        self,
        msg: object,
        level: str = "INFO",
        html: bool = False,
        console: Optional[bool] = None,
    ) -> None:
        """Route logs to either the per-thread record or the original
        implementation depending on the current thread.
        """
        record = _REGISTRY.record_for_current()
        if record is None:
            # Main thread or an untracked thread - preserve original behaviour.
            assert self._orig_write is not None
            self._orig_write(msg, level, html, console)
            return
        if not isinstance(msg, str):
            from robot.utils import safe_str

            msg = safe_str(msg)
        if level == "FAIL":
            raise ValueError(f"Invalid log level '{level}'.")
        record.append_message(
            _LogMessage(message=msg, level=level, html=html, console=console)
        )


_PATCHER = _Patcher()


# ---------------------------------------------------------------------------
# Result-tree replay
# ---------------------------------------------------------------------------


def _dispatch_methods(item):
    """Return the ``(start, end)`` methods on the global LOGGER that
    match ``item``'s result-model type."""
    if isinstance(item, _IfBranchResult):
        return _LOGGER.start_if_branch, _LOGGER.end_if_branch
    if isinstance(item, _IfResult):
        return _LOGGER.start_if, _LOGGER.end_if
    if isinstance(item, _TryBranchResult):
        return _LOGGER.start_try_branch, _LOGGER.end_try_branch
    if isinstance(item, _TryResult):
        return _LOGGER.start_try, _LOGGER.end_try
    if isinstance(item, _ForIterationResult):
        return _LOGGER.start_for_iteration, _LOGGER.end_for_iteration
    if isinstance(item, _ForResult):
        return _LOGGER.start_for, _LOGGER.end_for
    if isinstance(item, _WhileIterationResult):
        return _LOGGER.start_while_iteration, _LOGGER.end_while_iteration
    if isinstance(item, _WhileResult):
        return _LOGGER.start_while, _LOGGER.end_while
    if isinstance(item, _GroupResult):
        return _LOGGER.start_group, _LOGGER.end_group
    if isinstance(item, _VarResult):
        return _LOGGER.start_var, _LOGGER.end_var
    if isinstance(item, _BreakResult):
        return _LOGGER.start_break, _LOGGER.end_break
    if isinstance(item, _ContinueResult):
        return _LOGGER.start_continue, _LOGGER.end_continue
    if isinstance(item, _ReturnResult):
        return _LOGGER.start_return, _LOGGER.end_return
    if isinstance(item, _ErrorResult):
        return _LOGGER.start_error, _LOGGER.end_error
    if isinstance(item, _KeywordResult):
        return _LOGGER.start_keyword, _LOGGER.end_keyword
    raise TypeError(f"Unsupported result type: {type(item).__name__}")


def _replay_tree(item) -> None:
    """Replay a result-model tree through the global LOGGER.

    Structural items (Keyword/For/If/Try/...) are dispatched through
    ``LOGGER.start_*`` / ``LOGGER.end_*`` so every registered listener and
    the streaming output file see them in the correct order.  Message
    items are dispatched directly to every output logger to avoid
    ``Logger.log_message``'s side effect of re-appending them to the
    current parent's ``body`` (they already live inside the tree).
    """
    if isinstance(item, _LogMessage):
        for logger in _LOGGER:
            try:
                logger.log_message(item)
            except Exception:
                # A misbehaving listener must not corrupt the replay.
                pass
        return
    start, end = _dispatch_methods(item)
    start(None, item)
    try:
        for child in item.body:
            _replay_tree(child)
    finally:
        end(None, item)


# ---------------------------------------------------------------------------
# Structural helpers available inside a worker thread
# ---------------------------------------------------------------------------


def _require_record() -> _ThreadRecord:
    record = _REGISTRY.record_for_current()
    if record is None:
        raise RuntimeError(
            "ThreadLogger structural helpers may only be called from a "
            "worker thread started via ThreadLogger.Start Thread."
        )
    return record


@contextmanager
def thread_group(name: str):
    """Group nested events under an explicit ``<group>`` element."""
    record = _require_record()
    item = _GroupResult(name=name, status="PASS", start_time=datetime.now())
    record.push(item)
    try:
        yield item
    except BaseException as err:
        item.status = "FAIL"
        item.message = f"{type(err).__name__}: {err}"
        item.end_time = datetime.now()
        raise
    else:
        item.end_time = datetime.now()
    finally:
        record.pop()


@contextmanager
def thread_for(flavor: str = "IN", assign=(), values=()):
    """Create a native ``<for>`` block inside a thread's log tree.

    Example::

        with thread_for(assign=("${item}",), values=("a", "b")) as for_:
            for val in ("a", "b"):
                with for_.iteration(item=val):
                    rf_logger.info(f"processing {val}")
    """
    record = _require_record()
    for_item = _ForResult(
        assign=tuple(assign),
        flavor=flavor,
        values=tuple(values),
        status="PASS",
        start_time=datetime.now(),
    )
    record.push(for_item)

    class _ForHandle:
        @contextmanager
        def iteration(self, **assigned):
            iter_item = _ForIterationResult(
                assign=dict(assigned) if assigned else {},
                status="PASS",
                start_time=datetime.now(),
            )
            record.push(iter_item)
            try:
                yield iter_item
            except BaseException as err:
                iter_item.status = "FAIL"
                iter_item.message = f"{type(err).__name__}: {err}"
                iter_item.end_time = datetime.now()
                raise
            else:
                iter_item.end_time = datetime.now()
            finally:
                record.pop()

    try:
        yield _ForHandle()
    except BaseException as err:
        for_item.status = "FAIL"
        for_item.message = f"{type(err).__name__}: {err}"
        for_item.end_time = datetime.now()
        raise
    else:
        for_item.end_time = datetime.now()
    finally:
        record.pop()


@contextmanager
def thread_if(condition: str = ""):
    """Create a native ``<if>`` block with a single IF branch.

    Example::

        with thread_if("${flag}") as branch:
            rf_logger.info("inside IF branch")
    """
    record = _require_record()
    if_root = _IfResult(status="PASS", start_time=datetime.now())
    record.push(if_root)
    branch = _IfBranchResult(
        type=_IfBranchResult.IF,
        condition=condition,
        status="PASS",
        start_time=datetime.now(),
    )
    record.push(branch)
    try:
        yield branch
    except BaseException as err:
        branch.status = "FAIL"
        branch.message = f"{type(err).__name__}: {err}"
        branch.end_time = datetime.now()
        if_root.status = "FAIL"
        if_root.message = branch.message
        if_root.end_time = datetime.now()
        raise
    else:
        branch.end_time = datetime.now()
        if_root.end_time = datetime.now()
    finally:
        record.pop()  # branch
        record.pop()  # if_root


@contextmanager
def thread_try(patterns=()):
    """Create a native ``<try>`` block mirroring Robot Framework's
    TRY / EXCEPT semantics.

    Usage::

        with thread_try(patterns=("ValueError*",)) as handle:
            with handle.try_block():
                raise ValueError("boom")      # captured, not re-raised
            if handle.caught:
                with handle.except_block():
                    rf_logger.warn("recovered")

    ``try_block`` captures the exception (like RF's TRY branch does),
    records it on the branch as ``status=FAIL`` and exposes it via
    ``handle.caught`` so the user can decide whether to run the
    ``except_block``.
    """
    record = _require_record()
    try_root = _TryResult(status="PASS", start_time=datetime.now())
    record.push(try_root)

    class _TryHandle:
        caught: Optional[BaseException] = None

        @contextmanager
        def try_block(self):
            branch = _TryBranchResult(
                type=_TryBranchResult.TRY, status="PASS", start_time=datetime.now()
            )
            record.push(branch)
            try:
                yield branch
            except BaseException as err:  # noqa: BLE001 - mirrors TRY/EXCEPT
                self.caught = err
                branch.status = "FAIL"
                branch.message = f"{type(err).__name__}: {err}"
            finally:
                branch.end_time = datetime.now()
                record.pop()

        @contextmanager
        def except_block(self):
            branch = _TryBranchResult(
                type=_TryBranchResult.EXCEPT,
                patterns=tuple(patterns),
                pattern_type="GLOB" if patterns else None,
                status="PASS",
                start_time=datetime.now(),
            )
            record.push(branch)
            try:
                yield branch
            except BaseException as err:
                branch.status = "FAIL"
                branch.message = f"{type(err).__name__}: {err}"
                branch.end_time = datetime.now()
                raise
            else:
                branch.end_time = datetime.now()
                # If the except block ran without raising it handled
                # the exception caught by try_block, so the whole TRY
                # stays PASS.
                self.caught = None
            finally:
                record.pop()

    handle = _TryHandle()
    try:
        yield handle
    except BaseException as err:
        try_root.status = "FAIL"
        try_root.message = f"{type(err).__name__}: {err}"
        try_root.end_time = datetime.now()
        raise
    else:
        if handle.caught is not None:
            # The caller never ran except_block - surface the failure so
            # test logs faithfully show the unhandled error.
            try_root.status = "FAIL"
            try_root.message = (
                f"Unhandled in TRY: {type(handle.caught).__name__}: {handle.caught}"
            )
        try_root.end_time = datetime.now()
    finally:
        record.pop()


def run_keyword(name: str, *args: Any) -> Any:
    """Execute a Robot Framework keyword from inside a worker thread.

    The call is NOT dispatched through the main Runner (which is not
    thread-safe and would corrupt the streaming ``output.xml``).  Instead
    we look up the keyword's implementation via the suite's namespace,
    invoke its Python callable directly, and record the execution as a
    proper ``<kw>`` element inside the thread's log tree. Messages logged
    by the keyword (via ``robot.api.logger``) end up *inside* that
    ``<kw>`` element thanks to the thread-aware ``librarylogger`` patch
    and the parent stack of the thread's record.
    """
    record = _require_record()
    context = EXECUTION_CONTEXTS.current
    if context is None:
        raise RuntimeError("Cannot resolve keyword - no active Robot Framework context.")
    runner = context.get_runner(name)
    impl = runner.keyword
    owner = getattr(impl, "owner", None) or getattr(impl, "libname", None)
    owner_name = getattr(owner, "name", None) if owner is not None else None
    kw_item = _KeywordResult(
        name=getattr(impl, "name", name),
        owner=owner_name or "",
        args=[str(a) for a in args],
        type="KEYWORD",
        status="PASS",
        start_time=datetime.now(),
    )
    record.push(kw_item)
    try:
        # Log arguments similar to RF's normal keyword tracing.
        rf_logger.trace(
            "Arguments: [ " + " | ".join(repr(a) for a in args) + " ]"
        )
        # Invoke the underlying Python method directly.
        method = getattr(impl, "method", None) or getattr(impl, "current_handler", None)
        if method is None:
            raise RuntimeError(
                f"Keyword '{name}' cannot be executed from a thread "
                "(not a plain library keyword)."
            )
        result = method(*args)
    except BaseException as err:
        kw_item.status = "FAIL"
        kw_item.message = f"{type(err).__name__}: {err}"
        kw_item.end_time = datetime.now()
        raise
    else:
        kw_item.end_time = datetime.now()
        return result
    finally:
        record.pop()


# ---------------------------------------------------------------------------
# Robot Framework library API
# ---------------------------------------------------------------------------


class ThreadLogger:
    """Robot Framework library exposing thread-safe logging helpers."""

    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    ROBOT_LIBRARY_VERSION = "1.0.0"
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self) -> None:
        self._threads: list[threading.Thread] = []
        self._records: list[_ThreadRecord] = []
        # Register as listener so that Stop All Threads can run on teardown.
        self.ROBOT_LIBRARY_LISTENER = self

    # ---------- Robot Framework listener hooks ----------
    def end_test(self, data, result):  # noqa: D401 - RF listener API
        """Safety net: never leave patches installed after a test."""
        if self._threads:
            try:
                self.wait_all_threads()
            except Exception:
                # Even if joining fails, we must restore patches.
                pass
        # Extra defence: if our patch somehow leaked, forcibly restore.
        if _PATCHER._active > 0 and not _REGISTRY.has_records():
            while _PATCHER._active > 0:
                _PATCHER.deactivate()

    # ---------- Keywords ----------

    def start_thread(
        self, name: str, kind: str, target: str, *args: Any
    ) -> None:
        """Start a worker thread.

        Arguments:
            ``name``    - unique label of the thread; used as a Thread.name and
                          as the title of the ``<kw>`` wrapping its log tree.
            ``kind``    - either ``KEYWORD`` (``target`` names a Robot
                          Framework keyword to execute in the thread) or
                          ``PYTHON`` (``target`` names a dotted path to a
                          Python callable).
            ``target``  - the keyword name or the dotted Python callable.
            ``args``    - arguments passed to the callable / keyword.
        """
        kind = kind.upper()
        if kind not in ("KEYWORD", "PYTHON"):
            raise ValueError(
                f"Unknown thread kind '{kind}'. Expected 'KEYWORD' or 'PYTHON'."
            )

        record = _ThreadRecord(name)

        def _runner() -> None:
            _REGISTRY.attach_current(record)
            try:
                if kind == "KEYWORD":
                    run_keyword(target, *args)
                else:
                    callable_ = _resolve_callable(target)
                    callable_(*args)
            except BaseException as err:  # noqa: BLE001 - intentional
                record.finalize(err)
            else:
                record.finalize(None)

        thread = threading.Thread(target=_runner, name=name, daemon=True)

        _PATCHER.activate()
        _REGISTRY.declare(thread, record)
        self._records.append(record)
        self._threads.append(thread)
        thread.start()

    def wait_all_threads(self, timeout: Optional[float] = None) -> None:
        """Join every worker thread started by :meth:`start_thread` and
        merge their log trees into the currently active test/keyword log.

        All patches are reverted once the last worker has joined.
        """
        timeout_f = float(timeout) if timeout is not None else None
        for thread in self._threads:
            thread.join(timeout=timeout_f)
        # Drain records in registration order to keep report stable.
        finished = _REGISTRY.drain()

        # Attach every thread's result tree to the current parent AND
        # replay the tree through the global LOGGER so the streaming
        # output (output.xml) and every registered listener observe the
        # thread events in the correct nesting order.
        parent = self._current_main_parent()
        for _thread, record in finished:
            if parent is not None:
                parent.body.append(record.root)
            _replay_tree(record.root)

        # Deactivate the patch layer once for every thread we started.
        for _ in self._threads:
            _PATCHER.deactivate()

        errored = [r for r in self._records if r.error is not None]

        # Reset state (keep library reusable across multiple tests).
        self._threads.clear()
        self._records.clear()

        if errored:
            first = errored[0]
            msg = (
                f"{len(errored)} worker thread(s) ended with an error. "
                f"First failure in thread '{first.name}': "
                f"{type(first.error).__name__}: {first.error}"
            )
            raise AssertionError(msg)

    def active_thread_count(self) -> int:
        """Return the number of threads started but not yet joined."""
        return sum(1 for t in self._threads if t.is_alive())

    # ---------- Internals ----------

    @staticmethod
    def _current_main_parent():
        """Return the body item currently active on the MAIN thread."""
        stack = _LOGGER._log_message_parents
        if not stack:
            # Fall back to the running test result, if any.
            ctx = EXECUTION_CONTEXTS.current
            if ctx is not None and ctx.test is not None:
                return ctx.test
            return None
        return stack[-1]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _resolve_callable(dotted: str) -> Callable[..., Any]:
    """Import and return a callable from a ``module.path:attr`` or
    ``module.path.attr`` reference."""
    if ":" in dotted:
        module_name, attr = dotted.rsplit(":", 1)
    else:
        module_name, _, attr = dotted.rpartition(".")
    if not module_name or not attr:
        raise ValueError(
            f"Invalid callable reference '{dotted}'. "
            "Use 'package.module:callable' or 'package.module.callable'."
        )
    import importlib

    module = importlib.import_module(module_name)
    target = getattr(module, attr)
    if not callable(target):
        raise TypeError(f"'{dotted}' is not callable.")
    return target
