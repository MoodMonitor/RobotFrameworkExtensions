*** Settings ***
Library    robot_thread_capture.py
Library    threaded_demo_library.py
Test Setup    Enable Thread Logging Capture

*** Test Cases ***
Thread Logs Are Grouped Per Thread
    Log From Two Threads

Threaded Keyword Structure Is Preserved
    Run Composite Keywords In Threads

Thread Failure Is Visible
    Run Failing Thread

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
