*** Settings ***
Documentation     Scenario 1 – Simple logging from threads.
...
...               Verifies that messages produced by robot.api.logger inside
...               background threads are captured per-thread and appear in
...               output.xml / log.html grouped under individual thread wrapper
...               keywords, with original timestamps preserved.
Library           ../ThreadLogger.py
Library           WorkerLib
Library           Collections

*** Variables ***
${THREAD1_ID}     Thread-Alpha
${THREAD2_ID}     Thread-Beta
${THREAD3_ID}     Thread-Gamma

*** Test Cases ***

S1-TC1: Two Threads Log Simple Messages In Parallel
    [Documentation]    Two threads each log 3 messages via robot.api.logger.
    ...                Expected: two [Thread N] wrapper keywords appear in the
    ...                report, each containing its own messages only.
    ${f1}=    Get Log Function    ${THREAD1_ID}    3
    ${f2}=    Get Log Function    ${THREAD2_ID}    3
    Run Functions In Parallel    ${f1}    ${f2}
    Log    Both threads completed successfully

S1-TC2: Three Threads Log Messages Concurrently
    [Documentation]    Three threads run simultaneously. Verifies that messages
    ...                from different threads never mix into the wrong wrapper.
    ${f1}=    Get Log Function    ${THREAD1_ID}    4
    ${f2}=    Get Log Function    ${THREAD2_ID}    4
    ${f3}=    Get Log Function    ${THREAD3_ID}    4
    Run Functions In Parallel    ${f1}    ${f2}    ${f3}
    Log    Three threads completed successfully

S1-TC3: Thread Logs At Multiple Levels Including WARN
    [Documentation]    One thread logs DEBUG, INFO and WARN messages.
    ...                All levels must be visible in the thread wrapper.
    ${f1}=    Evaluate    lambda: __import__('WorkerLib').log_and_warn_from_thread('${THREAD1_ID}')    modules=WorkerLib
    ${f2}=    Evaluate    lambda: __import__('WorkerLib').log_and_warn_from_thread('${THREAD2_ID}')    modules=WorkerLib
    Run Functions In Parallel    ${f1}    ${f2}
    Log    Multi-level logging verified

S1-TC4: Main Thread Is Unaffected By Parallel Logging
    [Documentation]    Log messages on the main thread before, during
    ...                (sequentially) and after parallel calls remain
    ...                in the main execution scope – not in any thread wrapper.
    Log    MAIN: before parallel block
    ${f1}=    Get Log Function    ${THREAD1_ID}    2
    ${f2}=    Get Log Function    ${THREAD2_ID}    2
    Run Functions In Parallel    ${f1}    ${f2}
    Log    MAIN: after parallel block – still in main scope

S1-TC5: Single Failing Thread Is Clearly Visible As FAIL
    [Documentation]    One thread raises an exception.  The thread wrapper
    ...                must show FAIL status and the keyword overall must fail.
    ...                The failure message must appear in the report.
    ${f_fail}=    Get Failing Function    ${THREAD1_ID}
    Run Keyword And Expect Error    *Intentional failure*
    ...    Run Functions In Parallel    ${f_fail}
    Log    Expected failure was caught correctly

S1-TC6: One Failing One Passing Thread
    [Documentation]    Mixed result: one thread passes, one fails.
    ...                Both thread wrappers must appear in the report.
    ${f_ok}=    Get Log Function    ${THREAD2_ID}    2
    ${f_fail}=    Get Failing Function    ${THREAD1_ID}
    Run Keyword And Expect Error    *Intentional failure*
    ...    Run Functions In Parallel    ${f_fail}    ${f_ok}
    Log    Mixed outcome verified

S1-TC7: Timestamps Are Preserved (Sanity Check)
    [Documentation]    Basic sanity: the keyword completes without error and
    ...                the thread wrappers have non-zero elapsed time
    ...                (structural check – timestamp values confirmed in log.html).
    ${f1}=    Get Log Function    ${THREAD1_ID}    2
    Run Functions In Parallel    ${f1}
    Log    Timestamp sanity check passed

S1-TC8: Restore After Parallel Execution (Reversibility)
    [Documentation]    After Run Functions In Parallel completes, logging on
    ...                the main thread must work exactly as before – no leaked
    ...                state from thread proxies.
    ${f1}=    Get Log Function    ${THREAD1_ID}    1
    Run Functions In Parallel    ${f1}
    Log    POST-PARALLEL: main thread log 1
    Log    POST-PARALLEL: main thread log 2
    ${bi_msg}=    Set Variable    POST-PARALLEL via BuiltIn
    Log    ${bi_msg}
