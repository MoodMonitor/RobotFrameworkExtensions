# ThreadLogger for Robot Framework 7.4

Runtime-reversible library that captures logs and structured keyword
events produced by Python threads inside a Robot Framework test so that
they appear, grouped per thread, in `output.xml` / `log.html`.

## Layout

```
solution/ThreadLogger.py          - the library itself
tests/demo_library.py             - demo RF library that reproduces the bug and shows the fix
tests/reversibility_checks.py     - checks that monkey-patches are gone after use
tests/01_baseline_problem.robot   - reproduces the vanilla RF problem
tests/02_solution.robot           - demonstrates correct logging with the library
tests/03_stress_and_reversibility.robot
                                  - stress test + patch-removal check
tests/verify_output.py            - structural verifier for output.xml
results/                          - artifacts produced by the runs
AI_REPORT.md                      - technical report
```

## Running

```powershell
py -3 -m venv .venv
.\.venv\Scripts\pip install robotframework==7.4.0

# reproduce the problem
.\.venv\Scripts\python -m robot --pythonpath tests --pythonpath solution `
    --outputdir results/baseline tests/01_baseline_problem.robot

# run the solution tests
.\.venv\Scripts\python -m robot --pythonpath tests --pythonpath solution `
    --outputdir results/solution tests/02_solution.robot

# full suite
.\.venv\Scripts\python -m robot --pythonpath tests --pythonpath solution `
    --outputdir results/all tests

# structural verification
.\.venv\Scripts\python tests/verify_output.py results/all/output.xml
```

## Public API (from a test library)

```python
from ThreadLogger import ThreadLogger, thread_for, thread_if, thread_try, run_keyword

tl = ThreadLogger()
tl.start_thread("worker-1", "PYTHON", "my_pkg.my_module:do_work", 42)
tl.wait_all_threads()
```

See `AI_REPORT.md` for full details.
