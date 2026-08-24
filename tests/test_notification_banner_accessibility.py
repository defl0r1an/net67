from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from qfluentwidgets import TransparentToolButton

from ui.widgets.notification_banner import NotificationBanner


class NotificationBannerAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_notification_banner_has_screen_reader_text(self) -> None:
        banner = NotificationBanner()

        banner.show_error("Не удалось запустить Zapret", auto_hide_ms=0)

        self.assertEqual(banner.accessibleName(), "Ошибка: Не удалось запустить Zapret")
        self.assertEqual(banner.property("screenReaderStateText"), "Ошибка: Не удалось запустить Zapret")
        self.assertEqual(banner.message_label.property("screenReaderStateText"), "Ошибка: Не удалось запустить Zapret")
        self.assertIn("уведомление", banner.accessibleDescription().lower())

    def test_close_button_has_screen_reader_name_and_description(self) -> None:
        banner = NotificationBanner()
        close_buttons = banner.findChildren(TransparentToolButton)

        self.assertEqual(len(close_buttons), 1)
        self.assertEqual(close_buttons[0].accessibleName(), "Закрыть уведомление")
        self.assertEqual(close_buttons[0].property("screenReaderStateText"), "Закрыть уведомление")
        self.assertIn("скрывает", close_buttons[0].accessibleDescription().lower())

    def test_notification_icon_reads_type_not_only_color(self) -> None:
        banner = NotificationBanner()
        self.addCleanup(banner.deleteLater)

        banner.show_error("Не удалось запустить Zapret", auto_hide_ms=0)

        self.assertEqual(banner.icon_label.accessibleName(), "Иконка уведомления: Ошибка")
        self.assertEqual(
            banner.icon_label.property("screenReaderStateText"),
            "Иконка уведомления: Ошибка",
        )

        banner.show_success("Zapret запущен", auto_hide_ms=0)

        self.assertEqual(banner.icon_label.accessibleName(), "Иконка уведомления: Успешно")
        self.assertEqual(
            banner.icon_label.property("screenReaderStateText"),
            "Иконка уведомления: Успешно",
        )


if __name__ == "__main__":
    unittest.main()
