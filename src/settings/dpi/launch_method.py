"""Текущий способ запуска обхода.

Способ остался один — winws2. Функция сохранена, потому что её
спрашивают из нескольких мест, и подменять каждое обращение константой
значило бы размазать по коду знание, которое лучше держать в одном
месте.
"""

from __future__ import annotations


def get_current_launch_method(*, default: str = "") -> str:
    from settings.mode import DEFAULT_LAUNCH_METHOD

    _ = default
    return DEFAULT_LAUNCH_METHOD


__all__ = ["get_current_launch_method"]
