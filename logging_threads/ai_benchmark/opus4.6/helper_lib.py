"""Helper Python library for testing thread_executor.

Contains functions designed to be run inside worker threads.  Each function
exercises a different aspect of the threading solution:

- simple logging via robot.api.logger
- keyword execution via BuiltIn
- nested control structures (FOR, IF, TRY-EXCEPT)
- deliberate error scenarios
"""

import time
from robot.api import logger
from robot.libraries.BuiltIn import BuiltIn


# ---------------------------------------------------------------------------
# Simple logging functions
# ---------------------------------------------------------------------------

def simple_log_from_thread():
    """Log several messages at different levels from a thread."""
    logger.info("Hello from thread - INFO level")
    logger.debug("Hello from thread - DEBUG level")
    logger.warn("Hello from thread - WARN level")
    logger.info("Thread timestamp test", html=False)
    logger.info("<b>HTML message from thread</b>", html=True)


def log_with_delays():
    """Log messages with small delays to test timestamp ordering."""
    for i in range(5):
        logger.info(f"Delayed message #{i} from thread")
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# Keyword execution functions
# ---------------------------------------------------------------------------

def run_keywords_from_thread():
    """Execute BuiltIn keywords from a thread."""
    bi = BuiltIn()
    bi.log("Message via BuiltIn.log from thread", level="INFO")
    bi.log("Another message via BuiltIn.log", level="DEBUG")
    result = bi.evaluate("1 + 2 + 3")
    bi.log(f"Evaluate result: {result}")
    bi.should_be_equal_as_integers(result, 6)


def run_keyword_with_sleep():
    """Execute keywords that include a sleep."""
    bi = BuiltIn()
    bi.log("Before sleep in thread")
    bi.sleep("0.1s", reason="Testing sleep in thread")
    bi.log("After sleep in thread")


# ---------------------------------------------------------------------------
# Nested control structure functions
# ---------------------------------------------------------------------------

def run_for_loop_in_thread():
    """Execute a FOR-like loop with keyword calls from a thread."""
    bi = BuiltIn()
    bi.log("Starting FOR loop simulation in thread")
    for i in range(3):
        bi.log(f"FOR iteration {i}")
        value = bi.evaluate(f"{i} * 10")
        bi.log(f"Computed value: {value}")
    bi.log("FOR loop complete")


def run_conditional_in_thread():
    """Execute conditional logic with keyword calls from a thread."""
    bi = BuiltIn()
    value = bi.evaluate("2 + 2")
    bi.log(f"Evaluated: 2 + 2 = {value}")
    if int(str(value)) == 4:
        bi.log("Condition TRUE: 2+2 equals 4")
        bi.should_be_equal_as_integers(value, 4)
    else:
        bi.log("Condition FALSE: unexpected!")
        bi.fail("2+2 should equal 4")


def run_try_except_in_thread():
    """Execute try/except logic with keyword calls from a thread."""
    bi = BuiltIn()
    bi.log("Attempting operation that might fail")
    try:
        bi.should_be_equal("foo", "foo")
        bi.log("First assertion passed")
    except Exception as e:
        bi.log(f"Caught exception: {e}", level="WARN")

    try:
        # This will intentionally fail
        result = 10 / 0
    except ZeroDivisionError as e:
        bi.log(f"Caught expected ZeroDivisionError: {e}", level="WARN")
        bi.log("Error handling complete")


def run_nested_structures_in_thread():
    """Complex nested structures: loops with conditionals and error handling."""
    bi = BuiltIn()
    bi.log("Starting complex nested execution")

    for i in range(3):
        bi.log(f"Outer iteration {i}")
        if i % 2 == 0:
            bi.log(f"  Even iteration {i}: running extra check")
            bi.should_be_true(f"{i} % 2 == 0")
        else:
            bi.log(f"  Odd iteration {i}: skipping check")

        try:
            if i == 1:
                raise ValueError(f"Simulated error at iteration {i}")
            bi.log(f"  No error at iteration {i}")
        except ValueError as e:
            bi.log(f"  Handled error: {e}", level="WARN")

    bi.log("Complex nested execution complete")


# ---------------------------------------------------------------------------
# Error scenario functions
# ---------------------------------------------------------------------------

def thread_that_fails():
    """A function that deliberately raises an exception."""
    logger.info("About to fail...")
    raise RuntimeError("Deliberate failure from thread!")


def thread_partial_success():
    """Logs some messages then fails."""
    bi = BuiltIn()
    bi.log("Step 1: OK")
    bi.log("Step 2: OK")
    bi.log("Step 3: About to fail...")
    raise RuntimeError("Partial failure after successful steps")


# ---------------------------------------------------------------------------
# Multiple threads stress test
# ---------------------------------------------------------------------------

def worker_function(worker_id=None):
    """Generic worker for multi-thread tests."""
    if worker_id is None:
        worker_id = "unknown"
    bi = BuiltIn()
    bi.log(f"Worker {worker_id} starting")
    for i in range(3):
        bi.log(f"Worker {worker_id}: step {i}")
        time.sleep(0.02)
    bi.log(f"Worker {worker_id} complete")


# ---------------------------------------------------------------------------
# Patch cleanup verification
# ---------------------------------------------------------------------------

def normal_logging_after_threads():
    """Just log normally — used to verify patches were cleaned up."""
    logger.info("Normal logging works after threads!")
    BuiltIn().log("BuiltIn.log works normally after threads")


# ---------------------------------------------------------------------------
# RF keyword execution — calls user keywords with native RF structures
# ---------------------------------------------------------------------------

def run_rf_for_keyword_in_thread():
    """Call a Robot Framework user keyword containing a FOR loop."""
    bi = BuiltIn()
    bi.log("About to run RF FOR keyword from thread")
    bi.run_keyword("Keyword With FOR Loop", 3)
    bi.log("RF FOR keyword complete")


def run_rf_if_keyword_in_thread():
    """Call a Robot Framework user keyword containing IF/ELSE."""
    bi = BuiltIn()
    bi.log("About to run RF IF keyword from thread")
    bi.run_keyword("Keyword With IF ELSE", 5)
    bi.log("RF IF keyword complete")


def run_rf_try_keyword_in_thread():
    """Call a Robot Framework user keyword containing TRY/EXCEPT."""
    bi = BuiltIn()
    bi.log("About to run RF TRY keyword from thread")
    bi.run_keyword("Keyword With TRY EXCEPT")
    bi.log("RF TRY keyword complete")


def run_rf_nested_keyword_in_thread():
    """Call a Robot Framework user keyword with complex nested structures."""
    bi = BuiltIn()
    bi.log("About to run RF nested keyword from thread")
    bi.run_keyword("Keyword With Nested Structures", 4)
    bi.log("RF nested keyword complete")
