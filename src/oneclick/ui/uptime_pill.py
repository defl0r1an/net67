"""Плашка «сколько уже работает обход» рядом с заголовком карточки обхода.

Вид взят у zapret: приглушённая «таблетка» с часиками. Текст плашка сама
не считает — его ставит кнопка обхода (oneclick/ui/button.py) раз в секунду
по общим часам ui/launch_uptime.py: секунды у net67 видны всегда, иначе
первые минуты выглядят застывшими.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

from qfluentwidgets import CaptionLabel


PILL_PAD_Y = 2
PILL_PAD_LEFT = 20
PILL_PAD_RIGHT = 8


class UptimePill(CaptionLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Приглушённый цвет: это пояснение к заголовку, а не второй заголовок.
        self.setTextColor("#3f4650", "#c8ced8")
        # Плашка-«таблетка» с часиками ровно стоит рядом с крупным заголовком
        # по центру строки, и мелкий шрифт не кажется съехавшим.
        self.setContentsMargins(PILL_PAD_LEFT, PILL_PAD_Y, PILL_PAD_RIGHT, PILL_PAD_Y)
        self.setVisible(False)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.palette().color(self.foregroundRole()))
        pill = QColor(color)
        pill.setAlphaF(0.12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pill)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        # Часики: кружок и две стрелки.
        pen = QPen(color, 1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center = QPointF(PILL_PAD_Y + 5.0 + 2.0, rect.center().y())
        painter.drawEllipse(center, 4.6, 4.6)
        painter.drawLine(center, QPointF(center.x(), center.y() - 2.8))
        painter.drawLine(center, QPointF(center.x() + 2.2, center.y()))
        painter.end()
        super().paintEvent(event)


__all__ = ["UptimePill"]
