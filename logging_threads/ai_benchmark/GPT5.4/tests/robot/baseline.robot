*** Settings ***
Library    threaded_demo_library.py

*** Test Cases ***
Baseline Direct Thread Logging Is Lost
    Log From Two Threads

Baseline Threaded Keyword Execution Is Not Grouped
    Run Composite Keywords In Threads

*** Keywords ***
Worker Composite Keyword
    [Arguments]    ${index}
    Log    worker ${index} start
    FOR    ${item}    IN    alpha    boom    omega
        IF    '${item}' == 'boom'
            TRY
                Log    try-${index}-${item}
            EXCEPT    *
                Log    except-${index}
            END
        ELSE
            Log    item-${index}-${item}
        END
    END
    Log    worker ${index} end
