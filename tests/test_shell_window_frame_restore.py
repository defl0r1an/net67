"""Выход из развёрнутого окна просит Windows пересчитать раму.

Обработчик раньше стоял в классе окна qfluentwidgets, который net67 не
создаёт, и потому не срабатывал ни разу. Тест держит его в настоящем окне.
"""

import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402


def _pump(seconds: float = 0.1) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()


class ShellWindowFrameRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_restore_from_maximized_recalculates_frame_once(self) -> None:
        from shell.app_window import AppShellWindow

        window = AppShellWindow()
        self.addCleanup(window.deleteLater)
        with mock.patch.object(AppShellWindow, "_recalculate_native_frame") as recalc:
            window.show()
            _pump()
            window.showMaximized()
            _pump()
            self.assertEqual(recalc.call_count, 0)
            window.showNormal()
            _pump()
            self.assertEqual(recalc.call_count, 1)


if __name__ == "__main__":
    unittest.main()
