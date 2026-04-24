*** Settings ***
Library    mock_thread_lib.py
Library    ThreadInterceptorLibrary.py

*** Test Cases ***
Test Logging Without Interceptor
    [Documentation]    Threads run but their logs may be mismatched or lost.
    Start Threads

Test Logging With Interceptor
    [Documentation]    Thread logs are caught and played back nicely.
    Start Thread Interception
    Start Threads
    Stop And Replay Thread Logs
