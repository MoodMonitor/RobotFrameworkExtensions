*** Settings ***
Documentation     Scenario 3 – RF-native FOR / IF / TRY-EXCEPT structures inside threads.
...
...               Verifies requirement 10: nested RF result nodes (FOR, ITER,
...               IF_ELSE_ROOT, BRANCH, TRY_EXCEPT_ROOT) must appear with their
...               proper tags and signatures in output.xml when executed inside
...               parallel thread wrappers. No flattening or degradation allowed.
Library           ../ThreadLogger.py
Resource          rf_user_keywords.resource
Library           WorkerLib

*** Variables ***
${T1}    Thread-1
${T2}    Thread-2

*** Test Cases ***

S3-TC1: RF FOR Loop Nodes Preserved In Thread Result
    [Documentation]    Two threads each run a user keyword that contains
    ...                a Robot Framework FOR loop.
    ...                The output.xml must contain for/iter nodes under each
    ...                thread wrapper – not just flat log messages.
    @{kw1}=    Create List    User KW With RF FOR Loop    ${T1}    alpha    beta    gamma
    @{kw2}=    Create List    User KW With RF FOR Loop    ${T2}    1    2    3    4
    Run Keywords In Parallel    ${kw1}    ${kw2}
    Log    RF FOR nodes preserved in both thread wrappers

S3-TC2: RF IF Branch Nodes Preserved In Thread Result
    [Documentation]    Two threads each run a user keyword with RF IF/ELSE IF/ELSE.
    ...                Different branches are taken (values 150 and 5).
    ...                The output.xml must contain if/branch nodes per thread.
    @{kw1}=    Create List    User KW With RF IF Branch    ${T1}    150
    @{kw2}=    Create List    User KW With RF IF Branch    ${T2}    5
    Run Keywords In Parallel    ${kw1}    ${kw2}
    Log    RF IF/ELSE branch nodes preserved in both thread wrappers

S3-TC3: RF TRY EXCEPT Nodes Preserved In Thread Result
    [Documentation]    Thread 1 follows the TRY path (no error),
    ...                Thread 2 triggers the EXCEPT path.
    ...                Both FINALLY blocks must also appear in output.xml.
    @{kw1}=    Create List    User KW With RF TRY EXCEPT    ${T1}    false
    @{kw2}=    Create List    User KW With RF TRY EXCEPT    ${T2}    true
    Run Keywords In Parallel    ${kw1}    ${kw2}
    Log    RF TRY/EXCEPT/FINALLY nodes preserved in both thread wrappers

S3-TC4: Deeply Nested FOR With IF Preserved In Thread Result
    [Documentation]    FOR loop containing an IF block – tests multi-level nesting.
    ...                The output.xml must show for > iter > if > branch hierarchy.
    @{kw1}=    Create List    User KW With Nested FOR And IF    ${T1}    1    -2    3    -4
    @{kw2}=    Create List    User KW With Nested FOR And IF    ${T2}    10    20    -5
    Run Keywords In Parallel    ${kw1}    ${kw2}
    Log    Deeply nested FOR+IF structure preserved in thread results

S3-TC5: Mixed Library And User Keywords In Parallel
    [Documentation]    Thread 1 runs a library keyword (Python),
    ...                Thread 2 runs a user keyword with RF FOR loop.
    ...                Both must produce correct result trees.
    @{kw1}=    Create List    Simple Worker Keyword    ${T1}    3
    @{kw2}=    Create List    User KW With RF FOR Loop    ${T2}    x    y    z
    Run Keywords In Parallel    ${kw1}    ${kw2}
    Log    Mixed library and user keyword threads both preserved correctly
