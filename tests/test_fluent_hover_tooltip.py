"""Фирменная подсказка «по точке» для сеток, которые сами рисуют плитки.

Сетки провайдеров DNS и сервисов hosts меняли системную подсказку на
каждом движении мыши: белая на тёмной теме, она была чужой остальной
программе. Теперь текст спрашивается у сетки в момент показа — и
подсказка гаснет, когда курсор уходит на другую плитку.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FluentHoverToolTipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _grid(self):
        from PyQt6.QtWidgets import QWidget

        from ui.widgets.fluent_item_tooltip import install_fluent_hover_tooltip

        widget = QWidget()
        widget.resize(200, 50)
        widget.setMouseTracking(True)
        self.addCleanup(widget.deleteLater)
        # Две «плитки»: левая половина и правая.
        controller = install_fluent_hover_tooltip(
            widget, lambda point: "левая" if point.x() < 100 else "правая"
        )
        return widget, controller

    def _shown(self, controller) -> str:
        tooltip = controller._tooltip._tooltip
        if tooltip is None or not tooltip.isVisible():
            return ""
        return tooltip.text()

    def _tooltip_event(self, widget, x: int) -> bool:
        from PyQt6.QtCore import QEvent, QPoint
        from PyQt6.QtGui import QHelpEvent

        local = QPoint(x, 10)
        event = QHelpEvent(QEvent.Type.ToolTip, local, widget.mapToGlobal(local))
        return self.app.sendEvent(widget, event)

    def _move(self, widget, x: int) -> None:
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        local = QPointF(x, 10)
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            local,
            widget.mapToGlobal(local),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.app.sendEvent(widget, event)

    def test_shows_text_of_the_tile_under_cursor(self) -> None:
        widget, controller = self._grid()
        widget.show()

        self._tooltip_event(widget, 30)
        self.assertEqual(self._shown(controller), "левая")

        self._tooltip_event(widget, 150)
        self.assertEqual(self._shown(controller), "правая")

    def test_moving_to_another_tile_hides_stale_text(self) -> None:
        widget, controller = self._grid()
        widget.show()

        self._tooltip_event(widget, 30)
        self._move(widget, 40)  # та же плитка — подсказка остаётся
        self.assertEqual(self._shown(controller), "левая")

        self._move(widget, 150)  # другая плитка — старая подсказка уже не про неё
        self.assertEqual(self._shown(controller), "")

    def test_install_is_idempotent(self) -> None:
        from ui.widgets.fluent_item_tooltip import install_fluent_hover_tooltip

        widget, controller = self._grid()
        self.assertIs(install_fluent_hover_tooltip(widget, lambda _point: "другое"), controller)


if __name__ == "__main__":
    unittest.main()
