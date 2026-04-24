*** Settings ***
Library           thread_executor.py
Library           helper_lib.py
Library           Collections
Resource          test_keywords.resource

*** Test Cases ***
Simple Logging From Threads
    [Documentation]    Verify that simple robot.api.logger calls from threads
    ...                are captured and appear in the output.
    Log    Starting simple logging test from MainThread
    &{threads}=    Create Dictionary
    ...    logger1=helper_lib.simple_log_from_thread
    ...    logger2=helper_lib.log_with_delays
    Run In Threads    &{threads}
    Log    Simple logging test complete

Keyword Execution From Threads
    [Documentation]    Verify that BuiltIn keyword calls from threads
    ...                are captured with proper structure.
    Log    Starting keyword execution test
    &{threads}=    Create Dictionary
    ...    kw_runner=helper_lib.run_keywords_from_thread
    ...    kw_sleeper=helper_lib.run_keyword_with_sleep
    Run In Threads    &{threads}
    Log    Keyword execution test complete

Nested Structures In Threads
    [Documentation]    Verify that FOR loops, IF/ELSE, and TRY/EXCEPT
    ...                executed inside threads preserve their structure.
    Log    Starting nested structures test
    &{threads}=    Create Dictionary
    ...    for_loop=helper_lib.run_for_loop_in_thread
    ...    conditional=helper_lib.run_conditional_in_thread
    ...    try_except=helper_lib.run_try_except_in_thread
    Run In Threads    &{threads}
    Log    Nested structures test complete

Complex Nested Structures
    [Documentation]    Complex nesting: loops with conditionals and error handling.
    Log    Starting complex nested test
    &{threads}=    Create Dictionary
    ...    complex=helper_lib.run_nested_structures_in_thread
    Run In Threads    &{threads}
    Log    Complex nested test complete

Thread Error Handling
    [Documentation]    Verify that thread errors are properly reported
    ...                and visible in the output.
    Log    Starting error handling test
    ${status}=    Run Keyword And Return Status
    ...    Run In Threads    failing_thread=helper_lib.thread_that_fails
    Should Be Equal    ${status}    ${FALSE}
    Log    Error handling test complete - failure was caught

Partial Failure With Logs
    [Documentation]    Verify that logs before a thread failure are preserved.
    Log    Starting partial failure test
    ${status}=    Run Keyword And Return Status
    ...    Run In Threads    partial=helper_lib.thread_partial_success
    Should Be Equal    ${status}    ${FALSE}
    Log    Partial failure test complete

Multiple Concurrent Threads
    [Documentation]    Verify correct behavior with many parallel threads.
    Log    Starting multi-thread test
    @{t1}=    Create List    worker_0    helper_lib.worker_function    0
    @{t2}=    Create List    worker_1    helper_lib.worker_function    1
    @{t3}=    Create List    worker_2    helper_lib.worker_function    2
    @{t4}=    Create List    worker_3    helper_lib.worker_function    3
    Run In Threads With Args    ${t1}    ${t2}    ${t3}    ${t4}
    Log    Multi-thread test complete

Patch Cleanup Verification
    [Documentation]    After threaded execution, verify that normal RF logging
    ...                still works correctly (patches fully reverted).
    Log    Before threaded execution
    &{threads}=    Create Dictionary
    ...    worker=helper_lib.simple_log_from_thread
    Run In Threads    &{threads}
    Log    After threaded execution - testing normal logging
    ${result}=    Evaluate    1 + 1
    Should Be Equal As Integers    ${result}    2
    Log    Normal keyword execution confirmed OK

RF FOR Loop In Thread
    [Documentation]    Verify that a Robot Framework FOR loop keyword
    ...                executed in a thread preserves native <for> XML tags.
    Log    Starting RF FOR loop test
    &{threads}=    Create Dictionary
    ...    for_worker=helper_lib.run_rf_for_keyword_in_thread
    Run In Threads    &{threads}
    Log    RF FOR loop test complete

RF IF ELSE In Thread
    [Documentation]    Verify that RF IF/ELSE keyword preserves native <if> XML tags.
    Log    Starting RF IF/ELSE test
    &{threads}=    Create Dictionary
    ...    if_worker=helper_lib.run_rf_if_keyword_in_thread
    Run In Threads    &{threads}
    Log    RF IF/ELSE test complete

RF TRY EXCEPT In Thread
    [Documentation]    Verify that RF TRY/EXCEPT keyword preserves native <try> XML tags.
    Log    Starting RF TRY/EXCEPT test
    &{threads}=    Create Dictionary
    ...    try_worker=helper_lib.run_rf_try_keyword_in_thread
    Run In Threads    &{threads}
    Log    RF TRY/EXCEPT test complete

RF Nested Structures In Thread
    [Documentation]    Verify that complex nested RF structures (FOR+IF+TRY)
    ...                are fully preserved with native XML tags in thread output.
    Log    Starting RF nested structures test
    &{threads}=    Create Dictionary
    ...    nested_worker=helper_lib.run_rf_nested_keyword_in_thread
    Run In Threads    &{threads}
    Log    RF nested structures test complete
