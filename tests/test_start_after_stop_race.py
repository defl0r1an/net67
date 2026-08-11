"""Выключить обход и сразу включить обратно.

Жалоба: «если просто включить, выключить и попытаться включить обратно»
— появляется «Обход не запустился за 40 секунд».

Причина в асимметрии проверок. Перед запуском смотрели, не идёт ли уже
запуск. Перед остановкой — не идёт ли уже остановка. А вот друг про
друга они не знали ничего.

Поэтому нажатие «включить» сразу после «выключить» отправляло поток
запуска работать бок о бок с потоком остановки. Дальше как повезёт:
остановка снимала winws, который запуск только что поднял. Оркестратор
сорок секунд ждал процесс и не находил ни одного — формально запуск
прошёл, фактически его убили свои же.

Вторая половина беды: отказ в запуске терялся по дороге. `start_dpi_async`
ничего не возвращала, а обёртка над ней всё равно отвечала True. Значит
даже честный отказ выглядел как «запуск принят», и ждать всё равно
приходилось все сорок секунд.

Здесь закреплено и то, и другое.
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _Thread:
    def __init__(self, running: bool) -> None:
        self._running = bool(running)

    def isRunning(self) -> bool:  # noqa: N802 (Qt API)
        return self._running


class _DeletedThread:
    """Поток, чей C++-объект уже удалён.

    PyQt в этом случае бросает RuntimeError из любого метода. Проверка
    обязана считать такой поток остановленным, а не падать.
    """

    def isRunning(self) -> bool:  # noqa: N802 (Qt API)
        raise RuntimeError("wrapped C/C++ object has been deleted")


class _Owner:
    def __init__(self, stop_thread=None) -> None:
        self._dpi_stop_thread = stop_thread


class StopDetectionTests(unittest.TestCase):
    def _flow(self):
        from winws_runtime.runtime import start_flow

        return start_flow

    def test_running_stop_is_noticed(self) -> None:
        flow = self._flow()

        self.assertTrue(flow._stop_in_progress(_Owner(_Thread(running=True))))

    def test_finished_stop_does_not_block_start(self) -> None:
        flow = self._flow()

        self.assertFalse(flow._stop_in_progress(_Owner(_Thread(running=False))))

    def test_no_stop_thread_at_all(self) -> None:
        flow = self._flow()

        self.assertFalse(flow._stop_in_progress(_Owner(None)))

    def test_deleted_thread_is_not_a_crash(self) -> None:
        flow = self._flow()
        owner = _Owner(_DeletedThread())

        self.assertFalse(flow._stop_in_progress(owner))
        # И ссылку на мёртвый объект надо сбросить, иначе каждая
        # следующая проверка снова ловит исключение.
        self.assertIsNone(owner._dpi_stop_thread)


class WiringTests(unittest.TestCase):
    def test_start_waits_for_a_running_stop(self) -> None:
        from winws_runtime.runtime import start_flow

        source = inspect.getsource(start_flow.start_dpi_async)

        self.assertIn("_stop_in_progress(runtime_owner)", source)
        self.assertIn("_defer_start_until_stop_finishes", source)

    def test_the_check_happens_before_anything_else(self) -> None:
        """Иначе окно успевало переключиться на «запускаем» впустую."""
        from winws_runtime.runtime import start_flow

        source = inspect.getsource(start_flow.start_dpi_async)

        self.assertLess(
            source.index("_stop_in_progress(runtime_owner)"),
            source.index("prepare_start_preflight("),
        )

    def test_waiting_has_a_limit(self) -> None:
        """Застрявшая остановка не должна отменять запуск навсегда."""
        from winws_runtime.runtime.start_flow import (
            STOP_WAIT_RETRY_MS,
            STOP_WAIT_TIMEOUT_MS,
        )

        self.assertGreater(STOP_WAIT_TIMEOUT_MS, 0)
        self.assertGreater(STOP_WAIT_TIMEOUT_MS, STOP_WAIT_RETRY_MS)

    def test_timeout_forces_the_start(self) -> None:
        from winws_runtime.runtime import start_flow

        source = inspect.getsource(start_flow._defer_start_until_stop_finishes)

        self.assertIn("_force_after_stop_wait=True", source)

    def test_retry_is_scheduled_in_the_main_thread(self) -> None:
        """Запуск приходит и из рабочего потока, где цикла событий нет.

        Голый QTimer.singleShot завёл бы таймер там же — и отложенный
        запуск не случился бы никогда.
        """
        from winws_runtime.runtime import start_flow

        source = inspect.getsource(start_flow._defer_start_until_stop_finishes)
        helper = inspect.getsource(start_flow._schedule_in_main_thread)

        self.assertIn("_schedule_in_main_thread", source)
        self.assertIn("QCoreApplication.instance()", helper)
        # Таймер привязан к объекту приложения, иначе привязки нет вовсе.
        self.assertIn("QTimer.singleShot(int(delay_ms), app, callback)", helper)


class RefusalIsReportedTests(unittest.TestCase):
    """Отказ должен доходить до вызывающего, а не теряться."""

    def test_start_flow_returns_a_verdict(self) -> None:
        from winws_runtime.runtime import start_flow

        signature = inspect.signature(start_flow.start_dpi_async)

        self.assertEqual(signature.return_annotation, "bool")

    def test_runtime_command_passes_the_verdict_through(self) -> None:
        from winws_runtime.runtime import commands

        source = inspect.getsource(commands.start_dpi_async)

        self.assertIn("return bool(", source)
        self.assertIn("runtime_owner.start_dpi_async(", source)

    def test_launch_runtime_passes_the_verdict_through(self) -> None:
        from winws_runtime.runtime.launch_runtime import PresetLaunchRuntime

        source = inspect.getsource(PresetLaunchRuntime.start_dpi_async)

        self.assertIn("return bool(", source)

    def test_deferred_start_counts_as_accepted(self) -> None:
        """Отложенный запуск всё равно случится — это не отказ."""
        from winws_runtime.runtime import start_flow

        source = inspect.getsource(start_flow.start_dpi_async)
        deferred = source[source.index("_defer_start_until_stop_finishes") :]

        self.assertIn("return True", deferred[: deferred.index("prepare_start_preflight")])


if __name__ == "__main__":
    unittest.main()
