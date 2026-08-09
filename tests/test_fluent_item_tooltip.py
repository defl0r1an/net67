from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QWidget
from qfluentwidgets import ToolTip

from ui.widgets.fluent_item_tooltip import (
    FLUENT_ITEM_TOOLTIP_ROLE,
    FluentItemToolTipController,
    FluentItemViewToolTipController,
    install_fluent_item_tooltips,
    set_fluent_item_tooltip,
)
from ui.fluent_widgets import set_tooltip


class _TooltipWidget:
    def __init__(self, text: str) -> None:
        self._text = text
        self._fluent_tooltip_filter = object()
        self.set_calls: list[str] = []

    def toolTip(self) -> str:  # noqa: N802
        return self._text

    def setToolTip(self, text: str) -> None:  # noqa: N802
        self.set_calls.append(str(text))
        self._text = str(text)


class FluentItemToolTipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_show_text_uses_qfluent_tooltip(self) -> None:
        owner = QWidget()
        controller = FluentItemToolTipController(owner)

        controller.show_text("MultiSplit\n\n--lua-desync=multisplit", QPoint(40, 40))

        tooltip = getattr(controller, "_tooltip")
        self.assertIsInstance(tooltip, ToolTip)
        self.assertEqual(tooltip.text(), "MultiSplit\n\n--lua-desync=multisplit")

    def test_empty_text_hides_existing_tooltip(self) -> None:
        owner = QWidget()
        controller = FluentItemToolTipController(owner)
        controller.show_text("test", QPoint(40, 40))

        controller.show_text("", QPoint(40, 40))

        self.assertFalse(getattr(controller, "_tooltip").isVisible())

    def test_item_tooltip_text_is_stored_in_data_role(self) -> None:
        item = QTableWidgetItem("row")

        set_fluent_item_tooltip(item, "detail text")

        self.assertEqual(item.data(FLUENT_ITEM_TOOLTIP_ROLE), "detail text")
        self.assertEqual(item.toolTip(), "")

    def test_item_view_tooltip_install_is_idempotent(self) -> None:
        table = QTableWidget(1, 1)

        first = install_fluent_item_tooltips(table)
        second = install_fluent_item_tooltips(table)

        self.assertIs(first, second)
        self.assertIsInstance(first, FluentItemViewToolTipController)

    def test_set_tooltip_skips_duplicate_text(self) -> None:
        widget = _TooltipWidget("same")

        set_tooltip(widget, "same")

        self.assertEqual(widget.set_calls, [])

    def test_source_uses_fluent_tooltip_entrypoints(self) -> None:
        root = Path(__file__).resolve().parents[1]
        allowed_set_tooltip_file = root / "src" / "ui" / "fluent_widgets.py"
        old_method = ".set" + "ToolTip("
        old_class = "Q" + "ToolTip"
        offenders: list[str] = []

        for path in (root / "src").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if old_method in text and path != allowed_set_tooltip_file:
                offenders.append(str(path.relative_to(root)))
            if old_class in text:
                offenders.append(str(path.relative_to(root)))

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
