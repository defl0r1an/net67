"""Настройки движка обхода.

Раньше отсюда торчала целая страница выбора способа запуска: winws1,
winws2, оркестратор. Выбор вырезан, и вместе с ним ушли страница,
команды переключения и настройки оркестратора.

Осталось то, что к выбору отношения не имело и продолжает работать:
текущий способ запуска (он теперь всегда один) и настройки стратегии
вроде `--wssize`. Их читают движок и подготовка запуска.
"""

from __future__ import annotations

from settings.dpi.launch_method import get_current_launch_method
from settings.dpi.strategy_settings import (
    get_strategy_launch_method,
    get_wssize_enabled,
)


def get_launch_method() -> str:
    """Способ запуска. Он один, но спрашивают его многие."""
    from settings.mode import DEFAULT_LAUNCH_METHOD

    return DEFAULT_LAUNCH_METHOD


__all__ = [
    "get_current_launch_method",
    "get_launch_method",
    "get_strategy_launch_method",
    "get_wssize_enabled",
]
