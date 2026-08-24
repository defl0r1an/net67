from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from settings.mode import ORCHESTRA_MODE, ZAPRET2_MODE


class DpiSettingsAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_launch_method_labels_are_named_for_screen_reader(self) -> None:
        from settings.dpi.page import DpiSettingsPage

        page = DpiSettingsPage(
            dpi_settings_feature=SimpleNamespace(),
            orchestra_feature=SimpleNamespace(),
            runtime_actions=SimpleNamespace(handle_launch_method_changed=Mock()),
            set_status=Mock(),
            after_launch_method_changed=Mock(),
        )
        self.addCleanup(page.deleteLater)

        self.assertEqual(
            page._method_desc_label.property("screenReaderStateText"),
            "Описание выбора метода запуска: Выберите способ запуска обхода блокировок",
        )
        self.assertEqual(
            page.zapret2_header.property("screenReaderStateText"),
            "Раздел метода запуска: net67 v2 (winws2.exe)",
        )
        self.assertEqual(
            page._zapret1_header.property("screenReaderStateText"),
            "Раздел метода запуска: net67 v1 (winws.exe)",
        )

        page._ensure_orchestra_settings_built()

        self.assertEqual(
            page._orchestra_label.property("screenReaderStateText"),
            "Раздел метода запуска: Настройки оркестратора",
        )

    def test_launch_method_options_can_be_changed_with_arrow_keys(self) -> None:
        from settings.dpi.page import DpiSettingsPage

        requested: list[tuple[str, str]] = []
        page = DpiSettingsPage(
            dpi_settings_feature=SimpleNamespace(
                describe_visibility=Mock(return_value=SimpleNamespace(show_orchestra_settings=False)),
            ),
            orchestra_feature=SimpleNamespace(),
            runtime_actions=SimpleNamespace(handle_launch_method_changed=Mock()),
            set_status=Mock(),
            after_launch_method_changed=Mock(),
        )
        self.addCleanup(page.deleteLater)
        page._request_dpi_settings_action = lambda action, method="": requested.append((action, method))
        page._update_method_selection(ZAPRET2_MODE)
        page.show()
        self._app.processEvents()
        page.method_zapret2_mode.setFocus()
        self._app.processEvents()

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        page.method_zapret2_mode.keyPressEvent(event)
        self._app.processEvents()

        self.assertTrue(event.isAccepted())
        self.assertTrue(page.method_orchestra.isSelected())
        self.assertEqual(requested[-1], ("apply_launch_method", ORCHESTRA_MODE))
        self.assertIs(self._app.focusWidget(), page.method_orchestra)


if __name__ == "__main__":
    unittest.main()
