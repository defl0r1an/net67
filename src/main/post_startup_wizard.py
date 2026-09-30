"""Первый запуск: открыть окно для первичной настройки.

Отдельного окна мастера больше нет — его вопросы задаёт обучающий тур
(ui/onboarding/setup_choices.py). Здесь остаётся то, что нужно до тура:
применить умолчания hosts после установки и показать главное окно,
спрятанное на первом запуске, чтобы не мелькать пустым. Пока настройка не
пройдена (ui_state.wizard_completed), тур начинается в режиме настройки.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer

from log.log import log
from main.post_startup_gate import is_startup_host_alive

#: Даём окну прорисоваться и отработать первичным проверкам.
#: Через сколько после запуска открывается мастер.
#:
#: Было 1200 мс — задержка досталась от времён, когда окно показывалось
#: сразу и мастеру надо было дождаться, пока оно устоится. Теперь на
#: первом запуске окно не показывается вовсе, ждать нечего, а полторы
#: секунды пустого экрана человек читает как «программа не запустилась».
#: Остаток нужен, чтобы цикл событий успел вернуться в интерфейс.
WIZARD_DELAY_MS = 150


def resync_open_pages(window) -> None:
    """Перечитывает настройки на уже построенных страницах.

    Мастер пишет настройки после того, как страница управления собрана,
    а её переключатели читают снимок один раз при построении. Без этого
    «Запускать вместе с Windows» из мастера оставался включённым только
    в самом мастере: в обычных настройках тумблер показывал старое
    значение, хотя задача в планировщике уже была создана.
    """
    session = None
    try:
        from ui.window_ui_session import get_window_ui_session

        session = get_window_ui_session(window)
    except Exception as exc:
        log(f"Мастер: не удалось получить страницы окна: {exc}", "DEBUG")

    if session is None:
        return

    for page in list(getattr(session, "pages", {}).values()):
        sync = getattr(page, "_sync_program_settings", None)
        if callable(sync):
            try:
                sync()
            except Exception as exc:
                log(f"Мастер: не удалось обновить настройки страницы: {exc}", "DEBUG")


def install_first_run_wizard(
    startup_host,
    *,
    log_startup_metric=None,
    delay_ms: int = WIZARD_DELAY_MS,
) -> None:
    def _open() -> None:
        if not is_startup_host_alive(startup_host):
            return

        # Сервисы hosts включаются один раз после установки, независимо
        # от того, показывается мастер или нет: обновление поверх старой
        # версии мастер не открывает, а сервисы включить всё равно надо.
        try:
            from hosts.first_run_defaults import apply_in_background

            apply_in_background()
        except Exception as exc:
            log(f"Умолчания hosts не применились: {exc}", "⚠ WARNING")

        try:
            from wizard.apply import is_wizard_needed

            if not is_wizard_needed():
                # Мастер не нужен — значит окно уже показано обычным
                # путём, и открывать его повторно нечего.
                return

            # Окна мастера больше нет: вопросы задаёт обучающий тур у тех
            # разделов, к которым они относятся (ui/onboarding/setup_choices.py).
            # Здесь остаётся только открыть окно — на первом запуске оно
            # спрятано до этой минуты, чтобы не мелькать пустым.
            _reveal_main_window(startup_host)
            if callable(log_startup_metric):
                log_startup_metric("FirstRunSetupHandedToTour", "1")
        except Exception as exc:
            # Мастер — удобство, а не обязательная часть запуска.
            # Его падение не должно мешать приложению работать.
            log(f"Мастер первого запуска не открылся: {exc}", "⚠ WARNING")
        finally:
            # Страховка. Окно уже открыто выше, но если разбор настроек
            # упал раньше этой строки, приложение осталось бы работать
            # без единого окна. Повторный вызов ничего не делает.
            _reveal_main_window(startup_host)

    QTimer.singleShot(int(delay_ms), _open)


def _reveal_main_window(startup_host) -> None:
    """Показывает главное окно после мастера.

    В трее приложение остаётся спрятанным: там окна и не должно быть,
    человек сам откроет его из значка.
    """
    window = getattr(startup_host, "_window", None) or getattr(startup_host, "window", None)
    if window is None:
        return
    try:
        if bool(getattr(window, "start_in_tray", False)) or window.isVisible():
            return

        # Раскладку и стили считаем до показа, а не после.
        #
        # Прежде здесь было показать прозрачным и проявить следующим
        # оборотом цикла. Не помогало: Windows создаёт и закрашивает окно
        # раньше, чем Qt применит прозрачность, и на экран успевал
        # выскочить чёрный прямоугольник размера по умолчанию.
        from main.window_startup_signal_setup import prepare_window_for_show

        prepare_window_for_show(window)
        # Прозрачность — оформление; если её не выставить, окно всё равно
        # должно открыться. Раньше похожая мелочь роняла весь показ.
        try:
            window.setWindowOpacity(1.0)
        except Exception:
            pass
        window.show()
        window.raise_()
        window.activateWindow()

        log("Основное окно показано после мастера первого запуска", "DEBUG")
    except Exception as exc:
        log(f"Не удалось показать окно после мастера: {exc}", "⚠ WARNING")


__all__ = ["WIZARD_DELAY_MS", "install_first_run_wizard"]
