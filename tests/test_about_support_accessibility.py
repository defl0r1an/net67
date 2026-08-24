"""Страница поддержки после удаления каналов автора.

Было три карточки: GitHub Discussions в репозитории автора, его Telegram
и Discord. Остался один канал обращения, и тот строится только если в
branding.py задан SUPPORT_URL или SUPPORT_EMAIL.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.pages.about_page_support_build import build_about_page_support_content
from ui.theme import get_theme_tokens


def _build(parent: QWidget):
    layout = QVBoxLayout(parent)
    return build_about_page_support_content(
        layout,
        tr_fn=lambda _key, default: default,
        content_parent=parent,
        tokens=get_theme_tokens(),
        on_open_discussions=lambda: None,
        on_open_telegram=lambda: None,
        on_open_discord=lambda: None,
    )


class AboutSupportAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_author_community_cards_are_gone(self) -> None:
        widgets = _build(QWidget())

        self.assertIsNone(widgets.telegram_card)
        self.assertIsNone(widgets.discord_card)
        self.assertIsNone(widgets.community_group)

    def test_support_card_follows_branding_settings(self) -> None:
        from branding import SUPPORT_EMAIL, SUPPORT_URL

        widgets = _build(QWidget())

        if SUPPORT_URL or SUPPORT_EMAIL:
            self.assertIsNotNone(widgets.discussions_card)
            self.assertTrue(widgets.discussions_card.accessibleName())
        else:
            self.assertIsNone(widgets.discussions_card)
            self.assertIsNone(widgets.discussions_group)

    def test_build_does_not_crash_without_links(self) -> None:
        """Пустая страница поддержки — допустимое состояние, а не ошибка."""
        widgets = _build(QWidget())

        self.assertIsNotNone(widgets)


if __name__ == "__main__":
    unittest.main()
