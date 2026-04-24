*** Settings ***
Documentation    User keywords with RF-native FOR / IF / TRY-EXCEPT structures
...              used to verify that nested RF result nodes are preserved when
...              keywords are executed inside parallel threads.
Library          Collections

*** Keywords ***

User KW With RF FOR Loop
    [Documentation]    RF FOR loop – produces FOR+ITER nodes in output.xml
    [Arguments]    ${thread_id}    @{items}
    Log    [${thread_id}] RF FOR loop starting
    FOR    ${item}    IN    @{items}
        Log    [${thread_id}] RF FOR item: ${item}
    END
    Log    [${thread_id}] RF FOR loop done

User KW With RF IF Branch
    [Documentation]    RF IF/ELSE IF/ELSE – produces IF+BRANCH nodes in output.xml
    [Arguments]    ${thread_id}    ${value}
    Log    [${thread_id}] RF IF starting with value=${value}
    IF    ${value} > 100
        Log    [${thread_id}] Branch: very large (${value} > 100)
    ELSE IF    ${value} > 10
        Log    [${thread_id}] Branch: medium (${value} > 10)
    ELSE
        Log    [${thread_id}] Branch: small (${value} <= 10)
    END
    Log    [${thread_id}] RF IF done

User KW With RF TRY EXCEPT
    [Documentation]    RF TRY/EXCEPT/FINALLY – produces TRY+BRANCH nodes in output.xml
    [Arguments]    ${thread_id}    ${should_fail}=false
    Log    [${thread_id}] RF TRY starting
    TRY
        IF    '${should_fail}' == 'true'
            Fail    Deliberate failure in ${thread_id}
        END
        Log    [${thread_id}] TRY block succeeded
    EXCEPT    *    type=GLOB
        Log    [${thread_id}] EXCEPT block caught error    level=WARN
    FINALLY
        Log    [${thread_id}] FINALLY block always runs
    END
    Log    [${thread_id}] RF TRY done

User KW With Nested FOR And IF
    [Documentation]    FOR loop containing IF branch – deep nesting in output.xml
    [Arguments]    ${thread_id}    @{values}
    Log    [${thread_id}] Nested FOR+IF starting
    FOR    ${val}    IN    @{values}
        IF    ${val} > 0
            Log    [${thread_id}] Positive: ${val}
        ELSE
            Log    [${thread_id}] Non-positive: ${val}
        END
    END
    Log    [${thread_id}] Nested FOR+IF done
