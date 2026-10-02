"""Окно обновления при запуске названо для диктора.

Раньше проверялось окошко в одну строку с кнопками «Скачать и
установить» и «Позже». Его сменило большое окно «Доступно обновление»;
требование прежнее — каждая кнопка говорит диктору, что она сделает.
"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

_APP = QApplication.instance() or QApplication(sys.argv)

from updater.ui.update_dialog import UpdateOfferDialog  # noqa: E402


class PostStartupHostAccessibilityTests(unittest.TestCase):
    def test_update_confirm_buttons_are_named_for_screen_reader(self) -> None:
        host = QWidget()
        self.addCleanup(host.deleteLater)
        dialog = UpdateOfferDialog(
            host,
            current_version="1.2.2",
            target_version="1.2.3",
            history=[{"version": "1.2.3", "notes": "- исправления", "is_new": True}],
            release_url="https://example.com/release",
        )
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.install_btn.accessibleName(), "Скачать и установить обновление")
        self.assertIn("Программа закроется и откроется снова", dialog.install_btn.accessibleDescription())
        self.assertEqual(dialog.later_btn.accessibleName(), "Отложить обновление")
        self.assertEqual(dialog.skip_btn.accessibleName(), "Пропустить версию")
        self.assertIn("больше не напоминать", dialog.skip_btn.accessibleDescription())
        self.assertEqual(dialog.browser_btn.accessibleName(), "Открыть в браузере")
        # Поле с изменениями читается диктору целиком: версия и её текст.
        self.assertIn("Версия 1.2.3", dialog.browser.accessibleName())
        self.assertIn("исправления", dialog.browser.accessibleName())
        self.assertIn("v1.2.3", dialog.subtitle_label.text())


if __name__ == "__main__":
    unittest.main()
