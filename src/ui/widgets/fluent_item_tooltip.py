from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject, QPoint, QEvent, Qt
from PyQt6.QtWidgets import QApplication, QAbstractItemView, QWidget
from qfluentwidgets import ToolTip


FLUENT_ITEM_TOOLTIP_ROLE = int(Qt.ItemDataRole.UserRole) + 610


class FluentItemToolTipController(QObject):
    """Fluent-подсказка для строк, которые рисуются через delegate."""

    def __init__(self, owner: QWidget, *, duration: int = 6000, offset: QPoint | None = None):
        super().__init__(owner)
        self._owner = owner
        self._duration = int(duration)
        self._offset = offset or QPoint(12, 18)
        self._tooltip: ToolTip | None = None
        owner.installEventFilter(self)

    def show_text(self, text: str, global_pos: QPoint) -> None:
        text = str(text or "").strip()
        if not text:
            self.hide()
            return

        if self._tooltip is None:
            parent = self._owner.window() if self._owner is not None else None
            self._tooltip = ToolTip("", parent)
            self._tooltip.setDuration(self._duration)

        self._tooltip.setText(text)
        self._tooltip.adjustSize()
        self._tooltip.move(self._bounded_pos(global_pos + self._offset))
        self._tooltip.show()

    def hide(self) -> None:
        if self._tooltip is not None:
            self._tooltip.hide()

    def eventFilter(self, obj, event):  # noqa: N802
        _ = obj
        if event.type() in {
            QEvent.Type.Hide,
            QEvent.Type.Leave,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
        }:
            self.hide()
        return super().eventFilter(obj, event)

    def _bounded_pos(self, pos: QPoint) -> QPoint:
        tooltip = self._tooltip
        if tooltip is None:
            return pos

        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen is None:
            return pos

        rect = screen.availableGeometry()
        x = max(rect.left(), min(pos.x(), rect.right() - tooltip.width() - 4))
        y = max(rect.top(), min(pos.y(), rect.bottom() - tooltip.height() - 4))
        return QPoint(x, y)


class FluentItemViewToolTipController(QObject):
    """Fluent-подсказка для item-view: таблиц, списков и похожих виджетов."""

    def __init__(
        self,
        view: QAbstractItemView,
        *,
        role: int = FLUENT_ITEM_TOOLTIP_ROLE,
        duration: int = 6000,
    ):
        super().__init__(view)
        self._view = view
        self._viewport = view.viewport()
        self._role = int(role)
        self._tooltip = FluentItemToolTipController(self._viewport, duration=duration)
        self._viewport.installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._viewport and event.type() == QEvent.Type.ToolTip:
            index = self._view.indexAt(event.pos())
            text = str(index.data(self._role) or "").strip() if index.isValid() else ""
            if text:
                self._tooltip.show_text(text, event.globalPos())
                return True

            self._tooltip.hide()
            return True

        if event.type() in {
            QEvent.Type.Hide,
            QEvent.Type.Leave,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
        }:
            self._tooltip.hide()
        return super().eventFilter(obj, event)


def install_fluent_item_tooltips(
    view: QAbstractItemView,
    *,
    role: int = FLUENT_ITEM_TOOLTIP_ROLE,
) -> FluentItemViewToolTipController:
    """Включает fluent-подсказки для item-view один раз."""

    controller = getattr(view, "_fluent_item_tooltip_controller", None)
    if controller is None:
        controller = FluentItemViewToolTipController(view, role=role)
        view._fluent_item_tooltip_controller = controller  # type: ignore[attr-defined]
    return controller


def set_fluent_item_tooltip(item, text: str) -> None:
    """Сохраняет текст подсказки в data-role без старой системной подсказки."""

    item.setData(FLUENT_ITEM_TOOLTIP_ROLE, str(text or "").strip())


class FluentHoverToolTipController(QObject):
    """Fluent-подсказка для виджета, который сам рисует плитки.

    Текст зависит от того, что под курсором, — виджет отдаёт его функцией
    text_at(точка). Раньше такие сетки меняли системную подсказку на каждом
    движении мыши: белая на тёмной теме, она была чужой остальной программе.
    """

    def __init__(self, owner: QWidget, text_at: Callable[[QPoint], str], *, duration: int = 6000):
        super().__init__(owner)
        self._owner = owner
        self._text_at = text_at
        self._shown_text = ""
        self._tooltip = FluentItemToolTipController(owner, duration=duration)
        owner.installEventFilter(self)

    def _text(self, point: QPoint) -> str:
        try:
            return str(self._text_at(point) or "").strip()
        except Exception:
            return ""

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._owner:
            kind = event.type()
            if kind == QEvent.Type.ToolTip:
                self._shown_text = self._text(event.pos())
                if self._shown_text:
                    self._tooltip.show_text(self._shown_text, event.globalPos())
                else:
                    self._tooltip.hide()
                return True
            if kind == QEvent.Type.MouseMove and self._shown_text:
                # Курсор ушёл на другую плитку: подсказка уже не про неё.
                # Новую покажет следующее событие ToolTip, когда мышь замрёт.
                if self._text(event.position().toPoint()) != self._shown_text:
                    self._shown_text = ""
                    self._tooltip.hide()
            elif kind == QEvent.Type.Leave:
                self._shown_text = ""
        return super().eventFilter(obj, event)


def install_fluent_hover_tooltip(
    owner: QWidget,
    text_at: Callable[[QPoint], str],
) -> FluentHoverToolTipController:
    """Включает fluent-подсказку «по точке» для рисующего виджета один раз."""

    controller = getattr(owner, "_fluent_hover_tooltip_controller", None)
    if controller is None:
        controller = FluentHoverToolTipController(owner, text_at)
        owner._fluent_hover_tooltip_controller = controller  # type: ignore[attr-defined]
    return controller


__all__ = [
    "FLUENT_ITEM_TOOLTIP_ROLE",
    "FluentHoverToolTipController",
    "FluentItemToolTipController",
    "FluentItemViewToolTipController",
    "install_fluent_hover_tooltip",
    "install_fluent_item_tooltips",
    "set_fluent_item_tooltip",
]
