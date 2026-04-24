← [Back to root README](../README.md)

---

# 🤖 AI vs RF Internals: The Thread Logging Benchmark

> A deep dive into how 5 state-of-the-art AI models (GPT, Claude, Gemini) tackled a highly specific architectural problem in Robot Framework.
> Full technical comparison of the human solution (`logging_threads.py`) against the AI models.  
> Quick summary & English root README → [../README.md](../README.md)

---

## 📌 Task Context

Robot Framework by default **silently blocks all logging from background threads**. Bypassing this is notoriously difficult because it requires interacting with deeply nested, fully undocumented RF internals (`EXECUTION_CONTEXTS`, `librarylogger`, `LOGGER`).

The task required the models to solve this architectural puzzle while maintaining strict rules:

| # | Requirement | Short |
|---|---|---|
| 8 | Must not force the user to modify code inside the thread | **Zero-Interference** |
| 9 | Interference operates **only** during thread execution, then fully restored | **Reversibility** |
| 10 | FOR/IF/TRY structures preserved as native tags in output.xml | **Structure Fidelity** |
| 11 | Forbid editing RF source files | **No RF edits** |

Full task description: [`task.txt`](task.txt)

---

## 🔬 Winning Solution - `logging_threads.py`

> **280 lines · 3 classes · context manager API**

### How it works

```python
with LoggingThreads(grouped_log=True) as lt:
    lt.create_thread("Worker-1", my_function, arg1, arg2)
    lt.create_thread("Worker-2", other_function)
# ← after block exit: join, cleanup, replay logs
```

### Lifecycle in 3 stages

```text
┌─ __enter__ ────────────────────────────────────────────┐
│  1. hijack_loggers()   → remember _output_file,        │
│                          _syslog, _console             │
│  2. unregister_loggers() → _output_file = DumpOutputFile│
│                            (blocks XML), remove rest   │
│  3. register_logger(LoggersManager)                    │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌─ thread lifetime ──────────────────────────────────────┐
│  LoggersManager.manage_loggers() routes every event    │
│                                                        │
│  main thread?  →  to original loggers (live)           │
│  worker thread? → partial(LOGGER.method, *args)        │
│                   saved to thread_messages[name]       │
│                                                        │
│  LOGGING_THREADS.append(thread_name) - RF unblocks     │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌─ __exit__ ─────────────────────────────────────────────┐
│  1. thread.join() for each thread                      │
│  2. LOGGER.unregister_logger(loggers_manager)          │
│  3. LOGGING_THREADS.remove(thread_name)                │
│  4. register_loggers() → restore originals             │
│  5. log_all_threads_messages() → replay partial() calls│
└────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Why |
|---|---|
| `DumpOutputFile` instead of `None` | RF throws an exception when `_output_file is None` |
| `functools.partial` as deferred calls | Replayed through current LOGGER state - listeners get events correctly |
| `LOGGER.register_logger()` (not monkey-patch) | Official RF API - easily reversible via `unregister_logger()` |
| `LOGGING_THREADS.append()` | Single line bypasses RF block without patching internals |
| `grouped_log` option | `ResultKeyword` wraps thread logs - collapsible section in log.html |

---

## 🤖 Models Analysis

---

### `Gemini3.1 Pro` - ThreadInterceptorLibrary

> **103 lines · monkey-patch LOGGER methods via setattr · no context manager**

**Mechanism:** Direct monkey-patch via `setattr` on 35 methods of the `LOGGER` singleton. Replay triggered manually by `stop_and_replay_thread_logs()` - no `threading.Thread` patches at all. Clever trick for LOGGING_THREADS:

```python
class AllThreadsList:
    def __contains__(self, item):
        return True   # RF never blocks any thread
```

**Strengths:**
- `AllThreadsList` - elegant trick, one-line RF block bypass without append/remove
- Meets Zero-Interference (no changes required in thread function)
- Untouched `threading.Thread` and `EXECUTION_CONTEXTS` - minimal interference outside LOGGER
- Shortest code of all solutions (103 lines)

**Weaknesses:**
- ❌ No `finally` upon restore → exception between start and stop = permanent patch leak
- ❌ No context manager - `start_thread_interception()` / `stop_and_replay_thread_logs()` called manually
- ❌ `setattr` on LOGGER singleton instance instead of `register_logger()` - less safe for multiple uses
- ❌ **Debug artifact in production code:** `print(f"INTERCEPTED {name}...", file=sys.stderr)` inside every wrapper - clutters stderr during tests

---

### `Sonnet4.6` - ThreadLogger

> **479 lines · thread-local proxy · visitor pattern replay**

**Mechanism:** `_ThreadLocalList` - proxy for `LOGGER._log_message_parents` and `context.steps`, where each thread sees its own isolated list. `_SuppressingOutputProxy` blocks XML writes for worker threads. Replay via `wrapper.visit(xml_logger)`.

```python
# Thread-local proxy for LOGGER parent list:
class _ThreadLocalList:
    def _current(self):
        tid = threading.current_thread().ident
        if tid == self._main_id:
            return self._main      # main thread - original list
        return self._stacks.get(tid, self._main)  # worker thread - own list
```

**Strengths:**
- `_ThreadLocalList` - elegant isolation without patching `librarylogger.write`
- `wrapper.visit(xml_logger)` - cleanly handled replay via visitor pattern
- Thread-safe via RLock on stacks
- **22/22 tests passed without any corrections in the first iteration** - the only model without iterations

**Weaknesses:**
- ❌ **Violates Zero-Interference (Requirement 8)** - the user must call `run_keywords_in_parallel([kw, arg1])`, cannot use a standard `Thread`
- ⚠️ 479 lines - almost 2× more than the winning solution for a similar result
- ⚠️ Patches `context.steps` and `context.user_keywords` - fragile upon RF API changes

---

### `Opus4.6` - thread_executor

> **723 lines · full ExecutionContext per thread · complete ThreadOutput**

**Mechanism:** Creates a new `_ExecutionContext` per thread with a separate `ThreadOutput`. Monkey-patch `librarylogger.write`, `LOGGER.log_message`, and `EXECUTION_CONTEXTS.current`. Replay via `root.visit(xml_logger)`.

```python
# Full isolation - each thread has its own context:
t_ctx = _ExecutionContext(
    suite=suite, namespace=namespace,
    output=ThreadOutput(thread_name),  # completely isolated output
    ...
)
```

**Strengths:**
- Best isolation - `ThreadOutput` with a complete push/pop stack
- `root.visit(xml_logger)` - clean replay

**Weaknesses:**
- ❌ **Violates Zero-Interference** - `Run In Threads    worker1=${func1}` - different API than a standard Thread
- ❌ `time.sleep(0.01)` for synchronization after `thread.start()` - **classic race condition**
- ❌ 723 lines - almost 3× more than the winning solution
- ⚠️ Creating a full `_ExecutionContext` - risk of conflicts with RF internals

---

### `Opus4.7` - ThreadLogger (advanced)

> **783 lines · minimal patch + rich auxiliary API**

**Mechanism:** Patches only `librarylogger.write`. Per-thread `_ThreadRecord` with an independent `parents` stack. Auxiliary context managers: `thread_for`, `thread_if`, `thread_try`, `run_keyword`. Replay via recursive `_replay_tree()`.

```python
# Only one thing is patched:
_librarylogger.write = self._thread_aware_write
# ← reverted by _PATCHER.deactivate() upon completion
```

**Strengths:**
- Minimal patching (only `librarylogger.write`) - least intrusive of all models
- `thread_for`, `thread_if`, `thread_try` - rich API for building thread log structures
- Clear documentation and architecture
- `_Patcher` with active thread counter - patch active only when needed

**Weaknesses:**
- ❌ **Violates Zero-Interference (Requirement 8)** - the thread MUST use `with thread_for():`, `with thread_if():`
- ⚠️ 783 lines - the largest solution
- ⚠️ `_replay_tree` utilizes LOGGER - listeners see events twice (once inside the thread via patch, once upon replay)

---

### `GPT5.4` - RobotThreadCapture

> **589 lines · global Thread.start/join patch · singleton manager**

**Mechanism:** Patches `threading.Thread.start` and `threading.Thread.join` globally. A singleton `RobotThreadCaptureManager` automatically captures **every** thread after `Enable Thread Logging Capture`. Manual `_write_body_item()` instead of a visitor.

```python
# Automatic capture - zero changes to thread code:
def patched_start(thread, *args, **kwargs):
    manager._prepare_thread(thread)   # wraps thread.run before start
    return manager._orig_thread_start(thread, *args, **kwargs)
threading.Thread.start = patched_start
```

**Strengths:**
- ✅ Best implementation of Zero-Interference - **literally zero changes** to the thread code

**Weaknesses:**
- ❌ **Violates Reversibility (Requirement 9)** - `_restore_patches` is called in `Output.close` (end of suite), not after thread completion. Throughout the suite - `Thread.start/.join` are globally patched
- ❌ Singleton `_instance` - impossible to reset between tests
- ❌ `_write_body_item()` uses 15 `isinstance` checks instead of visitor pattern - incomplete, misses new RF node types
- ⚠️ Global `Thread.start` patch affects **all** threads - Selenium, requests, any external library

---

## 📊 Comparison Table

| Criterion | **Yours (Human)** | `Gemini3.1 Pro` | `Sonnet4.6` | `Opus4.6` | `Opus4.7` | `GPT5.4` |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Zero-Interference** (req 8) | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| **Reversibility** (req 9) | ✅ | ⚠️ | ✅ | ✅ | ✅ | ❌ |
| **FOR/IF/TRY preserved** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Thread-safety** | ✅ Lock | ⚠️ | ✅ RLock | ⚠️ | ✅ RLock | ✅ |
| **Simplicity & Readability** | ✅✅ | ✅ | ⚠️ | ❌ | ❌ | ⚠️ |
| **Ease of rollback** | ✅✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| **No global Thread patch** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **No EXECUTION_CONTEXTS patch**| ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| **RF Listeners see events** | ✅ | ✅ | ❌ | ❌ | ⚠️ | ❌ |
| **Size (lines)** | **280** | 103 | 479 | 723 | 783 | 589 |

---

## 🏆 Ranking

### 🥇 1st Place - `logging_threads.py`

> The only solution satisfying **both** Zero-Interference and Reversibility simultaneously. The smallest viable solution. Context manager guarantees cleanup even on exceptions. `functools.partial` for replay is elegant and idiomatic Python.

**Requirements score: 10/11**

---

### 🥈 2nd Place - `Sonnet4.6`

> Professional, 22/22 tests passed in the 1st iteration (no fixes necessary!), solid documentation. Visitor pattern replay is the cleanest among AI models. Weaknesses: deeper patching into internal RF lists, no listener support, violates Zero-Interference.

**Requirements score: 7/11**

---

### 🥉 3rd Place - `Gemini3.1 Pro`

> The shortest code of all (103 lines). Untouched `threading.Thread` and `EXECUTION_CONTEXTS`. `AllThreadsList` is the most elegant trick presented. Unfortunately: lacks `finally`, lacks context manager, and leaves debug `print` in every production wrapper.

**Requirements score: 6/11**

---

### 4th Place - `Opus4.7`

> Minimal patch, best documentation, rich auxiliary API (`thread_for/if/try`). Ideal if not for the Zero-Interference rule. Architecturally the most mature model - a pity it failed the interference requirement.

**Requirements score: 8/11** *(but disqualified by R8)*

---

### 5th Place - `GPT5.4`

> Best Zero-Interference implementation - absolutely transparent for thread code. However, the global `Thread.start/join` patch violates Reversibility and affects the entire Python runtime.

**Requirements score: 7/11** *(but disqualified by R9)*

---

### 6th Place - `Opus4.6`

> 723 lines featuring a race condition (`time.sleep`), violation of Zero-Interference, and the heaviest architecture. It offers the best theoretical isolation, but practically rebuilds the RF runner from scratch.

**Requirements score: 5/11**

---

## 💡 What makes the winning solution stand out

1. **`functools.partial` as an elegant event buffer/replay mechanism** - **None of the 5 AI models figured out this semantic trick.** Instead of parsing raw RF event data and writing complex XML node constructors (which the AIs attempted to do), the human solution simply freezes the logger event into a ready-to-call closure. Replay becomes a trivial `for func in events: func()`, automatically guaranteeing that all external RF listeners (like Allure) get exactly what they expect.

2. **`LOGGER.register_logger()` instead of a monkey-patch** - official RF API. `unregister_logger()` ensures guaranteed, one-line cleanup. None of the AI models used this mechanism as their primary tool.

3. **`DumpOutputFile` as a precise blocking proxy** - it uniquely blocks XML writes during thread execution without replacing the entire logging stack with a custom one.

4. **The only solution utilizing `grouped_log`** - providing an optional collapsible section per thread in `log.html` is a feature that none of the models implemented.

---

## 🔁 How to replicate the benchmark

1. Read the assignment: [`task.txt`](task.txt)
2. Submit the exact assignment to the desired AI model
3. Evaluate against criteria R8 / R9 / R10 and remaining requirements
4. Compare with the solutions located in the model directories.

Each model directory (e.g., `Gemini3.1Pro/`, `sonnet4.6/`) contains:
- The main script with the generated code
- The full test suite proving or disproving their solutions
- `AI_REPORT.md` - AI's actual self-assessment (diagnosis, decisions, iterations, evaluation), so you can read exactly how they reasoned about the undocumented internals.

---

## ✍️ Author's Note

My personal take on what these results mean for AI-assisted development — and why I think every model here still has real value despite the failures — is in:

📄 **[logging_threads/README.md → My Final Comment](../README.md#my-final-comment)**

---

← [Back to root README](../README.md)
