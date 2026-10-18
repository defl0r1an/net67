"""Выход будит потоки, которые спят на своих событиях, и не ждёт их до таймаута.

18 октября 2026 каждый выход стоял две секунды: наблюдатель папки
пресетов спит в WaitForMultipleObjects, монитор winws — на threading.Event
между проверками, и общая команда выхода (requestInterruption и quit) ни
до одного не доходила. Сторож писал «Интерфейс не отвечает 2.2с».
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication  # noqa: E402

from main.process_exit import stop_running_qt_threads  # noqa: E402

#: Сколько можно ждать проснувшийся поток. С запасом на медленную машину,
#: но втрое меньше прежних двух секунд — разница видна сразу.
WAKE_BUDGET_S = 0.6


def _app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


def _wait_running(thread, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not thread.isRunning() and time.monotonic() < deadline:
        time.sleep(0.01)


class ExitWakesSleepingThreadsTests(unittest.TestCase):
    def _drain(self, thread) -> tuple[float, list]:
        _wait_running(thread)
        # Поток должен успеть уснуть, иначе проверяем не то.
        time.sleep(0.2)
        started = time.monotonic()
        unfinished = stop_running_qt_threads(2000)
        return time.monotonic() - started, unfinished

    def test_process_monitor_wakes_from_its_pause(self) -> None:
        from winws_runtime.monitoring.process_monitor import ProcessMonitorThread
        from winws_runtime.runtime.process_probe import WinwsProcessScan

        _app()
        thread = ProcessMonitorThread(interval_ms=60_000)
        self.addCleanup(thread.wait, 3000)
        with patch.object(
            ProcessMonitorThread,
            "_scan_processes_fast",
            lambda _self: WinwsProcessScan(canonical_pids={}, foreign_paths={}),
        ):
            thread.start()
            elapsed, unfinished = self._drain(thread)

        self.assertNotIn(thread, unfinished)
        self.assertLess(elapsed, WAKE_BUDGET_S)

    @unittest.skipUnless(sys.platform == "win32", "наблюдатель папки — WinAPI")
    def test_presets_dir_watcher_wakes_from_wait(self) -> None:
        from presets.native_dir_watcher import NativePresetsDirWatcher

        _app()
        folder = tempfile.mkdtemp(prefix="net67-watch-")
        thread = NativePresetsDirWatcher(folder)
        self.addCleanup(thread.wait, 3000)
        self.assertTrue(thread.start_watching())

        elapsed, unfinished = self._drain(thread)

        self.assertNotIn(thread, unfinished)
        self.assertLess(elapsed, WAKE_BUDGET_S)


if __name__ == "__main__":
    unittest.main()
