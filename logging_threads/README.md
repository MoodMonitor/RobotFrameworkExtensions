# 🧵 rf-thread-logging-with-AI-benchmark

> **Two things in one repo:**  
> 1️⃣ A production-ready, thread-safe logging library for Robot Framework.  
> 2️⃣ A fascinating benchmark of 5 top AI models trying (and mostly failing) to solve the exact same architectural problem.

![Robot Framework](https://img.shields.io/badge/Robot%20Framework-7.2%2B-blue)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)

---

## Table of Contents

- [Part 1 - The Library](#part-1--the-library)
  - [The Problem](#the-problem)
  - [Usage](#usage)
- [Part 2 - The Benchmark](#part-2--the-benchmark)
  - [The Task](#the-task)
  - [Results at a Glance](#results-at-a-glance)
  - [Why the human solution won](#why-the-human-solution-won)
  - [Full Analysis](#full-analysis)
  - [My Final Comment](#my-final-comment)

---

# Part 1 - The Library

## The Problem

Robot Framework **silently drops all log messages from Python threads**.  
If your library spawns threads (parallel API calls, background tasks, load testing), their logs never reach `log.html` or `output.xml`:

```python
import threading
from robot.api import logger

def check_endpoint(url):
    response = requests.get(url)
    logger.info(f"Status: {response.status_code}")  # ← this disappears
    assert response.status_code == 200

t = threading.Thread(target=check_endpoint, args=("https://example.com",))
t.start()
t.join()
# logs are gone from the report
```

Nested structures (`FOR`, `IF`, `TRY-EXCEPT`) executed inside threads are flattened into a confusing, unstructured mess in the report.

## Usage

```python
from logging_threads import LoggingThreads
from robot.libraries.BuiltIn import BuiltIn

def my_worker(url):
    BuiltIn().log(f"Calling {url}")
    # your existing code - zero modifications needed

def run_parallel_checks():
    with LoggingThreads(grouped_log=True) as lt:
        lt.create_thread("Worker-1", my_worker, "https://api1.example.com")
        lt.create_thread("Worker-2", my_worker, "https://api2.example.com")
    # after the block: all threads joined, all logs replayed correctly
```

Code inside `my_worker` needs **zero modifications** - it doesn't know it's running in a thread.

### What you get in `log.html`

With `grouped_log=True`, each thread's logs appear in a dedicated collapsible section:

```
▼ Thread Worker-1 Logs
    INFO   Calling https://api1.example.com
    INFO   Status: 200
▼ Thread Worker-2 Logs
    INFO   Calling https://api2.example.com
    INFO   Status: 200
```

Timestamps are the originals - captured at the moment each log was emitted inside the thread.

---

# Part 2 - The Benchmark

## The Task

The same problem - thread-safe logging in Robot Framework - was given to **5 AI models** as a coding challenge. The full task specification (11 requirements) is in [`ai_benchmark/task.txt`](ai_benchmark/task.txt).

**Hard rules that acted as eliminators:**

| Rule | What it means |
|---|---|
| **R8 Zero-Interference** | Thread code must NOT be modified - it can't know it's inside a thread |
| **R9 Reversibility** | All RF internals must be restored right after threads finish, not at suite end |
| **R10 Structure Fidelity** | `FOR`/`IF`/`TRY-EXCEPT` must appear as native XML tags in `output.xml` |

## Results at a Glance

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  🥇  logging_threads.py  (human solution)                          │
│                                                                     │
│      Only solution satisfying R8 + R9 + R10 simultaneously.        │
│      280 lines. No threading module patching.                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

  🥈  Sonnet4.6     - solid, 22/22 tests on first try, but breaks R8
  🥉  Gemini3.1 Pro - shortest AI solution (103 lines), no threading patch,
                      but no context manager + debug prints in prod
  4th  Opus4.7      - needs `with thread_for():` inside thread → R8 ❌
  5th  GPT5.4       - patches threading.Thread globally, restore at suite end → R9 ❌
  6th  Opus4.6      - 723 lines, time.sleep() as sync (race condition), R8 ❌
```

| Criterion | **`logging_threads`** | `Gemini3.1 Pro` | `Sonnet4.6` | `Opus4.6` | `Opus4.7` | `GPT5.4` |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Zero-Interference** (R8) | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| **Reversibility** (R9) | ✅ | ⚠️ | ✅ | ✅ | ✅ | ❌ |
| **Structure Fidelity** (R10) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **No `threading` module patch** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **No `EXECUTION_CONTEXTS` patch** | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| **RF Listeners receive events** | ✅ | ✅ | ❌ | ❌ | ⚠️ | ❌ |
| **Context manager API** | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| **Lines of code** | **280** | 103 | 479 | 723 | 783 | 589 |
| **Requirements met** | **10/11** | 6/11 | 7/11 | 5/11 | 8/11 | 7/11 |

## Why the human solution won

The winning approach does one thing: **registers itself as a proper RF logger via the official `LOGGER.register_logger()` API**, buffers thread events using `functools.partial`, then replays them after all threads finish.

```python
# During thread execution - events are captured as ready-to-call closures:
self.add_logger_func_to_thread_message(
    partial(LOGGER.start_keyword, data, result)  # frozen callable
)

# After threads finish - replay is trivial:
for logger_func in thread_messages:
    logger_func()  # same reference, same object, correct context
```

What this buys:
- **Timestamps are original** - RF captured them inside the thread at emission time
- **RF Listeners work** - replay goes through `LOGGER`, so Allure and custom listeners get all events
- **Reversible by design** - `unregister_logger()` is one call, guaranteed by `__exit__`
- **No threading module touch** - Python's `threading.Thread` is completely untouched

The AI models, lacking deep intuition for RF's architecture, reached for brute-force, heavier tools: cloning entire `_ExecutionContext` internal objects, monkey-patching Python's global `threading.Thread.start`, and building fragile manual XML dispatchers with 15+ `isinstance` checks. 

**The takeaway:** A human found a 280-line API-compliant bypass. The LLMs generated up to nearly 800 lines of highly risky, unmaintainable internal patches.

## Full Analysis

The detailed per-model analysis with architecture diagrams, code snippets and scoring is in:

📄 **[ai_benchmark/README.md](ai_benchmark/README.md)** ← full technical comparison

Individual model solutions and their self-assessment reports are located in their respective subdirectories within [`ai_benchmark/`](ai_benchmark/).

Benchmark artifacts (`log.html`, `report.html`, `output.xml`) are intentionally versioned in `ai_benchmark/` as reproducibility evidence.

## My Final Comment

Most of the AI models produced significantly more code than necessary. Their solutions were overly complex, highlighting that LLMs do not inherently optimize for human-readability and long-term codebase maintenance. For example, if you look closely at the solution from Opus 4.7 (currently one of the strongest models), attempting to modify it in the future-such as ensuring compatibility with a newer Robot Framework version-would be an unpleasant and time-consuming task. You would probably resort to using an AI model to fix it, creating a vicious cycle that ultimately distances you from understanding your own codebase.

Interestingly, **Gemini 3.1 Pro** was the notable exception. It crafted a rather neat and concise solution that I would personally pick as the closest runner-up (though I genuinely wonder if it had seen my approaches in its training data!).

Ultimately, I believe **every model tested can serve as a highly effective AI coding assistant** for this type of problem. They all correctly identified the core issue and pointed out that monkey patching was required, validating their utility in the implementation process. However, **none of them independently produced a production-ready solution out of the box** without requiring human modification and architectural intervention.