"""Компоненты страницы диагностики соединений."""

from __future__ import annotations

from qfluentwidgets import CaptionLabel, TextEdit

from ui.accessibility import set_state_text
from ui.smooth_scroll import apply_editor_smooth_scroll_preference


_STATUS_MARKERS = (
    "🔄",
    "✅",
    "⏹",
    "⚠",
    "❌",
    "ℹ",
    "🚀",
    "🌐",
    "🎮",
    "🎬",
    "🎉",
    "💡",
    "📦",
    "📋",
    "📁",
    "️",
)


def clean_connection_status_text(text: object) -> str:
    value = " ".join(str(text or "").strip().split())
    for marker in _STATUS_MARKERS:
        value = value.replace(marker, "")
    return " ".join(value.split())


class ScrollBlockingConnectionTextEdit(TextEdit):
    """TextEdit, который не прокручивает родительскую страницу колесом мыши."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("noDrag", True)
        apply_editor_smooth_scroll_preference(self)

    def wheelEvent(self, event):
        scrollbar = self.verticalScrollBar()
        delta = event.angleDelta().y()
        if delta > 0 and scrollbar.value() == scrollbar.minimum():
            event.accept()
            return
        if delta < 0 and scrollbar.value() == scrollbar.maximum():
            event.accept()
            return
        super().wheelEvent(event)
        event.accept()


class ConnectionStatusBadge(CaptionLabel):
    """Небольшой статусный бейдж."""

    def __init__(self, text: str = "", status: str = "muted", parent=None):
        super().__init__(parent)
        self.set_status(text, status)

    def set_status(self, text: str, status: str = "muted"):
        _ = status
        self.setText(text)
        value = clean_connection_status_text(text)
        if value:
            set_state_text(self, f"Индикатор диагностики: {value}")
