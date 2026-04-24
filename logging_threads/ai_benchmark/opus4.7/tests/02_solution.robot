*** Settings ***
Documentation    Shows that thread logs are captured with ThreadLogger.
Library          demo_library.DemoLibrary

*** Test Cases ***
Thread Logs Are Preserved
    [Documentation]    Three worker threads. Their messages must appear
    ...                in output.xml, grouped per thread, with original
    ...                timestamps and without mixing with MainThread.
    Run Workers With Thread Logger    3

Nested Structures From Thread Are Preserved
    [Documentation]    The worker uses thread_for / thread_if /
    ...                thread_try context managers. In output.xml the
    ...                resulting <for>, <iter>, <if>, <branch>, <try>
    ...                tags must be present exactly as if they had been
    ...                written from Robot Framework itself.
    Run Worker With Nested Structures

Running Robot Keyword In Thread
    [Documentation]    Calls a Robot Framework library keyword from
    ...                inside a worker thread and records it as a proper
    ...                <kw> element.
    Run Keyword In Worker Thread    Log    hello from a background thread

Parallel Workers With Failure
    [Documentation]    Three parallel workers, one fails. The test must
    ...                fail with a clear message but every worker's log
    ...                tree must still be present in output.xml.
    Run Keyword And Expect Error    *intentional failure*
    ...    Run Parallel Workers With One Failing
