*** Keywords ***
Keyword With FOR Loop
    [Arguments]    ${count}=3
    Log    Starting FOR loop with ${count} iterations
    FOR    ${i}    IN RANGE    ${count}
        Log    FOR iteration ${i}
        ${value}=    Evaluate    ${i} * 10
        Log    Computed: ${i} * 10 = ${value}
    END
    Log    FOR loop complete

Keyword With IF ELSE
    [Arguments]    ${value}=4
    Log    Evaluating condition for value=${value}
    IF    ${value} > 3
        Log    Value ${value} is greater than 3
        Should Be True    ${value} > 3
    ELSE
        Log    Value ${value} is 3 or less
    END
    Log    IF/ELSE complete

Keyword With TRY EXCEPT
    Log    Starting TRY/EXCEPT block
    TRY
        Log    Inside TRY block
        Should Be Equal    foo    foo
        Log    Assertion passed in TRY
    EXCEPT    *    type=GLOB
        Log    Caught exception in EXCEPT    level=WARN
    FINALLY
        Log    Inside FINALLY block
    END
    Log    TRY/EXCEPT complete

Keyword With Nested Structures
    [Arguments]    ${iterations}=3
    Log    Starting nested structures
    FOR    ${i}    IN RANGE    ${iterations}
        Log    Outer FOR iteration ${i}
        IF    ${i} % 2 == 0
            Log    Even iteration ${i}
            TRY
                ${result}=    Evaluate    100 / (${i} + 1)
                Log    Division result: ${result}
            EXCEPT    *    type=GLOB
                Log    Division failed for iteration ${i}    level=WARN
            END
        ELSE
            Log    Odd iteration ${i}
        END
    END
    Log    Nested structures complete

Simple Log Keyword
    [Arguments]    ${message}    ${level}=INFO
    Log    ${message}    level=${level}
