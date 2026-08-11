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


def prepare_window_for_show(window) -> None:
    """Доводит окно до готовности к показу, пока его ещё нет на экране.

    Раскладка, стили и размеры считаются здесь — у скрытого окна. Иначе
    Qt посчитает их уже после того, как Windows создаст окно на экране, и
    первый кадр достанется не тому размеру.
    """
    try:
        window.ensurePolished()
    except Exception:
        pass
    try:
        layout = window.layout()
        if layout is not None:
            layout.activate()
    except Exception:
        pass

    # Развёрнутое состояние — тоже до показа, а не в showEvent.
    #
    # Иначе окно выходит на экран в сохранённом размере и следующим
    # кадром прыгает на весь экран. Пока показ был прозрачным, прыжок
    # прятался; без прозрачности он стал бы вторым мельканием вместо
    # исправленного первого.
    try:
        geometry_runtime = getattr(window, "window_geometry_runtime", None)
        applied = getattr(geometry_runtime, "apply_pending_maximized_before_show", None)
        if callable(applied):
            applied()
    except Exception as exc:
        log(f"Не удалось развернуть окно до показа: {exc}", "DEBUG")


def show_initial_window_if_needed(window) -> None:
    """Показывает главное окно. Вызывается только с готовым интерфейсом.

    ## Почему не раньше

    Раньше окно показывалось первым, а интерфейс строился «после первого
    кадра» — ради ощущения быстрого запуска. Ощущение выходило обратное.

    Windows создаёт окно и закрашивает его фоном оконного класса задолго
    до того, как Qt успеет что-то нарисовать. Пока размер и раскладка не
    посчитаны, окно получает размер по умолчанию — и на экран на долю
    секунды выскакивает маленький чёрный прямоугольник без заголовка и
    кнопок. Это и есть то самое «маленькое чёрное окно при запуске».

    Прозрачностью это не лечится, и я потратил на попытку целый заход:
    setWindowOpacity(0) применяется к уже созданному окну, а первый кадр
    Windows рисует до того. Лечится только порядком: окна не должно
    существовать, пока показывать нечего.

    Стоимость нулевая: показ всё равно происходил после сборки — раньше
    через снятие прозрачности, теперь напрямую.
    """
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
    prepare_window_for_show(window)
    try:
        window.setWindowOpacity(1.0)
    except Exception:
        pass
    window.show()
    emit_startup_metric(
        "StartupWindowInitShowCall",
        f"{(_time.perf_counter() - t_show) * 1000:.0f}ms",
    )
    log("Основное окно показано с готовым интерфейсом", "DEBUG")


def start_window_deferred_init(window) -> None:
    window.deferred_init_requested.emit()


__all__ = [
    "connect_window_startup_signals",
    "is_first_run_wizard_pending",
    "show_initial_window_if_needed",
    "start_window_deferred_init",
]
