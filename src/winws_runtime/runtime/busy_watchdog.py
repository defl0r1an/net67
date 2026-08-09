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

_WORKER_THREAD_ATTRS = ("_dpi_start_thread", "_dpi_stop_thread")


def _has_live_worker(runtime_owner) -> bool:
    for attr in _WORKER_THREAD_ATTRS:
        thread = getattr(runtime_owner, attr, None)
        if thread is None:
            continue
        try:
            if thread.isRunning():
                return True
        except Exception:
            # Объект уже удалён Qt — считаем, что потока нет.
            continue
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
