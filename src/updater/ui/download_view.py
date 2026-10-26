"""Куда отдавать ход загрузки обновления, кроме карточки на «Серверах».

Загрузку ведёт страница «Серверы» (updater/update_page_runtime.py), а
показывает её ещё и окно «Доступно обновление», если человек нажал
«Обновить» в нём и не скрыл. Окно встаёт сюда само на время загрузки и
уходит, когда закрывается; страница отдаёт ход сюда же, а не знает про
окно напрямую.

Ссылка слабая: закрытое и удалённое окно не держится и не получает вызовов.
"""

from __future__ import annotations

import weakref

_active = None


def set_active(view) -> None:
    global _active
    _active = weakref.ref(view)


def clear(view=None) -> None:
    """Снимает окно; с ``view`` — только если стоит именно оно."""
    global _active
    if view is None or get_active() is view:
        _active = None


def get_active():
    view = _active() if _active is not None else None
    if view is None:
        return None
    try:
        view.isVisible()
    except RuntimeError:
        # Оболочка Python осталась, а окно Qt уже удалено.
        return None
    return view


def forward(method: str, *args) -> None:
    """Зовёт метод активного окна; ошибка окна не мешает загрузке."""
    view = get_active()
    if view is None:
        return
    try:
        getattr(view, method)(*args)
    except Exception:
        pass


__all__ = ["clear", "forward", "get_active", "set_active"]
