# Robot Framework Extensions

This repository contains experimental extensions and utilities for enhancing the behavior of [Robot Framework](https://robotframework.org/), especially when working with dynamic Python code and multi-threaded execution.

## Repository Structure

### `keyword_injector/`

A utility that allows you to **inject Python functions or class methods as Robot Framework keywords at runtime**, without the need to import them explicitly in test suites.

- Solves the issue where keywords defined in Python are not available in Robot’s namespace unless pre-imported.
- Ensures proper visibility in `log.html` and compatibility with `BuiltIn` keywords.
- Useful when dynamically building libraries or working with class-based logic.

👉 See [`keyword_injector/README.md`](./keyword_injector/README.md) for details.

---

### `logging_threads/`

Provides a logging mechanism that ensures **log messages from Python threads are correctly captured and displayed in Robot Framework’s `log.html`**.

- Stores thread-generated logs in a queue during execution.
- Re-injects logs into Robot’s main logging context once threads finish.
- Preserves correct ordering, structure, and timestamping of logs.

👉 See [`logging_threads/README.md`](./logging_threads/README.md) for implementation and usage.

---

##  Purpose

These tools aim to bridge the gap between Python’s flexibility and Robot Framework’s logging and keyword execution model — especially useful when working with:

- Custom dynamic libraries
- Class-based architecture
- Parallel/threaded execution in Python

---
