"""Deep inspection of results/solution/output.xml.

Validates:
    1. Messages from every worker thread are present.
    2. Each thread has its own <kw> subtree named Thread '<name>'.
    3. Nested structures survive: <for>, <iter>, <if>, <branch>, <try>.
    4. Message timestamps from the same thread are monotonically
       non-decreasing (original timestamps preserved).
    5. Messages of different threads do NOT mix under the same parent.
    6. Failing worker is flagged with status FAIL and traceback is present.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


def main(path: Path) -> int:
    tree = ET.parse(path)
    root = tree.getroot()

    errors: list[str] = []

    # ------------------------------------------------------------------
    # Locate every "Thread '<name>'" keyword
    # ------------------------------------------------------------------
    thread_kws: dict[str, ET.Element] = {}
    for kw in root.iter("kw"):
        name = kw.get("name", "")
        owner = kw.get("owner", "")
        if owner == "ThreadLogger" and name.startswith("Thread '"):
            thread_kws[name] = kw

    print(f"Found {len(thread_kws)} thread wrappers: {sorted(thread_kws)}")
    if not thread_kws:
        errors.append("No thread wrappers found in output.xml")

    # ------------------------------------------------------------------
    # 1) + 2) Content and grouping
    # ------------------------------------------------------------------
    per_thread_messages: dict[str, list[ET.Element]] = defaultdict(list)
    for name, kw in thread_kws.items():
        for m in kw.iter("msg"):
            per_thread_messages[name].append(m)

    for name in sorted(thread_kws):
        msgs = per_thread_messages[name]
        texts = [(m.text or "").strip() for m in msgs]
        print(f"  {name}: {len(msgs)} messages ->")
        for t in texts[:5]:
            print(f"     - {t!r}")
        if len(texts) > 5:
            print(f"     ... ({len(texts)-5} more)")

    # Check that baseline worker messages are present only as DIRECT
    # children of their own Thread '<name>' wrapper. (They may still be
    # observed when iterating recursively because the Thread wrapper
    # nests inside the parent kw - that is correct nesting, not a leak.)
    def _parent_map(tree_root: ET.Element) -> dict[ET.Element, ET.Element]:
        return {c: p for p in tree_root.iter() for c in p}

    pmap = _parent_map(root)
    for i in range(3):
        expected_prefix = f"[worker {i}]"
        leaks = []
        for m in root.iter("msg"):
            if not (m.text or "").startswith(expected_prefix):
                continue
            parent = pmap.get(m)
            # Valid if the direct parent is Thread 'worker-<i>' kw.
            if (
                parent is not None
                and parent.tag == "kw"
                and parent.get("owner") == "ThreadLogger"
                and parent.get("name", "").startswith(f"Thread 'worker-{i}'")
            ):
                continue
            leaks.append(f"under <{parent.tag if parent is not None else '?'}>"
                         f" {parent.get('name', '')}: {m.text!r}")
        if leaks:
            errors.append(
                f"Messages of worker {i} leaked outside its thread wrapper: {leaks}"
            )

    # ------------------------------------------------------------------
    # 3) Nested structures inside nested-1 thread
    # ------------------------------------------------------------------
    nested = thread_kws.get("Thread 'nested-1'")
    if nested is None:
        errors.append("nested-1 thread wrapper missing")
    else:
        tags_found = {child.tag for child in nested.iter()}
        required = {"group", "for", "iter", "if", "branch", "try"}
        missing = required - tags_found
        if missing:
            errors.append(
                f"nested-1 tree lost structural tags: missing {sorted(missing)}"
            )
        else:
            print(f"  nested-1 preserves structural tags: {sorted(required)}")

    # ------------------------------------------------------------------
    # 4) Timestamp monotonicity per thread
    # ------------------------------------------------------------------
    from datetime import datetime

    for name, msgs in per_thread_messages.items():
        prev = None
        for m in msgs:
            ts_str = m.get("time") or m.get("timestamp")
            if ts_str is None:
                continue
            ts = datetime.fromisoformat(ts_str.replace("Z", ""))
            if prev is not None and ts < prev:
                errors.append(
                    f"{name}: timestamp went backwards at {ts_str} (previous {prev})"
                )
            prev = ts

    # ------------------------------------------------------------------
    # 5) Verify no thread message ended up on MainThread's body directly
    # ------------------------------------------------------------------
    # Any direct <msg> child of the <test> element whose text matches a
    # worker pattern would prove a leak.
    for test in root.iter("test"):
        for m in list(test):
            if m.tag == "msg" and (m.text or "").startswith(("[worker", "[baseline worker")):
                errors.append(f"worker message leaked as test-level msg: {m.text!r}")

    # ------------------------------------------------------------------
    # 6) Failing worker marked FAIL
    # ------------------------------------------------------------------
    fail_kw = thread_kws.get("Thread 'parallel-fail'")
    if fail_kw is not None:
        status = fail_kw.find("status")
        if status is None or status.get("status") != "FAIL":
            errors.append("parallel-fail thread should have status FAIL")
        else:
            print(f"  parallel-fail thread correctly marked as FAIL")
        # traceback message must be present
        if not any("Traceback" in (m.text or "") for m in fail_kw.iter("msg")):
            errors.append("parallel-fail: traceback not attached to the thread log")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nAll structural assertions passed.")
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results/solution/output.xml")
    sys.exit(main(path))
