"""Плашки страниц уходят в колокольчик, а не на экран.

В колокольчик приходило только то, что шло через центр уведомлений
(ui/window_notification_center.py). А плашки страниц — «Пресет сохранён»,
«Не удалось записать hosts», ошибки редактора профилей — показывались
напрямую, InfoBar.success/.error, мимо центра: 83 вызова в 27 файлах.
Плашка гасла через несколько секунд, и найти её потом было негде.

Переписывать каждый вызов — значит пропустить следующий новый. Поэтому
перехват один, на создании InfoBar. Сначала плашка писалась в
колокольчик просмотренной и всё равно всплывала; владелец решил: плашек
нет вовсе, всё в колокольчик (30.09.2026). Теперь плашка окна с
колокольчиком записывается туда и не показывается. Окно без колокольчика
(диалог, самый ранний старт) показывает её как раньше — потерять
сообщение хуже, чем показать его. Плашки самого центра перехват
пропускает: центр решает о них сам.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

__all__ = ["center_owned_infobar", "install_infobar_capture", "level_for_icon"]

_OWN = threading.local()


@contextmanager
def center_owned_infobar():
    """Плашку создаёт сам центр уведомлений — в колокольчик он пишет её сам."""
    previous = getattr(_OWN, "active", False)
    _OWN.active = True
    try:
        yield
    finally:
        _OWN.active = previous


def level_for_icon(icon) -> str:
    try:
        from qfluentwidgets import InfoBarIcon
    except Exception:
        return "info"
    return {
        InfoBarIcon.SUCCESS: "success",
        InfoBarIcon.WARNING: "warning",
        InfoBarIcon.ERROR: "error",
        InfoBarIcon.INFORMATION: "info",
    }.get(icon, "info")


def _center_for(bar):
    widget = bar.parentWidget()
    while widget is not None:
        center = getattr(widget.window(), "window_notification_center", None)
        if center is not None:
            return center
        widget = widget.parentWidget()
    return None


def page_name_for(widget) -> str:
    """Раздел окна (имя PageName), к которому относится виджет.

    Плашку страницы обычно создают с родителем-окном, а не страницей:
    по родителю раздел не узнать. Тогда раздел — тот, что открыт
    сейчас: плашка — ответ на то, что человек сделал на нём.
    """
    try:
        from ui.window_ui_session import get_window_ui_session

        host = get_window_ui_session(widget.window()).page_host
        pages = dict(host.pages)
        current = host.current_page()
    except Exception:
        return ""
    for name, page in pages.items():
        try:
            if page is widget or page.isAncestorOf(widget):
                return name.name
        except RuntimeError:
            continue
    for name, page in pages.items():
        if page is current:
            return name.name
    return ""


def _take(bar, icon, title, content) -> bool:
    center = _center_for(bar)
    if center is None:
        return False
    parent = bar.parentWidget()
    source = f"infobar.{type(parent).__name__}" if parent is not None else "infobar"
    return bool(
        center.take_infobar(
            {
                "level": level_for_icon(icon),
                "title": str(title or ""),
                "content": str(content or ""),
                "source": source,
                "page": page_name_for(parent) if parent is not None else "",
            }
        )
    )


def install_infobar_capture() -> bool:
    """Ставит перехват один раз на процесс. True — поставлен сейчас."""
    from qfluentwidgets.components.widgets.info_bar import InfoBar

    if getattr(InfoBar, "_net67_inbox_capture", False):
        return False
    original_init = InfoBar.__init__
    original_show = InfoBar.show

    def __init__(self, icon, title, content, *args, **kwargs):
        original_init(self, icon, title, content, *args, **kwargs)
        self._net67_in_bell = False
        if getattr(_OWN, "active", False):
            return
        try:
            self._net67_in_bell = _take(self, icon, title, content)
        except Exception:
            # Не забрали — пусть покажется: потерять сообщение хуже.
            self._net67_in_bell = False

    def show(self):
        # Забранная в колокольчик плашка не показывается. Вызывающий
        # может дальше добавлять в неё кнопки и закрывать её — объект
        # живой, только невидимый.
        if getattr(self, "_net67_in_bell", False):
            return None
        return original_show(self)

    InfoBar.__init__ = __init__
    InfoBar.show = show
    InfoBar._net67_inbox_capture = True
    return True
