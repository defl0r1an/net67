"""Переключатель простого и расширенного интерфейса.

В простом режиме сайдбар показывает только главную страницу текущего
режима и «Оформление». Всё остальное — настройки DPI, диагностика,
логи, Telegram-прокси, режимы v1 и Оркестр — открывается этой кнопкой.

Кнопка живёт внизу сайдбара и не является страницей: она не выбирается
и не участвует в маршрутизации, поэтому selectable=False.
"""

from __future__ import annotations

from log.log import log
from settings.store import get_advanced_mode, set_advanced_mode
from ui.accessibility import set_control_accessibility
from ui.window_ui_session import get_window_ui_session


#: routeKey кнопки. Не пересекается ни с одним PageName.route_key.
ADVANCED_TOGGLE_ROUTE_KEY = "__advanced_mode_toggle__"


def _labels(expanded: bool) -> tuple[str, str]:
    """Текст и подсказка кнопки под текущее состояние."""
    if expanded:
        return ("Простой вид", "Скрыть расширенные настройки")
    return ("Расширенные настройки", "Показать все разделы приложения")


def _icon(expanded: bool):
    from qfluentwidgets import FluentIcon

    return FluentIcon.HIDE if expanded else FluentIcon.SETTING


def add_advanced_mode_toggle(window) -> None:
    """Добавляет кнопку в низ сайдбара. Повторный вызов игнорируется."""
    session = get_window_ui_session(window)
    if session is None:
        return
    if getattr(session, "advanced_toggle_item", None) is not None:
        return

    try:
        from qfluentwidgets import NavigationItemPosition
    except Exception:
        log("[NAV] qfluentwidgets недоступен, переключатель режима не добавлен", "DEBUG")
        return

    advanced = get_advanced_mode()
    text, tooltip = _labels(advanced)

    try:
        item = window.navigationInterface.addItem(
            routeKey=ADVANCED_TOGGLE_ROUTE_KEY,
            icon=_icon(advanced),
            text=text,
            onClick=lambda checked=False, current_window=window: toggle_advanced_mode(current_window),
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )
    except Exception as exc:
        log(f"[NAV] не удалось добавить переключатель режима: {exc}", "⚠ WARNING")
        return

    if item is None:
        return

    session.advanced_toggle_item = item
    set_control_accessibility(item, name=text, description=tooltip)
    log(f"[NAV] переключатель режима добавлен, advanced={advanced}", "DEBUG")


def refresh_advanced_mode_toggle(window) -> None:
    """Обновляет текст и иконку кнопки под текущее состояние настройки."""
    session = get_window_ui_session(window)
    if session is None:
        return
    item = getattr(session, "advanced_toggle_item", None)
    if item is None:
        return

    advanced = get_advanced_mode()
    text, tooltip = _labels(advanced)

    try:
        item.setText(text)
    except Exception:
        pass
    try:
        item.setIcon(_icon(advanced))
    except Exception:
        pass
    # Прямая установка подсказки Qt в проекте запрещена: они идут через
    # собственную реализацию, иначе они не попадают в стиль Fluent.
    try:
        from ui.widgets.fluent_item_tooltip import set_fluent_item_tooltip

        set_fluent_item_tooltip(item, tooltip)
    except Exception:
        pass
    set_control_accessibility(item, name=text, description=tooltip)


def _slide_navigation_panel(window, *, expanding: bool) -> None:
    """Плавно раскрывает или сворачивает панель разделов.

    Видимость переключается здесь же, и порядок принципиален. При
    раскрытии панель надо сначала показать, иначе анимировать нечего:
    раскладка пропускает спрятанные виджеты. При сворачивании — наоборот,
    спрятать только после того, как ширина дошла до нуля, иначе панель
    исчезнет мгновенно и движения никто не увидит.

    Сбой оформления не должен мешать переключению режима, поэтому любая
    ошибка здесь только пишется в лог: пункты уже переключены.
    """
    try:
        from ui.navigation.panel_side import load_side
        from ui.navigation.panel_slide import animate_panel

        panel = getattr(window, "navigationInterface", None)
        if panel is None:
            return

        side = load_side()
        if expanding:
            panel.setVisible(True)
            animate_panel(panel, side, expanding=True)
            return

        animate_panel(
            panel,
            side,
            expanding=False,
            on_finished=lambda target=panel: target.setVisible(False),
        )
    except Exception as exc:
        log(f"[NAV] панель не анимирована: {exc}", "DEBUG")


def toggle_advanced_mode(window) -> None:
    """Переключает режим и перерисовывает сайдбар.

    Пункты навигации для расширенных страниц создаются всегда, независимо
    от режима, — здесь меняется только их видимость. Полная пересборка
    сайдбара не нужна и была бы заметна глазу.
    """
    from ui.navigation.sidebar_builder import (
        apply_nav_visibility_filter,
        refresh_nav_mode_visibility_cache,
    )

    next_value = not get_advanced_mode()
    try:
        set_advanced_mode(next_value)
    except Exception as exc:
        log(f"[NAV] не удалось сохранить режим интерфейса: {exc}", "⚠ WARNING")
        return

    log(f"[NAV] режим интерфейса переключён, advanced={next_value}", "INFO")

    refresh_advanced_mode_toggle(window)

    method = None
    try:
        method = window.get_launch_method()
    except Exception:
        method = None

    # Обязательный шаг. apply_nav_visibility_filter берёт минимум из двух
    # источников: актуальной схемы и кэша session.nav_mode_visibility.
    # Кэш посчитан при запуске в прежнем режиме, и без обновления пункты
    # останутся скрытыми, хотя схема их уже разрешила: над пустыми
    # группами повиснут одни заголовки.
    refresh_nav_mode_visibility_cache(window, method, advanced=next_value)
    apply_nav_visibility_filter(window, method=method, advanced=next_value)

    # Выезд панели. Строго после того, как видимость пунктов уже
    # применена: анимировать панель, в которой ещё не те разделы, значит
    # показать человеку промежуточное состояние.
    #
    # Видимостью панели теперь распоряжается сама анимация: раскрыть —
    # показать и растянуть, свернуть — сжать и спрятать по завершении.
    # Прежний отдельный вызов apply_sidebar_width_for_mode отсюда убран,
    # он гасил панель мгновенно и съедал всё движение.
    _slide_navigation_panel(window, expanding=next_value)

    # Вкладки разделов наверху зависят от режима так же, как пункты
    # панели: в простом виде почти все разделы пустеют. Сигнал об этом
    # панель не шлёт — пункты не добавляются и не удаляются, у них
    # меняется видимость, — поэтому зовём пересборку явно.
    try:
        refresh_tabs = getattr(window, "refresh_after_mode_change", None)
        if callable(refresh_tabs):
            refresh_tabs()
    except Exception as exc:
        log(f"[NAV] вкладки разделов не пересобраны: {exc}", "DEBUG")

    # Поисковые подсказки тоже зависят от режима: в простом виде
    # расширенные страницы не должны находиться поиском.
    try:
        from ui.navigation.search import update_sidebar_search_suggestions

        update_sidebar_search_suggestions(window)
    except Exception:
        pass

    # Простому виду хватает окна вдвое меньше: одна страница и два
    # пункта в боковой панели.
    try:
        from ui.window_mode_geometry import apply_window_size_for_mode

        apply_window_size_for_mode(window, next_value)
    except Exception as exc:
        log(f"[NAV] не удалось подогнать размер окна под режим: {exc}", "DEBUG")

    # На странице управления в простом виде остаются только кнопка,
    # состояние и автозапуск.
    try:
        from presets.ui.control.simple_view import apply_simple_view
        from ui.window_ui_session import get_window_ui_session

        session = get_window_ui_session(window)
        for page in list(getattr(session, "pages", {}).values()) if session else []:
            if hasattr(page, "control_card_card"):
                apply_simple_view(page, next_value)
    except Exception as exc:
        log(f"[NAV] не удалось перестроить страницу под режим: {exc}", "DEBUG")

    if not next_value:
        _return_to_entry_page(window, method)


def _return_to_entry_page(window, method) -> None:
    """Уводит на главную при переходе в простой вид.

    Иначе получалась ловушка: человек нажимает «Простой вид», находясь,
    например, в диагностике. Боковая панель прячется, страница остаётся
    открытой, а кнопка возврата в расширенный вид есть только на главной
    странице управления. Выйти можно было лишь через диспетчер задач.
    """
    try:
        from ui.navigation.schema import get_mode_entry_page
        from ui.navigation.search import show_page
    except Exception as exc:
        log(f"[NAV] возврат на главную недоступен: {exc}", "DEBUG")
        return

    try:
        entry_page = get_mode_entry_page(method)
    except Exception as exc:
        log(f"[NAV] не удалось определить главную страницу режима: {exc}", "⚠ WARNING")
        return

    try:
        show_page(window, entry_page)
        log(f"[NAV] простой вид: возврат на {entry_page.name}", "INFO")
    except Exception as exc:
        log(f"[NAV] не удалось вернуться на главную: {exc}", "⚠ WARNING")


def apply_sidebar_width_for_mode(window, advanced: bool) -> None:
    """Ставит боковую панель под режим без анимации.

    Это путь запуска: при старте окна анимировать нечего, состояние надо
    просто выставить. Переключение режима руками идёт другой дорогой —
    через _slide_navigation_panel, там панель раскрывается плавно.

    В простом виде в панели остаются два пункта, и полоса шириной в
    288 пикселей ради них — пустое место. Вернуться к полному интерфейсу
    можно кнопкой «Расширенные настройки» внизу самой страницы, см.
    presets/ui/control/simple_view.

    Прятать надо именно панель, а не её содержимое. Промежуточная
    попытка оставить панель и убрать пункты дала худшее из двух: слева
    оставалась тёмная пустая полоса, и это читалось как поломка.

    Размер восстанавливается явно. Анимация сворачивания оставляет
    панели нулевую ширину, и без восстановления она открылась бы пустой
    полосой — ровно та поломка, из-за которой этот путь и переписан.
    """
    try:
        nav = window.navigationInterface
    except Exception:
        return

    advanced = bool(advanced)
    try:
        from ui.navigation.panel_side import load_side
        from ui.navigation.panel_slide import apply_panel_state

        apply_panel_state(nav, load_side(), expanded=advanced)
        nav.setVisible(advanced)
    except Exception as exc:
        log(f"[NAV] не удалось переключить боковую панель: {exc}", "DEBUG")


__all__ = [
    "ADVANCED_TOGGLE_ROUTE_KEY",
    "apply_sidebar_width_for_mode",
    "add_advanced_mode_toggle",
    "refresh_advanced_mode_toggle",
    "toggle_advanced_mode",
]
