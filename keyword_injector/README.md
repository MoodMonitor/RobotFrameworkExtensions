# Robot Framework Keyword Injector

An extension for Robot Framework that enables dynamic injection of keywords into the Robot namespace without needing to import them explicitly.

---

## Project Goal

This project aims to allow executing Python-defined keywords in Robot Framework's namespace without requiring the library to be imported in the test suite. It dynamically injects keywords into the Robot runtime environment, making them accessible just like built-in keywords.

---

## The Problem

Keywords that are not explicitly imported in a Robot Framework suite are not visible in the Robot namespace and cannot be executed using `Run Keyword` from the `BuiltIn` library.

This issue is demonstrated in the file example_library.py, which tries to call a keyword defined in `example_library3.py`. Since the keyword is not imported, the suite (`example_suite.robot`) fails at runtime.

You can reproduce the issue by running the suite yourself, or inspect the failure in the generated log file - `example_suite_log.html`

### Main challenges:
- Importing all required libraries is often inconvenient or even impossible in dynamic or threaded environments.
- Class-based keywords:
  - Automatically invoke the `__init__` method on import.
  - Do not work well with `Run Keyword`.
  - Can be called using `Call Method`, but it executes in the Python namespace rather than the Robot namespace, which results in:
    - Missing or incomplete log entries in `log.html`.
    - Limited or broken support for `BuiltIn` keywords and logging features.




---

##  The Solution

This project provides a solution by dynamically creating a `LibraryKeyword` instance and injecting it into the `BuiltIn` library’s keyword list. This makes the keyword:
- Visible in the Robot namespace.
- Executable via `Run Keyword`.
- Properly logged in `log.html`.
- Fully functional with `BuiltIn` features.

Implementation is available in the `keyword_injector.py` file.

