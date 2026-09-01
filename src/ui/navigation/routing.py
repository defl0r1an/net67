# ui/navigation/routing.py
"""Переход на страницу окна.

Здесь осталось то, ради чего в окно вообще обращаются извне: показать
страницу и, если надо, открыть на ней нужную вкладку.

Раньше это лежало в `ui/navigation/search.py` вместе с поиском по
разделам — строкой в полосе заголовка, подсказками, обходом результатов
с клавиатуры и отдельным указателем по preset-ам и profile-ям. Поиск
убран целиком: разделов на экране четыре, страниц в каждом не больше
четырёх, и искать там было нечего, а виджет при этом жил своей жизнью и
временами всплывал сам по себе.

Навигация к поиску отношения не имела и переехала сюда — в модуль, чьё
название говорит, что он делает.
"""

from __future__ import annotations

from app.page_names import PageName
from ui.page_actions import switch_page_tab
from ui.window_ui_session import get_window_ui_session


def _get_page_host(window):
    session = get_window_ui_session(window)
    return None if session is None else session.page_host


def show_page(window, page_name: PageName) -> bool:
    """Открывает страницу. False — окно ещё не собрано."""
    page_host = _get_page_host(window)
    if page_host is None:
        return False
    return bool(page_host.show_page(page_name))


def route_to_page(window, page_name: PageName, tab_key: str = "") -> bool:
    """Открывает страницу и, если задана, вкладку на ней.

    Вкладка — необязательное уточнение, и её неудача не отменяет
    перехода: страница уже открыта, и возвращать человека обратно
    из-за того, что не нашлась вкладка, было бы хуже.
    """
    if not show_page(window, page_name):
        return False

    if not tab_key:
        return True

    try:
        return bool(switch_page_tab(window, page_name, tab_key))
    except Exception:
        return False


__all__ = [
    "route_to_page",
    "show_page",
]
