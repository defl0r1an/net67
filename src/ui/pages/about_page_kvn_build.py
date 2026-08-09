"""Удалено.

Здесь строилась вкладка «net67 KVN» — раздел о стороннем проекте автора
исходников со ссылками на его Telegram-канал, бота подписки и GitHub.

Вкладка убрана из about_page_tabs_build и about_page.py. Модуль оставлен
пустым, чтобы не ломать возможные внешние импорты.
"""

from __future__ import annotations


def build_about_page_kvn_content(*_args, **_kwargs) -> None:
    return None


__all__ = ["build_about_page_kvn_content"]
