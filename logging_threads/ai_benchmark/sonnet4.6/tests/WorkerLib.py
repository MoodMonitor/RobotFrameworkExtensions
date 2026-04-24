"""
WorkerLib – test helper library that simulates real user code patterns
that interact with Robot Framework from inside threads.

Scenario 1 helpers  – functions that call robot.api.logger directly
                      (zero-interface: no awareness of ThreadLogger).
Scenario 2 helpers  – RF keywords (called by ThreadLogger) that contain
                      nested FOR, IF, TRY-EXCEPT structures.
"""

import time

from robot.api import logger as rf_logger
from robot.libraries.BuiltIn import BuiltIn


# ---------------------------------------------------------------------------
# Scenario 1 – simple logging helpers (called as Python functions)
# ---------------------------------------------------------------------------

def log_messages_from_thread(thread_id, count=3, delay=0.0):
    """Log ``count`` messages; simulates existing user thread code."""
    rf_logger.info(f"[{thread_id}] Thread started")
    for i in range(1, count + 1):
        if delay:
            time.sleep(delay)
        rf_logger.info(f"[{thread_id}] Message {i} of {count}")
    rf_logger.info(f"[{thread_id}] Thread finished")


def log_and_warn_from_thread(thread_id):
    """Log at multiple levels including WARN."""
    rf_logger.debug(f"[{thread_id}] DEBUG entry")
    rf_logger.info(f"[{thread_id}] INFO entry")
    rf_logger.warn(f"[{thread_id}] WARN entry")
    rf_logger.info(f"[{thread_id}] After warn")


def failing_thread_function(thread_id):
    """Deliberately raises an exception to verify error visibility."""
    rf_logger.info(f"[{thread_id}] About to fail")
    raise RuntimeError(f"Intentional failure in {thread_id}")


# ---------------------------------------------------------------------------
# Scenario 2 – RF keywords with nested structures
# ---------------------------------------------------------------------------

class WorkerLib:
    """Robot Framework library providing worker keywords for thread tests."""

    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    # --- Simple keyword -------------------------------------------------------

    def simple_worker_keyword(self, thread_id, steps=3):
        """Log a sequence of steps – plain library keyword."""
        steps = int(steps)
        bi = BuiltIn()
        bi.log(f"[{thread_id}] Keyword starting, steps={steps}")
        for i in range(1, steps + 1):
            bi.log(f"[{thread_id}] Step {i}/{steps}")
        bi.log(f"[{thread_id}] Keyword done")
        return f"{thread_id}:OK"

    # --- Keyword with FOR loop -------------------------------------------------

    def keyword_with_for_loop(self, thread_id, items="a,b,c"):
        """Execute a FOR loop internally to verify nested structure in output."""
        bi = BuiltIn()
        bi.log(f"[{thread_id}] FOR loop keyword starting")
        result = []
        for item in items.split(","):
            bi.log(f"[{thread_id}] Processing item: {item.strip()}")
            result.append(item.strip().upper())
        bi.log(f"[{thread_id}] FOR loop done, result: {result}")
        return ",".join(result)

    # --- Keyword with IF branch ------------------------------------------------

    def keyword_with_if_branch(self, thread_id, value="42"):
        """Use BuiltIn.run_keyword_if to produce IF node in output."""
        bi = BuiltIn()
        bi.log(f"[{thread_id}] IF keyword starting, value={value}")
        val = int(value)
        if val > 10:
            bi.log(f"[{thread_id}] Branch: value {val} is large")
            category = "large"
        else:
            bi.log(f"[{thread_id}] Branch: value {val} is small")
            category = "small"
        bi.log(f"[{thread_id}] IF keyword done, category={category}")
        return category

    # --- Keyword with TRY-EXCEPT ----------------------------------------------

    def keyword_with_try_except(self, thread_id, should_fail="false"):
        """Use try/except internally to verify TRY node in output."""
        bi = BuiltIn()
        bi.log(f"[{thread_id}] TRY keyword starting")
        try:
            if should_fail.lower() == "true":
                raise ValueError(f"[{thread_id}] Deliberate inner error")
            bi.log(f"[{thread_id}] Inner block succeeded")
            result = "success"
        except ValueError as exc:
            bi.log(f"[{thread_id}] Caught: {exc}", "WARN")
            result = "caught"
        bi.log(f"[{thread_id}] TRY keyword done, result={result}")
        return result

    # --- Failing keyword -------------------------------------------------------

    def failing_worker_keyword(self, thread_id):
        """Keyword that intentionally fails to test error visibility."""
        bi = BuiltIn()
        bi.log(f"[{thread_id}] About to fail")
        raise AssertionError(f"[{thread_id}] Intentional keyword failure")

    # --- Helper: return a log function ----------------------------------------

    def get_log_function(self, thread_id, count=3):
        """Return a lambda suitable for Run Functions In Parallel."""
        return lambda: log_messages_from_thread(thread_id, int(count))

    def get_failing_function(self, thread_id):
        """Return a lambda that will fail."""
        return lambda: failing_thread_function(thread_id)
