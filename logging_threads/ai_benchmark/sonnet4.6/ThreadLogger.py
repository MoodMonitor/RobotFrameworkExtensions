"""
ThreadLogger – Robot Framework library for proper parallel thread logging.

Solves two scenarios:
  1. Simple logging from threads: robot.api.logger calls inside threads are
     captured per-thread and injected into the result tree after join.
  2. Keyword execution in threads: RF keywords run inside threads produce
     properly nested result structures (FOR/IF/TRY preserved) per thread.

Mechanism: three temporary monkey-patches on RF globals + LOGGING_THREADS,
all unconditionally restored in a finally block.

No external packages. RF 7.4+ internal API only.
"""

import threading
import traceback
from datetime import datetime
from types import SimpleNamespace

from robot.errors import ExecutionFailed
from robot.output import librarylogger
from robot.output.logger import LOGGER
from robot.result import Keyword as ResultKeyword
from robot.running.context import EXECUTION_CONTEXTS
from robot.running.model import Keyword as RunningKeyword


# ---------------------------------------------------------------------------
# _ThreadLocalList
# ---------------------------------------------------------------------------

class _ThreadLocalList:
    """Thread-local proxy for a shared list attribute on an RF singleton.

    The main thread continues to use the original list unchanged.
    Each background thread gets its own isolated list, pre-populated via
    register_thread() called from inside the thread once its ident is known.
    """

    def __init__(self, main_list):
        self._stacks = {}          # {thread_ident: list}
        self._lock = threading.RLock()
        self._main = main_list
        self._main_id = threading.main_thread().ident

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current(self):
        tid = threading.current_thread().ident
        if tid == self._main_id:
            return self._main
        with self._lock:
            stack = self._stacks.get(tid)
        if stack is None:
            # Fallback: thread not pre-registered – use main list (safe read)
            return self._main
        return stack

    def register_thread(self, thread_id, initial=None):
        with self._lock:
            self._stacks[thread_id] = list(initial or [])

    def unregister_thread(self, thread_id):
        with self._lock:
            self._stacks.pop(thread_id, None)

    # ------------------------------------------------------------------
    # List interface
    # ------------------------------------------------------------------

    def append(self, item):
        self._current().append(item)

    def pop(self):
        return self._current().pop()

    def remove(self, item):
        self._current().remove(item)

    def extend(self, items):
        self._current().extend(items)

    def __getitem__(self, idx):
        return self._current()[idx]

    def __setitem__(self, idx, val):
        self._current()[idx] = val

    def __bool__(self):
        return bool(self._current())

    def __len__(self):
        return len(self._current())

    def __iter__(self):
        # Snapshot to avoid modification-during-iteration in caller
        return iter(list(self._current()))

    def __contains__(self, item):
        return item in self._current()

    def __reversed__(self):
        return reversed(list(self._current()))


# ---------------------------------------------------------------------------
# _SuppressingOutputProxy
# ---------------------------------------------------------------------------

class _SuppressingOutputProxy:
    """Proxy for LOGGER._output_file.

    Background threads: all write methods (start_*, end_*, log_message,
    message) are silently dropped to prevent concurrent XML writes.
    Main thread calls (unlikely during parallel wait, but possible from
    listeners): serialised through a lock and forwarded to the real output.

    Keyed by thread NAME (known before thread.start(), avoids the window
    between thread.start() and tid assignment).
    """

    def __init__(self, real_output, bg_thread_names):
        self._real = real_output
        self._bg_names = bg_thread_names   # set of str
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_bg(self):
        return threading.current_thread().name in self._bg_names

    def _fwd(self, method_name, *args, **kwargs):
        if not self._is_bg():
            with self._lock:
                getattr(self._real, method_name)(*args, **kwargs)

    # ------------------------------------------------------------------
    # Delegated properties (always return from real; no serialisation needed
    # for reads, and the values are immutable or lazily evaluated)
    # ------------------------------------------------------------------

    @property
    def is_logged(self):
        return self._real.is_logged

    @property
    def real_logger(self):
        return self._real.real_logger

    @property
    def logger(self):
        return self._real.logger

    @property
    def errors(self):
        return self._real.errors

    @property
    def delayed_logging(self):
        return self._real.delayed_logging

    @property
    def delayed_logging_paused(self):
        return self._real.delayed_logging_paused

    # ------------------------------------------------------------------
    # Write methods – suppressed for bg threads
    # ------------------------------------------------------------------

    def start_keyword(self, d, r):            self._fwd('start_keyword', d, r)
    def end_keyword(self, d, r):              self._fwd('end_keyword', d, r)
    def start_library_keyword(self, d, i, r): self._fwd('start_library_keyword', d, i, r)
    def end_library_keyword(self, d, i, r):   self._fwd('end_library_keyword', d, i, r)
    def start_user_keyword(self, d, i, r):    self._fwd('start_user_keyword', d, i, r)
    def end_user_keyword(self, d, i, r):      self._fwd('end_user_keyword', d, i, r)
    def start_invalid_keyword(self, d, i, r): self._fwd('start_invalid_keyword', d, i, r)
    def end_invalid_keyword(self, d, i, r):   self._fwd('end_invalid_keyword', d, i, r)
    def start_for(self, d, r):                self._fwd('start_for', d, r)
    def end_for(self, d, r):                  self._fwd('end_for', d, r)
    def start_for_iteration(self, d, r):      self._fwd('start_for_iteration', d, r)
    def end_for_iteration(self, d, r):        self._fwd('end_for_iteration', d, r)
    def start_while(self, d, r):              self._fwd('start_while', d, r)
    def end_while(self, d, r):                self._fwd('end_while', d, r)
    def start_while_iteration(self, d, r):    self._fwd('start_while_iteration', d, r)
    def end_while_iteration(self, d, r):      self._fwd('end_while_iteration', d, r)
    def start_if(self, d, r):                 self._fwd('start_if', d, r)
    def end_if(self, d, r):                   self._fwd('end_if', d, r)
    def start_if_branch(self, d, r):          self._fwd('start_if_branch', d, r)
    def end_if_branch(self, d, r):            self._fwd('end_if_branch', d, r)
    def start_try(self, d, r):                self._fwd('start_try', d, r)
    def end_try(self, d, r):                  self._fwd('end_try', d, r)
    def start_try_branch(self, d, r):         self._fwd('start_try_branch', d, r)
    def end_try_branch(self, d, r):           self._fwd('end_try_branch', d, r)
    def start_group(self, d, r):              self._fwd('start_group', d, r)
    def end_group(self, d, r):                self._fwd('end_group', d, r)
    def start_var(self, d, r):                self._fwd('start_var', d, r)
    def end_var(self, d, r):                  self._fwd('end_var', d, r)
    def start_break(self, d, r):              self._fwd('start_break', d, r)
    def end_break(self, d, r):                self._fwd('end_break', d, r)
    def start_continue(self, d, r):           self._fwd('start_continue', d, r)
    def end_continue(self, d, r):             self._fwd('end_continue', d, r)
    def start_return(self, d, r):             self._fwd('start_return', d, r)
    def end_return(self, d, r):               self._fwd('end_return', d, r)
    def start_error(self, d, r):              self._fwd('start_error', d, r)
    def end_error(self, d, r):                self._fwd('end_error', d, r)
    def start_test(self, d, r):               self._fwd('start_test', d, r)
    def end_test(self, d, r):                 self._fwd('end_test', d, r)
    def start_suite(self, d, r):              self._fwd('start_suite', d, r)
    def end_suite(self, d, r):                self._fwd('end_suite', d, r)

    def log_message(self, msg, no_delay=False):
        self._fwd('log_message', msg, no_delay)

    def message(self, msg):
        self._fwd('message', msg)

    def close(self):
        with self._lock:
            self._real.close()

    def statistics(self, stats):
        with self._lock:
            self._real.statistics(stats)


# ---------------------------------------------------------------------------
# ThreadLogger library
# ---------------------------------------------------------------------------

class ThreadLogger:
    """Robot Framework library for proper parallel thread logging.

    Usage
    -----
    Run Keywords In Parallel
        Each positional argument must be a list whose first element is the
        RF keyword name and the remaining elements are its arguments::

            @{t1}=    Create List    My Keyword    arg1    arg2
            @{t2}=    Create List    My Keyword    arg3    arg4
            Run Keywords In Parallel    ${t1}    ${t2}

    Run Functions In Parallel
        Each positional argument must be a list whose first element is a
        Python callable and the remaining elements are its arguments::

            ${f1}=    Evaluate    lambda: my_module.work("a")
            Run Functions In Parallel    ${f1}

        If an argument is just a callable (not a list), it is called with
        no arguments.
    """

    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    # ------------------------------------------------------------------
    # Public keywords
    # ------------------------------------------------------------------

    def run_keywords_in_parallel(self, *keyword_lists):
        """Run RF keywords in parallel threads, one thread per argument.

        Each argument must be a list: ``[keyword_name, arg1, arg2, ...]``.
        Threads run simultaneously; results are injected in call order after
        all threads complete.  A thread failure raises ``ExecutionFailed``
        after all threads have joined (other threads always finish first).
        """
        if not keyword_lists:
            return
        configs = []
        for item in keyword_lists:
            if isinstance(item, (list, tuple)) and item:
                configs.append({"name": str(item[0]), "args": tuple(item[1:])})
            else:
                raise ValueError(
                    f"Each argument to Run Keywords In Parallel must be a "
                    f"non-empty list [keyword_name, arg…], got: {item!r}"
                )
        self._run_parallel(configs, is_keyword=True)

    def run_functions_in_parallel(self, *function_specs):
        """Run Python callables in parallel threads, one thread per argument.

        Each argument is either:
        - a callable (called with no args), or
        - a list ``[callable, arg1, arg2, …]``.

        The callable body may freely use ``robot.api.logger`` – messages are
        captured and attached to the thread's result node.
        """
        if not function_specs:
            return
        configs = []
        for item in function_specs:
            if callable(item):
                configs.append({"func": item, "args": ()})
            elif isinstance(item, (list, tuple)) and item and callable(item[0]):
                configs.append({"func": item[0], "args": tuple(item[1:])})
            else:
                raise ValueError(
                    f"Each argument to Run Functions In Parallel must be a "
                    f"callable or [callable, arg…], got: {item!r}"
                )
        self._run_parallel(configs, is_keyword=False)

    # ------------------------------------------------------------------
    # Core parallel runner
    # ------------------------------------------------------------------

    def _run_parallel(self, configs, is_keyword):
        context = EXECUTION_CONTEXTS.current
        if context is None:
            raise RuntimeError(
                "ThreadLogger: no active Robot Framework execution context."
            )

        # Capture the result node that should parent our thread wrappers.
        # _log_message_parents[-1] is the currently-running keyword or test.
        if LOGGER._log_message_parents:
            parent_result = LOGGER._log_message_parents[-1]
        elif context.test:
            parent_result = context.test
        else:
            raise RuntimeError(
                "ThreadLogger: cannot determine parent result node."
            )

        # ---------------------------------------------------------------
        # Create one ResultKeyword wrapper per thread (before threads start)
        # ---------------------------------------------------------------
        wrappers = []
        thread_names = []
        for i, cfg in enumerate(configs):
            label = cfg.get("name") or getattr(cfg.get("func"), "__name__", f"func-{i+1}")
            tname = f"RF-Thread-{i + 1}"
            wrapper = ResultKeyword(
                name=f"[Thread {i + 1}] {label}",
                owner="ThreadLogger",
            )
            wrapper.start_time = datetime.now()
            wrapper.status = "NOT SET"
            wrappers.append(wrapper)
            thread_names.append(tname)

        # ---------------------------------------------------------------
        # Save originals
        # ---------------------------------------------------------------
        orig_log_parents   = LOGGER._log_message_parents
        orig_output        = LOGGER._output_file
        orig_steps         = context.steps
        orig_user_keywords = context.user_keywords
        orig_logging_threads = list(librarylogger.LOGGING_THREADS)

        # ---------------------------------------------------------------
        # Install thread-local proxies
        # ---------------------------------------------------------------
        tl_parents       = _ThreadLocalList(orig_log_parents)
        tl_steps         = _ThreadLocalList(orig_steps)
        tl_user_keywords = _ThreadLocalList(orig_user_keywords)
        bg_names         = set(thread_names)
        proxy_output     = _SuppressingOutputProxy(orig_output, bg_names)

        LOGGER._log_message_parents = tl_parents
        LOGGER._output_file         = proxy_output
        context.steps               = tl_steps
        context.user_keywords       = tl_user_keywords
        librarylogger.LOGGING_THREADS = list(orig_logging_threads) + thread_names

        # ---------------------------------------------------------------
        # Thread worker
        # ---------------------------------------------------------------
        thread_errors = [None] * len(configs)

        def run_thread(idx, cfg, wrapper):
            tid = threading.current_thread().ident
            fake_data = SimpleNamespace(lineno=None, name=wrapper.name)

            # Pre-populate this thread's local stacks so that:
            #   - log messages land in wrapper.body (Scenario 1)
            #   - BuiltIn.run_keyword finds wrapper as the current result
            #     parent and creates sub-keyword results inside it (Scenario 2)
            tl_parents.register_thread(tid, [wrapper])
            tl_steps.register_thread(tid, [(fake_data, wrapper, None)])
            tl_user_keywords.register_thread(tid, [])

            try:
                if is_keyword:
                    kw = RunningKeyword(cfg["name"], args=cfg["args"])
                    kw.run(wrapper, context)
                else:
                    cfg["func"](*cfg["args"])
            except ExecutionFailed as exc:
                wrapper.status = "FAIL"
                wrapper.message = str(exc)
                thread_errors[idx] = exc
            except Exception as exc:
                wrapper.status = "FAIL"
                wrapper.message = str(exc)
                # Log traceback into the wrapper body for visibility
                from robot.output.loggerhelper import Message as LogMsg
                tb_text = traceback.format_exc()
                wrapper.body.append(
                    LogMsg(tb_text, "DEBUG", timestamp=datetime.now())
                )
                thread_errors[idx] = exc
            else:
                if wrapper.status == "NOT SET":
                    wrapper.status = "PASS"
            finally:
                if wrapper.start_time is not None:
                    wrapper.elapsed_time = datetime.now() - wrapper.start_time

        # ---------------------------------------------------------------
        # Start threads
        # ---------------------------------------------------------------
        threads = [
            threading.Thread(
                target=run_thread,
                args=(i, cfg, wrappers[i]),
                name=thread_names[i],
                daemon=False,
            )
            for i, cfg in enumerate(configs)
        ]

        try:
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            # ---------------------------------------------------------------
            # Unconditionally restore original state
            # ---------------------------------------------------------------
            LOGGER._log_message_parents   = orig_log_parents
            LOGGER._output_file           = orig_output
            context.steps                 = orig_steps
            context.user_keywords         = orig_user_keywords
            librarylogger.LOGGING_THREADS = orig_logging_threads

        # ---------------------------------------------------------------
        # Inject thread results into the main result tree (main thread)
        # ---------------------------------------------------------------
        for wrapper in wrappers:
            # Finalise timing if not already set by thread
            if wrapper.start_time is not None and wrapper.elapsed_time.total_seconds() == 0:
                wrapper.elapsed_time = datetime.now() - wrapper.start_time

            # 1. Attach to in-memory result model so log.html picks it up
            parent_result.body.append(wrapper)

            # 2. Write to output.xml via XmlLogger ResultVisitor
            #    loggerhelper.Message IS a result.Message subclass, so
            #    wrapper.visit() handles messages, keywords, FOR/IF/TRY
            #    nodes all correctly through the visitor pattern.
            if orig_output is not None and orig_output.real_logger is not None:
                wrapper.visit(orig_output.real_logger)

        # ---------------------------------------------------------------
        # Raise if any thread failed
        # ---------------------------------------------------------------
        failures = [
            (i + 1, err)
            for i, err in enumerate(thread_errors)
            if err is not None
        ]
        if failures:
            msgs = "; ".join(
                f"Thread {n}: {err}" for n, err in failures
            )
            raise ExecutionFailed(
                f"Parallel execution failed in {len(failures)} thread(s): {msgs}"
            )
