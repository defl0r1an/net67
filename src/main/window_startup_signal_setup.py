from __future__ import annotations

import time as _time

from log.log import log
from main.runtime_state import log_startup_metric as emit_startup_metric


def connect_window_startup_signals(window, *, continue_startup) -> None:
    window.deferred_init_requested.connect(window._deferred_init, window._queued_connection())
    window.continue_startup_requested.connect(continue_startup, window._queued_connection())
    window.finalize_ui_bootstrap_requested.connect(window._finalize_ui_bootstrap, window._queued_connection())


def is_first_run_wizard_pending() -> bool:
    """Нужен ли мастер первого запуска прямо сейчас.

    Сбой проверки трактуем как «не нужен»: иначе поломка в настройках
    оставила бы человека вообще без окна.
    """
    try:
        from wizard.apply import is_wizard_needed

        return bool(is_wizard_needed())
    except Exception:
        return False


def show_initial_window_if_needed(window) -> None:
    if window.start_in_tray or window.isVisible():
        return

    # На первом запуске окно не показываем вовсе: его покажет мастер,
    # когда закончит. Иначе человек видел, как окно выскакивает, секунду
    # висит и следом его накрывает мастер — а если успеть нажать на выбор
    # провайдера в этот промежуток, мастер закрывался вместе с нажатием.
    if is_first_run_wizard_pending():
        log("Первый запуск: окно откроется после мастера", "DEBUG")
        return

    t_show = _time.perf_counter()
    window.show()
    emit_startup_metric(
        "StartupWindowInitShowCall",
        f"{(_time.perf_counter() - t_show) * 1000:.0f}ms",
    )
    log("Основное окно показано (FluentWindow, init в фоне)", "DEBUG")


def start_window_deferred_init(window) -> None:
    window.deferred_init_requested.emit()


__all__ = [
    "connect_window_startup_signals",
    "is_first_run_wizard_pending",
    "show_initial_window_if_needed",
    "start_window_deferred_init",
]
