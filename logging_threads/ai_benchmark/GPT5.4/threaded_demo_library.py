from __future__ import annotations

import threading
import time

from robot.api import logger
from robot.api.deco import keyword, library
from robot.libraries.BuiltIn import BuiltIn


@library(scope="GLOBAL", auto_keywords=False)
class ThreadedDemoLibrary:
    @keyword("Log From Two Threads")
    def log_from_two_threads(self):
        ready = threading.Barrier(3)
        threads = [
            threading.Thread(
                target=self._log_worker,
                args=(f"worker-{index}", ready),
                name=f"worker-{index}",
            )
            for index in range(1, 3)
        ]
        logger.info("main-before-threads")
        for thread in threads:
            thread.start()
        ready.wait()
        logger.info("main-after-release")
        for thread in threads:
            thread.join()
        logger.info("main-after-join")

    def _log_worker(self, worker_name: str, ready: threading.Barrier):
        logger.info(f"{worker_name}-info-1")
        time.sleep(0.02)
        ready.wait()
        logger.info(f"{worker_name}-info-2")

    @keyword("Run Composite Keywords In Threads")
    def run_composite_keywords_in_threads(self):
        threads = [
            threading.Thread(
                target=self._run_composite_keyword,
                args=(index,),
                name=f"kw-thread-{index}",
            )
            for index in range(1, 3)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def _run_composite_keyword(self, index: int):
        BuiltIn().run_keyword("Worker Composite Keyword", index)

    @keyword("Run Failing Thread")
    def run_failing_thread(self):
        thread = threading.Thread(target=self._failing_worker, name="crash-thread")
        thread.start()
        thread.join()

    def _failing_worker(self):
        raise RuntimeError("boom-from-thread")
