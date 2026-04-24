"""Test-only library that showcases the thread-logging problem.

The *baseline* keyword :func:`run_worker_baseline` reproduces the issue:
it spawns a :class:`threading.Thread` and calls
``robot.api.logger.info`` from within it.  Robot Framework silently
drops those messages because the thread name is not in
``robot.output.librarylogger.LOGGING_THREADS``.

The *fixed* keyword :func:`run_worker_with_threadlogger` uses the
``ThreadLogger`` library and the :func:`thread_for`, :func:`thread_if`
and :func:`thread_try` context managers to produce correct, grouped
per-thread output with full nested structure.
"""

from __future__ import annotations

import threading
import time

from robot.api import logger
from robot.api.deco import library, keyword

import sys
from pathlib import Path

# Allow importing ThreadLogger whether this file is run from the repo root
# or from a subdirectory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "solution"))

from ThreadLogger import (  # noqa: E402
    ThreadLogger,
    thread_for,
    thread_if,
    thread_try,
    thread_group,
)


@library(scope="GLOBAL")
class DemoLibrary:
    """Simulates a third-party library that internally uses threads."""

    def __init__(self) -> None:
        self._logger = ThreadLogger()

    # ------------------------------------------------------------------
    # 1) Baseline (buggy): plain threading.Thread + robot.api.logger
    # ------------------------------------------------------------------
    @keyword("Run Worker Baseline")
    def run_worker_baseline(self, count: int = 3) -> None:
        """Spawn ``count`` worker threads using the plain Python threading
        API.  Each worker logs using Robot Framework's public logger.

        On an unmodified Robot Framework runtime, most of those messages
        are NEVER written to ``output.xml`` because the threads are not
        the MainThread.
        """
        count = int(count)
        logger.info(f"MainThread: starting {count} baseline workers")

        def _worker(idx: int) -> None:
            for step in range(3):
                logger.info(f"[baseline worker {idx}] step {step}")
                time.sleep(0.01)

        threads = [
            threading.Thread(target=_worker, args=(i,), name=f"baseline-{i}")
            for i in range(count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        logger.info("MainThread: baseline workers finished")

    # ------------------------------------------------------------------
    # 2) Fixed: same scenario but using ThreadLogger helpers
    # ------------------------------------------------------------------
    @keyword("Run Workers With Thread Logger")
    def run_workers_with_thread_logger(self, count: int = 3) -> None:
        """Same scenario as above but every worker is started through
        :class:`ThreadLogger`.  All messages - with original timestamps -
        are grouped under a dedicated ``<kw>`` per thread.
        """
        count = int(count)
        logger.info(f"MainThread: starting {count} workers via ThreadLogger")
        for i in range(count):
            self._logger.start_thread(
                f"worker-{i}",
                "PYTHON",
                "tests.demo_library:_worker_simple",
                i,
            )
        self._logger.wait_all_threads()
        logger.info("MainThread: ThreadLogger workers finished")

    # ------------------------------------------------------------------
    # 3) Thread with nested structures (FOR, IF, TRY-EXCEPT)
    # ------------------------------------------------------------------
    @keyword("Run Worker With Nested Structures")
    def run_worker_with_nested_structures(self) -> None:
        logger.info("MainThread: launching worker with nested structures")
        self._logger.start_thread(
            "nested-1",
            "PYTHON",
            "tests.demo_library:_worker_nested",
        )
        self._logger.wait_all_threads()
        logger.info("MainThread: nested worker finished")

    # ------------------------------------------------------------------
    # 4) Thread running a Robot Framework keyword
    # ------------------------------------------------------------------
    @keyword("Run Keyword In Worker Thread")
    def run_keyword_in_worker_thread(self, keyword_name: str, *args: str) -> None:
        self._logger.start_thread(
            f"kw-runner-{keyword_name}",
            "KEYWORD",
            keyword_name,
            *args,
        )
        self._logger.wait_all_threads()

    # ------------------------------------------------------------------
    # 5) Stress test: N parallel workers producing many log messages
    # ------------------------------------------------------------------
    @keyword("Launch Many Parallel Workers")
    def launch_many_parallel_workers(self, count: int = 10, steps: int = 5) -> None:
        count = int(count)
        steps = int(steps)
        logger.info(f"MainThread: launching {count} parallel workers")
        for i in range(count):
            self._logger.start_thread(
                f"stress-{i}",
                "PYTHON",
                "tests.demo_library:_worker_stress",
                i,
                steps,
            )
        self._logger.wait_all_threads()
        logger.info(f"MainThread: {count} parallel workers joined")

    # ------------------------------------------------------------------
    # 6) Parallel mix with an intentional failure
    # ------------------------------------------------------------------
    @keyword("Run Parallel Workers With One Failing")
    def run_parallel_workers_with_one_failing(self) -> None:
        logger.info("MainThread: starting 3 parallel workers (one will fail)")
        self._logger.start_thread(
            "parallel-ok-a", "PYTHON", "tests.demo_library:_worker_simple", 10
        )
        self._logger.start_thread(
            "parallel-fail", "PYTHON", "tests.demo_library:_worker_failing"
        )
        self._logger.start_thread(
            "parallel-ok-b", "PYTHON", "tests.demo_library:_worker_simple", 20
        )
        try:
            self._logger.wait_all_threads()
        except AssertionError as err:
            # Let the test see the propagated error but keep it readable.
            logger.warn(f"Detected worker failure: {err}")
            raise


# ----------------------------------------------------------------------
# Module-level worker callables (referenced by dotted path above)
# ----------------------------------------------------------------------


def _worker_simple(idx: int) -> None:
    for step in range(3):
        logger.info(f"[worker {idx}] step {step}")
        time.sleep(0.01)
    logger.debug(f"[worker {idx}] done")


def _worker_nested() -> None:
    logger.info("worker enters nested structures")
    with thread_group("group-level"):
        with thread_for(
            assign=("${item}",), values=("alpha", "beta", "gamma")
        ) as for_:
            for value in ("alpha", "beta", "gamma"):
                with for_.iteration(item=value):
                    with thread_if(f"'${{item}}' == '{value}'"):
                        logger.info(f"processing {value}")
                        if value == "alpha":
                            logger.info("this is the alpha branch")

        with thread_try(patterns=("ValueError*",)) as handle:
            with handle.try_block():
                logger.info("running a risky block")
                raise ValueError("simulated failure inside TRY")
            if handle.caught is not None:
                with handle.except_block():
                    logger.warn(f"recovered from: {handle.caught}")
    logger.info("worker completed nested structures")


def _worker_failing() -> None:
    logger.info("worker is about to fail")
    time.sleep(0.02)
    raise RuntimeError("intentional failure from worker thread")


def _worker_stress(idx: int, steps: int) -> None:
    for step in range(steps):
        logger.info(f"[stress {idx}] step {step}")
        # Tiny sleep to increase the odds of true interleaving between
        # threads. Without thread-awareness the logs would collide on
        # MainThread's current keyword.
        time.sleep(0.001)
