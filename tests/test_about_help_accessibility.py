"""Вкладка «Справка» после удаления ссылок автора.

Раньше здесь строилось восемь карточек: вики, руководство, инструкция для
Android, GitHub, Telegram, Mastodon, Bastyon и курс на YouTube. Все они
вели на ресурсы автора исходного проекта и удалены.

Теперь раздел собирается из branding.DOCS_URL и branding.SUPPORT_URL.
Пока они пусты, группа карточек не создаётся вовсе — поля виджетов
равны None.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, HyperlinkCard, PushSettingCard, SettingCardGroup

from ui.pages.about_page_help_build import build_about_page_help_content
from ui.theme import get_theme_tokens


def _build(parent: QWidget):
    layout = QVBoxLayout(parent)
    return build_about_page_help_content(
        layout,
        tr_fn=lambda _key, default: default,
        tokens=get_theme_tokens(),
        content_parent=parent,
        make_section_label=lambda text: QWidget(),
        hyperlink_card_cls=HyperlinkCard,
        push_setting_card_cls=PushSettingCard,
        setting_card_group_cls=SettingCardGroup,
        fluent_icon=FluentIcon,
        on_open_forum=lambda: None,
        on_open_telegram_news=lambda: None,
    )


class AboutHelpAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_author_link_cards_are_gone(self) -> None:
        widgets = _build(QWidget())

        for removed in (
            "telegram_card",
            "mastodon_card",
            "bastyon_card",
            "github_card",
            "android_card",
        ):
            self.assertIsNone(
                getattr(widgets, removed, None),
                f"карточка {removed} должна быть удалена вместе со ссылками автора",
            )

    def test_news_section_is_not_built(self) -> None:
        """Раздел новостей состоял только из каналов автора."""
        widgets = _build(QWidget())

        self.assertIsNone(widgets.news_group)

    def test_docs_section_follows_branding_links(self) -> None:
        """Пустые DOCS_URL и SUPPORT_URL не должны рождать пустую группу."""
        from branding import DOCS_URL, SUPPORT_URL

        widgets = _build(QWidget())

        if DOCS_URL or SUPPORT_URL:
            self.assertIsNotNone(widgets.docs_group)
        else:
            self.assertIsNone(widgets.docs_group)

    def test_motto_block_is_still_built(self) -> None:
        """Блок с названием продукта остаётся единственным содержимым."""
        widgets = _build(QWidget())

        self.assertIsNotNone(widgets.motto_wrap)


if __name__ == "__main__":
    unittest.main()
