from __future__ import annotations

from ui.window_appearance_state import (
    on_animations_changed,
    on_editor_smooth_scroll_changed,
    on_smooth_scroll_changed,
)


def initialize_window_appearance_bindings(window) -> None:
    """Применяет сохранённые настройки внешнего вида к окну при старте."""
    from settings.appearance import (
        peek_warmed_animations_enabled,
        peek_warmed_editor_smooth_scroll_enabled,
        peek_warmed_smooth_scroll_enabled,
    )

    on_animations_changed(window, bool(peek_warmed_animations_enabled()))
    on_smooth_scroll_changed(window, bool(peek_warmed_smooth_scroll_enabled()))
    on_editor_smooth_scroll_changed(window, bool(peek_warmed_editor_smooth_scroll_enabled()))


# Праздничные украшения окна — гирлянда и снежинки — убраны вместе с
# разделом «Оформление». Включались они не отсюда, а из подписки: их
# запускал обработчик состояния подписки, и вместе с ними тот же код
# применял прозрачность окна.
#
# Прозрачность при этом никуда не делась: её применяет main/entry.py
# сразу после создания окна, и делает это независимо от подписки.
# Проверено обходом src — второго применения там больше нет, так что
# удаление ничего не оставило без хозяина.


__all__ = [
    "initialize_window_appearance_bindings",
]
