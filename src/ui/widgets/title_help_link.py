"""Одинаковая ссылка на свою документацию в заголовках страниц net67."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import FluentIcon

from ui.accessibility import set_control_accessibility
from ui.fluent_widgets import set_tooltip
from ui.widgets.site_link_button import SiteLinkButton

HELP_LINK_TEXT = "Как это работает?"


def make_help_link(url: str, *, tooltip: str, description: str, text: str = HELP_LINK_TEXT, parent=None) -> SiteLinkButton:
    button = SiteLinkButton(FluentIcon.HELP, url, text, parent)
    set_tooltip(button, tooltip)
    set_control_accessibility(button, name=text, description=description)
    return button


def add_title_help_link(page, url: str, *, tooltip: str, description: str, text: str = HELP_LINK_TEXT):
    position = page.layout.indexOf(page.title_label)
    if position < 0 or not url:
        return None
    page.layout.removeWidget(page.title_label)
    header = QWidget(page.content)
    header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    row = QHBoxLayout(header)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(12)
    row.addWidget(page.title_label, 0, Qt.AlignmentFlag.AlignVCenter)
    row.addStretch(1)
    button = make_help_link(url, tooltip=tooltip, description=description, text=text, parent=header)
    row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
    page.layout.insertWidget(position, header)
    return header, button
