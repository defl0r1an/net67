"""Включить → выключить → включить должно работать.

Признаком «идёт остановка» служил живой QThread. Но поток после
окончания работы досиживает в своём цикле событий, пока до него не
дойдёт quit(), и isRunning() всё это время возвращает True. Работник же
обнуляется сразу, как только закончил.

Из-за этого запуск после остановки ждал двенадцать секунд, шёл напролом
и упирался в проверку, которая молча возвращала отказ. В журнале
оставалось «Остановка не завершилась за 12000 мс», дальше не
происходило ничего, а окно писало «Обход не запустился за 40 секунд».
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _Thread:
    def __init__(self, running: bool) -> None:
        self._running = running

    def isRunning(self) -> bool:  # noqa: N802 (совместимость с QThread)
        return self._running


class _Owner:
    def __init__(self, worker, thread) -> None:
        self._dpi_stop_worker = worker
        self._dpi_stop_thread = thread


class StopInProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        import winws_runtime.runtime.start_flow as start_flow

        self.start_flow = start_flow

    def test_running_worker_means_stop_is_in_progress(self) -> None:
        owner = _Owner("worker", _Thread(True))

        self.assertTrue(self.start_flow._stop_in_progress(owner))

    def test_finished_worker_frees_the_start_even_if_thread_lingers(self) -> None:
        # Ровно тот случай, что ломал повторное включение.
        owner = _Owner(None, _Thread(True))

        self.assertFalse(self.start_flow._stop_in_progress(owner))

    def test_dead_thread_reference_is_dropped(self) -> None:
        owner = _Owner(None, _Thread(False))

        self.assertFalse(self.start_flow._stop_in_progress(owner))
        self.assertIsNone(owner._dpi_stop_thread)

    def test_nothing_running_is_not_a_stop(self) -> None:
        owner = _Owner(None, None)

        self.assertFalse(self.start_flow._stop_in_progress(owner))


class WorkerSlotReleaseTests(unittest.TestCase):
    """Ссылка на работника снимается в обработчике завершения.

    Раньше её снимала цепочка сигналов: finished работника → очистка →
    quit() потока → finished потока → сброс ссылки. На живой машине
    цепочка рвалась, ссылки оставались, и приложение считало запуск и
    остановку идущими вечно. В журнале рядом стояли «DPI успешно
    остановлен» и «Остановка не завершилась за 12000 мс» — они говорили
    о разном: о работе и о ссылке на поток, который её давно закончил.
    """

    def test_release_clears_the_slot(self) -> None:
        from winws_runtime.runtime.lifecycle_feedback import release_worker_slot

        owner = _Owner("worker", _Thread(True))

        release_worker_slot(owner, "_dpi_stop_worker")

        self.assertIsNone(owner._dpi_stop_worker)

    def test_start_is_free_after_release_even_with_live_thread(self) -> None:
        import winws_runtime.runtime.start_flow as start_flow
        from winws_runtime.runtime.lifecycle_feedback import release_worker_slot

        owner = _Owner("worker", _Thread(True))
        self.assertTrue(start_flow._stop_in_progress(owner))

        release_worker_slot(owner, "_dpi_stop_worker")

        self.assertFalse(start_flow._stop_in_progress(owner))

    def test_release_survives_a_broken_owner(self) -> None:
        # Сброс не имеет права уронить обработчик завершения: он в
        # finally, и исключение отсюда съело бы настоящую ошибку.
        from winws_runtime.runtime.lifecycle_feedback import release_worker_slot

        class Stubborn:
            def __setattr__(self, name, value):
                raise RuntimeError("нельзя")

        release_worker_slot(Stubborn(), "_dpi_stop_worker")


if __name__ == "__main__":
    unittest.main()
