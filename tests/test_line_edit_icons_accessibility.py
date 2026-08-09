from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLineEdit, QToolButton

from ui.widgets.line_edit_icons import set_line_edit_clear_button_icon


class LineEditIconsAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_clear_button_has_screen_reader_text(self) -> None:
        line_edit = QLineEdit()
        line_edit.setClearButtonEnabled(True)
        line_edit.setText("youtube.com")
        line_edit.show()

        set_line_edit_clear_button_icon(line_edit)
        self._app.processEvents()

        clear_button = next(
            (
                button
                for button in line_edit.findChildren(QToolButton)
                if button.objectName() == "qt_clear_button"
                or (button.defaultAction() is not None and button.defaultAction().objectName() == "_q_qlineeditclearaction")
            ),
            None,
        )
        self.assertIsNotNone(clear_button)
        self.assertEqual(clear_button.accessibleName(), "Очистить поле ввода")
        self.assertEqual(clear_button.property("screenReaderStateText"), "Очистить поле ввода")
        self.assertIn("удаляет введенный текст", clear_button.accessibleDescription().lower())


if __name__ == "__main__":
    unittest.main()
