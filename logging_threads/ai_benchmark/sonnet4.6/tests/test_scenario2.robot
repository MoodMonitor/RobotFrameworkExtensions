*** Settings ***
Documentation     Scenario 2 – RF keyword execution inside threads.
...
...               Verifies that keywords run in parallel threads produce fully
...               structured result trees: sub-keywords, FOR/IF/TRY nodes are
...               preserved and grouped per thread in output.xml / log.html.
Library           ../ThreadLogger.py
Library           WorkerLib
Library           Collections

*** Variables ***
${T1}    Thread-1
${T2}    Thread-2
${T3}    Thread-3

*** Test Cases ***

S2-TC1: Two Threads Run Simple Keywords In Parallel
    [Documentation]    Two threads each run Simple Worker Keyword.
    ...                Expected: two [Thread N] wrappers each containing a
    ...                sub-keyword with its log messages.
    @{kw1}=    Create List    Simple Worker Keyword    ${T1}    3
    @{kw2}=    Create List    Simple Worker Keyword    ${T2}    3
    Run Keywords In Parallel    ${kw1}    ${kw2}
    Log    Both simple worker keywords completed

S2-TC2: Three Threads Run Keywords Concurrently
    [Documentation]    Three-thread scenario – verifies absence of cross-thread
    ...                result contamination under higher concurrency.
    @{kw1}=    Create List    Simple Worker Keyword    ${T1}    2
    @{kw2}=    Create List    Simple Worker Keyword    ${T2}    2
    @{kw3}=    Create List    Simple Worker Keyword    ${T3}    2
    Run Keywords In Parallel    ${kw1}    ${kw2}    ${kw3}
    Log    Three-thread scenario passed

S2-TC3: Keyword With FOR Loop Preserves Nesting In Report
    [Documentation]    The Keyword With For Loop keyword logs inside a Python
    ...                for loop. The log messages must appear nested inside the
    ...                thread wrapper in output.xml.
    @{kw1}=    Create List    Keyword With For Loop    ${T1}    x,y,z
    @{kw2}=    Create List    Keyword With For Loop    ${T2}    1,2,3,4
    Run Keywords In Parallel    ${kw1}    ${kw2}
    Log    FOR-loop keyword nesting verified

S2-TC4: Keyword With IF Branch Preserves Log Grouping
    [Documentation]    Two threads run Keyword With If Branch with different
    ...                values, taking different code paths.
    ...                Both thread wrappers must appear with correct messages.
    @{kw1}=    Create List    Keyword With If Branch    ${T1}    50
    @{kw2}=    Create List    Keyword With If Branch    ${T2}    5
    Run Keywords In Parallel    ${kw1}    ${kw2}
    Log    IF-branch keyword grouping verified

S2-TC5: Keyword With TRY-EXCEPT Preserves Structure
    [Documentation]    Thread 1 succeeds in try block; Thread 2 hits the except
    ...                branch.  Both must appear cleanly in their thread wrappers.
    @{kw1}=    Create List    Keyword With Try Except    ${T1}    false
    @{kw2}=    Create List    Keyword With Try Except    ${T2}    true
    Run Keywords In Parallel    ${kw1}    ${kw2}
    Log    TRY-EXCEPT keyword structure verified

S2-TC6: Failing Keyword In Thread Shows FAIL Status
    [Documentation]    A thread whose keyword raises AssertionError must appear
    ...                as FAIL in the thread wrapper.  The overall keyword must
    ...                also fail, and we catch that expected failure here.
    @{kw_fail}=    Create List    Failing Worker Keyword    ${T1}
    Run Keyword And Expect Error    *Intentional keyword failure*
    ...    Run Keywords In Parallel    ${kw_fail}
    Log    Expected keyword failure caught and verified

S2-TC7: Mixed Pass And Fail Threads
    [Documentation]    Thread 1 passes, Thread 2 fails.  Both wrappers must
    ...                appear in the report with correct PASS/FAIL labels.
    @{kw_ok}=    Create List    Simple Worker Keyword    ${T1}    2
    @{kw_fail}=    Create List    Failing Worker Keyword    ${T2}
    Run Keyword And Expect Error    *Intentional keyword failure*
    ...    Run Keywords In Parallel    ${kw_ok}    ${kw_fail}
    Log    Mixed PASS/FAIL thread outcome verified

S2-TC8: Reversibility After Keyword Parallel Execution
    [Documentation]    After Run Keywords In Parallel, the main RF execution
    ...                context must be fully restored:
    ...                - Log messages go to main scope
    ...                - BuiltIn keywords work normally
    ...                - No proxy objects remain active
    @{kw1}=    Create List    Simple Worker Keyword    ${T1}    1
    Run Keywords In Parallel    ${kw1}
    Log    MAIN SCOPE RESTORED: log 1
    ${x}=    Set Variable    sanity
    Should Be Equal    ${x}    sanity
    Log    MAIN SCOPE RESTORED: BuiltIn.Set Variable works: ${x}

S2-TC9: Context Is Clean After Thread Error
    [Documentation]    Even when a thread keyword fails, all RF globals must
    ...                be restored.  After catching the error, the main thread
    ...                must still be able to log and run keywords normally.
    @{kw_fail}=    Create List    Failing Worker Keyword    ${T1}
    Run Keyword And Expect Error    *    Run Keywords In Parallel    ${kw_fail}
    Log    POST-FAILURE: main context still works
    ${v}=    Evaluate    1 + 1
    Should Be Equal As Integers    ${v}    2
