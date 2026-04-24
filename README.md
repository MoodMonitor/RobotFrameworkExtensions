# Robot Framework Extensions

Practical extensions for advanced Robot Framework workflows.

This repository focuses on two real-world pain points:
- Dynamic keyword exposure from Python code.
- Correct logging for threaded Python execution in Robot artifacts.

It also documents a direct benchmark where the human implementation is compared against multiple AI-generated implementations for the same threading/logging task.

## What Is Included

### `keyword_injector/`

Runtime keyword injection into Robot namespace without explicit suite imports.

- Exposes Python functions and methods as executable Robot keywords.
- Keeps compatibility with `BuiltIn` and normal `Run Keyword` usage.
- Improves visibility and behavior in `log.html`.

See: [`keyword_injector/README.md`](./keyword_injector/README.md)

### `logging_threads/`

Thread-aware logging flow for Robot Framework.

- Captures logs generated in worker threads.
- Replays them in the main Robot logging context after thread completion.
- Preserves ordering and readability in `log.html`.

See: [`logging_threads/README.md`](./logging_threads/README.md)

## Benchmark: Human Solution vs AI Solutions

This benchmark is not a generic showcase. It is a direct **head-to-head comparison** of:
- **My solution** (`logging_threads.py`),
- versus **AI-generated solutions** (Gemini 3.1 Pro, Sonnet 4.6, Opus 4.6, Opus 4.7, GPT 5.4).

All solutions are evaluated against the same task and strict acceptance criteria, especially:
- Zero-Interference (no required changes in user thread code),
- Reversibility (full cleanup after thread execution),
- structure fidelity in `output.xml` (FOR/IF/TRY preserved),
- no Robot Framework source edits.

Benchmark materials are located at:
- [`logging_threads/ai_benchmark/README.md`](./logging_threads/ai_benchmark/README.md)
- [`logging_threads/ai_benchmark/task.txt`](./logging_threads/ai_benchmark/task.txt)

The benchmark includes:
- requirement-by-requirement scoring,
- technical ranking,
- architectural trade-offs and risk notes,
- final assessment of why the human implementation is the winning balance.

## Quick Start

From this directory:

```bash
python -m robot logging_threads/example_suite.robot
python -m robot keyword_injector/example_suite.robot
```

Then inspect generated logs to verify behavior.

## Why This Repository

The goal is to bridge Python flexibility with Robot Framework execution and reporting constraints, especially for:
- Dynamic and class-based library patterns.
- Concurrent execution with traceable logs.
- Production-safe behavior with minimal API interference.

Additionally, the repository serves as evidence-backed documentation of engineering decisions, where the final solution is justified through measurable comparison with AI alternatives.