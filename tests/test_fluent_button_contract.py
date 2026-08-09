from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon, PrimaryPushButton, PushButton, ToolButton

from ui.fluent_widgets import RefreshButton


class FluentButtonContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_qfluentwidgets_buttons_accept_icons_in_constructor(self) -> None:
        buttons = [
            PushButton("Открыть", icon=FluentIcon.FOLDER),
            PrimaryPushButton("Создать", icon=FluentIcon.ADD),
            RefreshButton("Обновить"),
            ToolButton(FluentIcon.ADD),
        ]

        for button in buttons:
            self.assertFalse(button.icon().isNull())

    def test_refresh_button_reads_name_state_and_clicks_from_keyboard(self) -> None:
        button = RefreshButton("Обновить статус")
        self.addCleanup(button.deleteLater)
        clicked: list[bool] = []
        button.clicked.connect(lambda: clicked.append(True))

        self.assertEqual(button.accessibleName(), "Обновить статус")
        self.assertEqual(button.property("screenReaderStateText"), "Обновить статус")

        button.show()
        self._app.processEvents()
        button.setFocus()
        self._app.processEvents()
        QTest.keyClick(button, Qt.Key.Key_Return)
        self._app.processEvents()

        self.assertEqual(clicked, [True])

        button.set_loading(True)

        self.assertEqual(button.accessibleName(), "Обновить статус, выполняется")
        self.assertEqual(button.property("screenReaderStateText"), "Обновить статус, выполняется")

        button.set_loading(False)

        self.assertEqual(button.accessibleName(), "Обновить статус")
        self.assertEqual(button.property("screenReaderStateText"), "Обновить статус")

    def test_legacy_project_button_layer_is_removed(self) -> None:
        root = os.path.dirname(os.path.dirname(__file__))
        blocked_patterns = (
            re.compile(r"\bActionButton\b"),
            re.compile(r"\bPrimaryActionButton\b"),
            re.compile(r"\bThemedActionButton\b"),
            re.compile(r"\bBigActionButton\b"),
            re.compile(r"\bStopButton\b"),
            re.compile(r"\bapply_themed_action_button\b"),
            re.compile(r"\bapply_themed_accent_button\b"),
        )
        allowed_files = {
            os.path.join(root, "tests", "test_fluent_button_contract.py"),
        }

        offenders: list[str] = []
        for base in (os.path.join(root, "src"), os.path.join(root, "tests")):
            for dirpath, _, filenames in os.walk(base):
                for filename in filenames:
                    if not filename.endswith(".py"):
                        continue
                    path = os.path.join(dirpath, filename)
                    if path in allowed_files:
                        continue
                    with open(path, "r", encoding="utf-8") as fh:
                        text = fh.read()
                    for pattern in blocked_patterns:
                        if pattern.search(text):
                            offenders.append(f"{os.path.relpath(path, root)}: {pattern.pattern}")

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
