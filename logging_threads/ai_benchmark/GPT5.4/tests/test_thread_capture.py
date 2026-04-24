from __future__ import annotations

import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROBOT_DIR = ROOT / "tests" / "robot"
RUNS_DIR = ROOT / "test_runs"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _texts(element):
    values = []
    for item in element.iter():
        if item.text and item.text.strip():
            values.append(item.text.strip())
    return values


def _find_group(root, name: str):
    for group in root.iter("group"):
        if group.get("name") == name:
            return group
    return None


def _run_suite(suite_name: str) -> tuple[Path, subprocess.CompletedProcess[str]]:
    output_dir = RUNS_DIR / suite_name
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    command = [
        str(PYTHON),
        "-m",
        "robot.run",
        "--pythonpath",
        str(ROOT),
        "--outputdir",
        str(output_dir),
        "--output",
        "output.xml",
        "--log",
        "log.html",
        "--report",
        "report.html",
        str(ROBOT_DIR / f"{suite_name}.robot"),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return output_dir, completed


class RobotThreadCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RUNS_DIR.mkdir(exist_ok=True)
        if not PYTHON.exists():
            raise AssertionError(f"Missing test interpreter: {PYTHON}")

    def test_baseline_reproduces_missing_thread_logging(self):
        output_dir, completed = _run_suite("baseline")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

        root = ET.parse(output_dir / "output.xml").getroot()
        texts = _texts(root)

        self.assertNotIn("worker-1-info-1", texts)
        self.assertNotIn("worker-2-info-2", texts)
        self.assertIsNone(_find_group(root, "Thread worker-1"))
        self.assertIsNone(_find_group(root, "Thread kw-thread-1"))
        self.assertIn("main-before-threads", texts)

    def test_capture_groups_threads_and_preserves_keyword_structure(self):
        output_dir, completed = _run_suite("fixed")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

        root = ET.parse(output_dir / "output.xml").getroot()

        worker_1 = _find_group(root, "Thread worker-1")
        worker_2 = _find_group(root, "Thread worker-2")
        kw_thread = _find_group(root, "Thread kw-thread-1")
        crash_thread = _find_group(root, "Thread crash-thread")

        self.assertIsNotNone(worker_1)
        self.assertIsNotNone(worker_2)
        self.assertIsNotNone(kw_thread)
        self.assertIsNotNone(crash_thread)

        worker_1_texts = _texts(worker_1)
        worker_2_texts = _texts(worker_2)
        self.assertIn("worker-1-info-1", worker_1_texts)
        self.assertIn("worker-1-info-2", worker_1_texts)
        self.assertNotIn("worker-2-info-1", worker_1_texts)
        self.assertIn("worker-2-info-1", worker_2_texts)
        self.assertIn("worker-2-info-2", worker_2_texts)
        self.assertNotIn("main-before-threads", worker_1_texts)

        thread_messages = []
        for msg in root.iter("msg"):
            if msg.text and "worker-" in msg.text:
                thread_messages.append(msg)
        self.assertTrue(thread_messages)
        self.assertTrue(all(msg.get("time") for msg in thread_messages))

        kw_tags = {item.tag for item in kw_thread.iter()}
        self.assertIn("kw", kw_tags)
        self.assertIn("for", kw_tags)
        self.assertIn("if", kw_tags)
        self.assertIn("try", kw_tags)
        self.assertIn("iter", kw_tags)
        self.assertIn("branch", kw_tags)
        self.assertIn("try-1-boom", _texts(kw_thread))

        crash_status = crash_thread.find("status")
        self.assertIsNotNone(crash_status)
        self.assertEqual(crash_status.get("status"), "FAIL")
        self.assertIn("boom-from-thread", "".join(_texts(crash_thread)))

        log_html = (output_dir / "log.html").read_text(encoding="utf-8")
        self.assertIn("Thread worker-1", log_html)
        self.assertIn("worker-1-info-1", log_html)
        self.assertIn("Thread kw-thread-1", log_html)
        self.assertIn("Thread crash-thread", log_html)


if __name__ == "__main__":
    unittest.main()
