"""Открывает страницу обновлений из любого места интерфейса.

Страница обновлений (`PageName.SERVERS`) в навигации скрыта. Так вышло
не по замыслу: попасть на неё можно было только через «О программе», а
«О программе» убрали из меню вместе со ссылками прежнего автора. Раздел
остался рабочим, но недостижимым — кнопки «проверить версию» в
приложении не стало вовсе.

Проверка обновлений при этом никуда не делась: она идёт сама при
запуске, но не чаще раза в шесть часов. Для человека, который хочет
посмотреть версию прямо сейчас, это то же самое, что её нет.

## Почему через свойство приложения, а не через зависимости страницы

У карточек на странице управления есть механизм внедрения обработчиков —
`page_actions`. Добавить туда ещё один было бы правильнее по форме, но
это правка в семи файлах, включая конструкторы обеих страниц управления,
их фабрики и договор о параметрах. Ради одной кнопки, которая просто
переключает раздел, цена несоразмерна.

Главное окно и без того лежит в свойстве приложения — его кладёт туда
`ui.app_window_locator.register_app_window` при запуске. Отсюда и берём.
"""

from __future__ import annotations

from log.log import log


#: Ключ, под которым главное окно лежит в свойствах QApplication.
#: Совпадает с тем, что пишет ui.app_window_locator.
WINDOW_PROPERTY = "zapret_primary_window"


def find_main_window():
    """Главное окно приложения или None."""
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return None
        return app.property(WINDOW_PROPERTY)
    except Exception:
        return None


def open_updates_page() -> bool:
    """Показывает страницу обновлений. False — не получилось.

    `allow_internal` обязателен: раздел помечен скрытым, и обычный переход
    его не пускает. Здесь переход не «обычный» — его запросил человек
    нажатием, а не поиск или восстановление вкладки.
    """
    window = find_main_window()
    if window is None:
        log("Страница обновлений: главное окно не найдено", "⚠️ WARNING")
        return False

    try:
        from app.page_names import PageName
        from ui.window_adapter import show_page

        return bool(show_page(window, PageName.SERVERS, allow_internal=True))
    except Exception as exc:
        log(f"Не удалось открыть страницу обновлений: {exc}", "❌ ERROR")
        return False


__all__ = ["WINDOW_PROPERTY", "find_main_window", "open_updates_page"]
