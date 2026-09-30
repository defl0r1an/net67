"""Страховка от навсегда зависшего признака «занято».

Запуск и остановка DPI помечают состояние как busy и снимают пометку в
обработчиках завершения рабочих потоков. Если обработчик не отработал —
поток умер, сигнал не дошёл, обработчик упал, — на странице навсегда
остаётся «Запуск net67...» или «Остановка net67...», а кнопки управления
заблокированы. Приложение в этот момент нельзя ни запустить, ни
остановить, только убить из диспетчера задач.

Сторож не чинит причину. Он проверяет простой факт: помечено «занято», а
ни одного живого рабочего потока нет. Такое состояние недостижимо при
нормальной работе, поэтому пометку можно снять и вернуть человеку
управление. Причина при этом остаётся в логе.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer

from log.log import log


#: Как часто проверять. Достаточно редко, чтобы не мешать, и достаточно
#: часто, чтобы человек не успел решить, что приложение зависло.
CHECK_INTERVAL_MS = 2_000

#: Сколько подряд проверок должны увидеть рассогласование. Одна проверка
#: может попасть в окно между установкой busy и стартом потока.
CONFIRMATIONS_BEFORE_RESET = 3

#: Работники запуска и остановки. Именно они, а не потоки.
#:
#: Поток после окончания работы досиживает в своём цикле событий, пока
#: до него не дойдёт quit(), и всё это время isRunning() возвращает
#: True. Сторож, смотревший на потоки, видел «работа идёт» там, где она
#: давно кончилась, и не снимал признак занятости — то есть не делал
#: ровно того, ради чего заведён.
#:
#: Работник обнуляется сразу в обработчике завершения (release_worker_slot
#: в lifecycle_feedback), поэтому по нему видно настоящее положение дел.
_WORKER_ATTRS = ("_dpi_start_worker", "_dpi_stop_worker")

#: Потоки смотрим следом: работник мог не появиться вовсе, если запуск
#: оборвался между созданием потока и стартом работника.
_WORKER_THREAD_ATTRS = ("_dpi_start_thread", "_dpi_stop_thread")


def _has_live_worker(runtime_owner) -> bool:
    for attr in _WORKER_ATTRS:
        if getattr(runtime_owner, attr, None) is not None:
            return True

    for attr in _WORKER_THREAD_ATTRS:
        thread = getattr(runtime_owner, attr, None)
        if thread is None:
            continue
        try:
            if not thread.isRunning():
                continue
        except Exception:
            # Объект уже удалён Qt — считаем, что потока нет.
            continue
        # Поток жив, а работника при нём нет: он либо ещё не стартовал,
        # либо уже отработал и досиживает. Первое — нормальная гонка,
        # второе — то самое зависание. Отличить их здесь нечем, поэтому
        # решает счётчик подтверждений: короткая гонка до него не
        # доживёт, а застрявшее состояние наберёт нужные три проверки.
        return False
    return False


def _is_busy(runtime_owner) -> bool:
    """Признак занятости живёт в общем состоянии интерфейса.

    LaunchRuntimeSnapshot его не содержит: set_busy пишет launch_busy в
    хранилище AppUiState, оттуда же его читает страница.
    """
    try:
        store = runtime_owner._runtime_service()._store()
        if store is None:
            return False
        return bool(getattr(store.snapshot(), "launch_busy", False))
    except Exception:
        return False


def install_busy_watchdog(runtime_owner, *, parent=None) -> QTimer | None:
    """Вешает периодическую проверку на владельца runtime."""
    if getattr(runtime_owner, "_busy_watchdog_timer", None) is not None:
        return runtime_owner._busy_watchdog_timer

    state = {"strikes": 0}

    def _check() -> None:
        if not _is_busy(runtime_owner):
            state["strikes"] = 0
            return

        if _has_live_worker(runtime_owner):
            state["strikes"] = 0
            return

        # «Занято» на время проверки стратегий ставит сама проверка, и
        # рабочих потоков запуска при этом нет по определению. Без этого
        # исключения сторож через шесть секунд возвращал кнопку «Включить»
        # посреди перебора.
        try:
            from winws_runtime.runtime.scan_guard import is_external_winws_scan_active

            if is_external_winws_scan_active():
                state["strikes"] = 0
                return
        except ImportError:
            pass

        state["strikes"] += 1
        if state["strikes"] < CONFIRMATIONS_BEFORE_RESET:
            return

        state["strikes"] = 0
        log(
            "Признак «занято» висит без единого рабочего потока — снимаю. "
            "Причину ищите выше по логу: обработчик завершения не отработал.",
            "⚠ WARNING",
        )
        try:
            runtime_owner._runtime_service().set_busy(False)
        except Exception as exc:
            log(f"Сторож не смог снять признак занятости: {exc}", "❌ ERROR")

    try:
        timer = QTimer(parent)
        timer.setInterval(CHECK_INTERVAL_MS)
        timer.timeout.connect(_check)
        timer.start()
    except Exception as exc:
        log(f"Не удалось запустить сторож занятости: {exc}", "DEBUG")
        return None

    runtime_owner._busy_watchdog_timer = timer
    return timer


__all__ = [
    "CHECK_INTERVAL_MS",
    "CONFIRMATIONS_BEFORE_RESET",
    "install_busy_watchdog",
]
