#  Robot Framework Logging Threads

## Project Goal

Enable proper logging from Python threads in Robot Framework so that messages from threaded execution are captured and correctly displayed in `log.html`.

## The Problem

By default, Robot Framework **ignores logs coming from additional Python threads**. Even if `BuiltIn` keywords like `Run Keyword` are executed inside a thread:

- The keyword call may appear in `log.html`,  
- But **the messages and logs produced within the keyword** are missing.

As a result, while the threaded function is executed correctly, its behavior is not properly logged, making test review and debugging difficult or even impossible.

## The Solution

This project introduces a mechanism that captures log messages generated within threads and queues them during execution. Once all threads have completed, the queued logs are replayed and logged in the main thread using the default loggers, ensuring that messages appear in the correct order and without conflicts.

Meanwhile, logs from the main thread are processed and displayed immediately, as usual.

This approach ensures thread-safe logging by deferring thread-generated log output until the threads have finished, preventing race conditions or mixed log entries.

### Benefits

- Threaded logs now appear in `log.html` with correct formatting and timing.
- No need to modify existing Robot code or test syntax.
- Compatible with `BuiltIn` functions like `Log`, `Should Be Equal`, etc.
- Main thread continues logging in real-time.

The solution is implemented in the `logging_threads.py` file.
An example of the resulting log output can be found in the `example_suite_log.html` file.
