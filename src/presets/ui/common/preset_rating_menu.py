from __future__ import annotations

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QWidget
from qfluentwidgets import Action, RoundMenu

from ui.popup_menu import exec_popup_menu


def show_preset_rating_menu(
    parent: QWidget,
    *,
    current_rating: int = 0,
    clear_label: str,
    global_pos: QPoint | None = None,
) -> int | None:
    """Show shared preset rating menu and return the selected rating."""

    menu = RoundMenu(parent=parent)
    current_rating = max(0, min(10, int(current_rating or 0)))

    clear_action = Action(str(clear_label or "Сбросить рейтинг"), menu)
    menu.addAction(clear_action)
    clear_action.setCheckable(True)
    clear_action.setChecked(current_rating == 0)
    menu.addSeparator()

    actions = {}
    for value in range(1, 11):
        action = Action(f"{value}/10", menu)
        menu.addAction(action)
        action.setCheckable(True)
        action.setChecked(current_rating == value)
        actions[action] = value

    chosen = exec_popup_menu(
        menu,
        global_pos or QCursor.pos(),
        owner=parent,
        capture_action=True,
    )
    if chosen == clear_action:
        return 0

    if chosen in actions:
        return int(actions[chosen])
    return None
