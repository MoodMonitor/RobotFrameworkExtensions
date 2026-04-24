*** Settings ***
Documentation    Stress test (many parallel threads) and verification
...              that no patch remains installed after Wait All Threads.
Library          demo_library.DemoLibrary
Library          reversibility_checks.py

*** Test Cases ***
Ten Parallel Workers Do Not Interleave
    [Documentation]    Ten threads each log five messages. Every message
    ...                must appear under its own Thread wrapper and
    ...                nowhere else.
    Launch Many Parallel Workers    10    5

Patches Are Removed After Wait All Threads
    [Documentation]    Verifies that the monkey-patch on
    ...                librarylogger.write is gone after the worker
    ...                threads have been joined.
    Launch Many Parallel Workers    2    1
    Assert No Patches Installed

Logging After Wait Still Works Normally
    [Documentation]    Reconfirms zero-interference: logging from the
    ...                MainThread after wait must behave exactly like
    ...                vanilla Robot Framework.
    Launch Many Parallel Workers    2    1
    Log    After-wait message must show up under the current keyword.
