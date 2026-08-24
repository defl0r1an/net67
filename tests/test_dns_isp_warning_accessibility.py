from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class DnsIspWarningAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_warning_exposes_text_and_actions_to_screen_reader(self) -> None:
        from dns.ui.isp_warning import build_isp_warning_ui

        parent = QWidget()
        plan = SimpleNamespace(
            title="Провайдер подменяет DNS",
            content="Текущий DNS может мешать обходу блокировок.",
            action_text="Выбрать безопасный DNS",
            dismiss_text="Не показывать",
        )

        widgets = build_isp_warning_ui(
            parent=parent,
            plan=plan,
            qframe_cls=QFrame,
            qvbox_layout_cls=QVBoxLayout,
            qhbox_layout_cls=QHBoxLayout,
            qlabel_cls=QLabel,
            qpush_button_cls=QPushButton,
            qt_namespace=Qt,
            on_accept=lambda: None,
            on_dismiss=lambda: None,
        )

        self.assertEqual(
            widgets.frame.property("screenReaderStateText"),
            "Предупреждение DNS: Провайдер подменяет DNS. Текущий DNS может мешать обходу блокировок.",
        )
        self.assertEqual(
            widgets.title.property("screenReaderStateText"),
            "Заголовок предупреждения DNS: Провайдер подменяет DNS",
        )
        self.assertEqual(
            widgets.content.property("screenReaderStateText"),
            "Описание предупреждения DNS: Текущий DNS может мешать обходу блокировок.",
        )
        self.assertEqual(widgets.accept_button.accessibleName(), "Выбрать безопасный DNS")
        self.assertIn("Применяет", widgets.accept_button.accessibleDescription())
        self.assertEqual(widgets.dismiss_button.accessibleName(), "Не показывать")
        self.assertIn("Скрывает предупреждение DNS", widgets.dismiss_button.accessibleDescription())


if __name__ == "__main__":
    unittest.main()
