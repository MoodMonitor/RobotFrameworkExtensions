*** Settings ***
Documentation    Reproduces the out-of-the-box thread-logging problem.
...              Messages logged from threading.Thread workers are dropped
...              by robot.output.librarylogger.write.
Library          demo_library.DemoLibrary

*** Test Cases ***
Baseline Thread Logging Is Broken
    [Documentation]    Three worker threads try to log 3 messages each.
    ...                The log should only show the MainThread messages.
    Run Worker Baseline    3
