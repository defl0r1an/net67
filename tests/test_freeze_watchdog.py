"""Сторож зависаний: замечает молчание главного потока и молчит сам.

Зависание — не падение: процесс жив, исключения нет, ловить обработчику
крашей нечего. Приложение переставало отвечать на BlockCheck и
диагностике, и в журнале оставалась тишина на двадцать шесть минут.
Эти проверки стерегут, что тишина больше не остаётся без следа — и что
сторож не поднимает тревогу на здоровом приложении.
"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class FreezeWatchdogTests(unittest.TestCase):
    def setUp(self) -> None:
        from PyQt6.QtCore import QCoreApplication

        self.app = QCoreApplication.instance() or QCoreApplication([])
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.folder = Path(self._dir.name)

        import log.freeze_watchdog as watchdog

        self.watchdog = watchdog
        # Порог занижен, иначе проверка длилась бы дольше минуты.
        self._threshold = watchdog.FREEZE_THRESHOLD_SECONDS
        watchdog.FREEZE_THRESHOLD_SECONDS = 2.0
        self.addCleanup(setattr, watchdog, "FREEZE_THRESHOLD_SECONDS", self._threshold)
        # Сторож ставится один раз на процесс; между проверками снимаем
        # признак, иначе второй тест получит установку от первого.
        watchdog._installed = False
        self.addCleanup(setattr, watchdog, "_installed", False)

    def _run_for(self, seconds: float, freeze_after: float | None, freeze_for: float) -> str:
        from PyQt6.QtCore import QTimer

        self.watchdog.install_freeze_watchdog(self.app, crash_folder=self.folder)

        if freeze_after is not None:
            QTimer.singleShot(int(freeze_after * 1000), lambda: time.sleep(freeze_for))

        QTimer.singleShot(int(seconds * 1000), self.app.quit)
        self.app.exec()

        path = self.folder / "freeze.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_stalled_main_thread_leaves_stack_in_log(self) -> None:
        text = self._run_for(seconds=9.0, freeze_after=1.5, freeze_for=5.0)

        self.assertIn("не отвечает", text)
        # Ради стека всё и затевалось: без него запись говорит «повисло»
        # и не говорит где.
        self.assertIn("Thread", text)

    def test_healthy_application_produces_no_alarm(self) -> None:
        text = self._run_for(seconds=6.0, freeze_after=1.0, freeze_for=0.3)

        self.assertNotIn("не отвечает", text)


if __name__ == "__main__":
    unittest.main()
