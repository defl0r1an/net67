"""Accessibility helpers for About help cards."""

from __future__ import annotations

from ui.accessibility import enable_keyboard_click, set_control_accessibility, set_state_text


def set_help_card_accessibility(card, *, action_name: str, description: str) -> None:
    """Задаёт понятный текст кликабельной карточке справки."""

    set_state_text(card, action_name)
    set_control_accessibility(card, name=action_name, description=description)
    enable_keyboard_click(card)
    for button in (getattr(card, "button", None), getattr(card, "linkButton", None)):
        if button is None:
            continue
        set_state_text(button, action_name)
        set_control_accessibility(button, name=action_name, description=description)


__all__ = ["set_help_card_accessibility"]
