"""Служебный поток, запущенный не из окна, обязан завершиться сам.

Главная кнопка включает и выключает обход из своего фонового потока. Для
остановки создаётся ещё один поток, и после работы ему должна прийти
команда «завершись». Команду ставила в очередь замыкание-обработчик, а
очередь эта — у потока, в котором обработчик подключали: у потока
кнопки. Тот к этому времени уже кончился, и команда не доходила никогда.

Поток остановки оставался «выполняющимся» навсегда, а остановка
проверяла именно это и молча выходила: «остановка уже идёт». Со стороны:
первый раз за сеанс обход выключается, дальше — нет, ни кругом, ни
меткой в заголовке; круг при этом писал «Обход выключен» при работающем
обходе. Так было и в 0.12.67.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


class _Worker(QObject):
    finished = pyqtSignal(bool, str)

    def run(self) -> None:
        self.finished.emit(True, "")


class _Owner(QObject):
    """Владелец потоков живёт в потоке окна, как настоящий."""

    def __init__(self) -> None:
        super().__init__()
        self._thread = None
        self._worker = None
        self.finished_calls = 0

    def on_finished(self, _ok, _message) -> None:
        self.finished_calls += 1


def _pump(app, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


class StartFromWorkerThreadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        from ui.ui_thread_guard import mark_gui_thread

        mark_gui_thread()

    def _start(self, owner: _Owner, *, from_other_thread: bool):
        from winws_runtime.runtime.thread_runtime import start_worker_thread

        holder: dict[str, object] = {}

        def _go() -> None:
            holder["thread"] = start_worker_thread(
                owner,
                thread_attr="_thread",
                worker_attr="_worker",
                worker=_Worker(),
                finished_slot=owner.on_finished,
            )

        if from_other_thread:
            caller = threading.Thread(target=_go)
            caller.start()
            caller.join()
        else:
            _go()
        return holder["thread"]

    def test_thread_started_from_a_background_thread_finishes(self) -> None:
        owner = _Owner()
        thread = self._start(owner, from_other_thread=True)
        _pump(self.app, 0.6)

        self.assertEqual(owner.finished_calls, 1)
        # Вот она, поломка: поток досиживал вечно, и вторая остановка
        # обхода считала, что первая ещё идёт.
        self.assertIsNone(owner._thread)
        self.assertIsNone(owner._worker)
        try:
            running = thread.isRunning()
        except RuntimeError:
            running = False  # уже удалён Qt — значит, завершился
        self.assertFalse(running)

    def test_second_run_from_a_background_thread_works_too(self) -> None:
        owner = _Owner()
        self._start(owner, from_other_thread=True)
        _pump(self.app, 0.6)
        self._start(owner, from_other_thread=True)
        _pump(self.app, 0.6)
        self.assertEqual(owner.finished_calls, 2)
        self.assertIsNone(owner._thread)

    def test_thread_started_from_the_window_thread_still_finishes(self) -> None:
        owner = _Owner()
        thread = self._start(owner, from_other_thread=False)
        _pump(self.app, 0.6)
        self.assertEqual(owner.finished_calls, 1)
        self.assertIsNone(owner._thread)
        self.assertIsNone(owner._worker)
        try:
            running = thread.isRunning()
        except RuntimeError:
            running = False
        self.assertFalse(running)


if __name__ == "__main__":
    unittest.main()
