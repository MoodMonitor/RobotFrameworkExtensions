"""Quick helper - prints per-thread message timestamps from output.xml."""

import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results/all/output.xml")
tree = ET.parse(path)
root = tree.getroot()

for kw in root.iter("kw"):
    if kw.get("owner") != "ThreadLogger":
        continue
    name = kw.get("name", "")
    if not name.startswith("Thread 'worker-"):
        continue
    msgs = list(kw.iter("msg"))
    stamps = [datetime.fromisoformat(m.get("time")) for m in msgs if m.get("time")]
    monotonic = all(a <= b for a, b in zip(stamps, stamps[1:]))
    print(f"{name}: {len(stamps)} msgs, monotonic={monotonic}, "
          f"span={(stamps[-1]-stamps[0]).total_seconds():.4f}s"
          if len(stamps) >= 2 else f"{name}: {len(stamps)} msgs")
