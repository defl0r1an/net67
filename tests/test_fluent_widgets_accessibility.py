from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication


class FluentWidgetsAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_settings_card_title_has_screen_reader_state(self) -> None:
        from ui.fluent_widgets import SettingsCard

        card = SettingsCard("DNS Серверы")
        self.addCleanup(card.deleteLater)

        self.assertEqual(card.property("screenReaderStateText"), "Раздел настроек: DNS Серверы")
        self.assertEqual(card.accessibleName(), "Раздел настроек: DNS Серверы")
        self.assertEqual(card._title_label.property("screenReaderStateText"), "Раздел настроек: DNS Серверы")

    def test_settings_card_set_title_updates_screen_reader_state(self) -> None:
        from ui.fluent_widgets import SettingsCard

        card = SettingsCard()
        self.addCleanup(card.deleteLater)

        card.set_title("Диагностика")

        self.assertEqual(card.property("screenReaderStateText"), "Раздел настроек: Диагностика")
        self.assertEqual(card.accessibleName(), "Раздел настроек: Диагностика")
        self.assertEqual(card._title_label.property("screenReaderStateText"), "Раздел настроек: Диагностика")

        card.set_title("Инструменты")

        self.assertEqual(card.property("screenReaderStateText"), "Раздел настроек: Инструменты")
        self.assertEqual(card._title_label.property("screenReaderStateText"), "Раздел настроек: Инструменты")

    def test_settings_row_title_and_description_have_screen_reader_state(self) -> None:
        from ui.fluent_widgets import SettingsRow

        row = SettingsRow("fa5s.palette", "Цвет акцента", "Открывает выбор цвета")
        self.addCleanup(row.deleteLater)

        expected = "Настройка: Цвет акцента. Открывает выбор цвета"
        self.assertEqual(row.property("screenReaderStateText"), expected)
        self.assertEqual(row.accessibleName(), expected)
        self.assertEqual(row.accessibleDescription(), "Открывает выбор цвета")
        self.assertEqual(row._title_label.property("screenReaderStateText"), "Настройка: Цвет акцента")
        self.assertEqual(row._desc_label.property("screenReaderStateText"), "Описание настройки: Открывает выбор цвета")

    def test_settings_row_updates_screen_reader_state_after_text_changes(self) -> None:
        from ui.fluent_widgets import SettingsRow

        row = SettingsRow("fa5s.palette", "Цвет акцента", "Открывает выбор цвета")
        self.addCleanup(row.deleteLater)

        row.set_title("Интенсивность")
        row.set_description("Меняет силу эффекта")

        expected = "Настройка: Интенсивность. Меняет силу эффекта"
        self.assertEqual(row.property("screenReaderStateText"), expected)
        self.assertEqual(row.accessibleName(), expected)
        self.assertEqual(row.accessibleDescription(), "Меняет силу эффекта")
        self.assertEqual(row._title_label.property("screenReaderStateText"), "Настройка: Интенсивность")
        self.assertEqual(row._desc_label.property("screenReaderStateText"), "Описание настройки: Меняет силу эффекта")

    def test_semantic_notice_reads_warning_text_for_screen_reader(self) -> None:
        from ui.fluent_widgets import SemanticNotice

        notice = SemanticNotice("Проверьте параметры перед запуском", tone="warning")
        self.addCleanup(notice.deleteLater)

        expected = "Предупреждение: Проверьте параметры перед запуском"
        self.assertEqual(notice.accessibleName(), expected)
        self.assertEqual(notice.property("screenReaderStateText"), expected)
        self.assertEqual(notice._text_label.property("screenReaderStateText"), expected)

        notice.setText("Изменения применятся после перезапуска")

        expected = "Предупреждение: Изменения применятся после перезапуска"
        self.assertEqual(notice.accessibleName(), expected)
        self.assertEqual(notice.property("screenReaderStateText"), expected)
        self.assertEqual(notice._text_label.property("screenReaderStateText"), expected)

    def test_premium_badge_reads_text_for_screen_reader(self) -> None:
        from ui.fluent_widgets import build_premium_badge

        badge = build_premium_badge("Premium")
        self.addCleanup(badge.deleteLater)

        self.assertEqual(badge.accessibleName(), "Метка Premium: Premium")
        self.assertEqual(badge.property("screenReaderStateText"), "Метка Premium: Premium")


if __name__ == "__main__":
    unittest.main()
