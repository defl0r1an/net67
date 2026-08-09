from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget


class PulsingDot(QWidget):
    """Animated status dot with a low-frequency timer."""

    def __init__(self, parent=None, *, size: int = 32):
        super().__init__(parent)
        self._color = QColor("#aeb5c1")
        self._pulse_phase = 0.0
        self._is_pulsing = False

        self.setFixedSize(max(12, int(size)), max(12, int(size)))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)

    def set_color(self, color: str) -> None:
        c = QColor(color)
        if c.isValid():
            self._color = c
        self.update()

    def start_pulse(self) -> None:
        if not self._is_pulsing:
            self._is_pulsing = True
            self._pulse_phase = 0.0
            if self.isVisible():
                self._timer.start()

    def stop_pulse(self) -> None:
        self._is_pulsing = False
        self._timer.stop()
        self._pulse_phase = 0.0
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._is_pulsing and not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._timer.stop()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            window = self.window()
            if window and window.isMinimized():
                self._timer.stop()
            elif self._is_pulsing and not self._timer.isActive():
                self._timer.start()

    def _tick(self) -> None:
        self._pulse_phase = (self._pulse_phase + 0.1) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2
        cy = self.height() / 2
        side = max(12, min(self.width(), self.height()))
        base_r = max(3.0, side * 0.1875)
        pulse_extra = max(1.0, side / 2 - base_r - 1)
        glow_extra = max(1.0, side * 0.09375)

        if self._is_pulsing:
            for phase_offset in (0.0, 0.5):
                phase = (self._pulse_phase + phase_offset) % 1.0
                opacity = max(0.0, 0.72 * (1.0 - phase))
                radius = base_r + pulse_extra * phase
                c = QColor(self._color)
                c.setAlphaF(opacity)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(c)
                r = int(radius)
                painter.drawEllipse(int(cx - r), int(cy - r), r * 2, r * 2)

        glow = QColor(self._color)
        glow.setAlphaF(0.42)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        glow_r = int(base_r + glow_extra)
        painter.drawEllipse(
            int(cx - glow_r),
            int(cy - glow_r),
            glow_r * 2,
            glow_r * 2,
        )

        painter.setBrush(self._color)
        r = int(base_r)
        painter.drawEllipse(int(cx - r), int(cy - r), r * 2, r * 2)

        painter.setBrush(QColor(255, 255, 255, 90))
        shine = max(2, int(side * 0.09375))
        painter.drawEllipse(int(cx - shine), int(cy - shine - 1), shine, shine)
