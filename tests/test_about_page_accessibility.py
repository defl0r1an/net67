"""Страница «О программе» после удаления подписки и раздела автора.

Удалены: вкладка «Zapret KVN», блок «Подписка» с кнопками Premium и KVN,
секция «Обучение» со ссылками на YouTube-канал автора.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.pages.about_page_about_build import build_about_page_about_content
from ui.pages.about_page_tabs_build import build_about_page_tabs
from ui.theme import get_theme_tokens


def _build_about(parent: QWidget):
    layout = QVBoxLayout(parent)
    return build_about_page_about_content(
        layout,
        tr_fn=lambda _key, default: default,
        tokens=get_theme_tokens(),
        content_parent=parent,
        app_version="1.0.0",
        make_section_label=lambda text: QWidget(),
        on_open_updates=lambda: None,
    )


class AboutPageAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_about_tabs_read_current_section_for_screen_reader(self) -> None:
        widgets = build_about_page_tabs(
            tr_fn=lambda _key, default: default,
            on_switch_tab=lambda _index: None,
        )
        self.addCleanup(widgets.stacked_widget.deleteLater)

        self.assertEqual(
            widgets.tabs_pivot.accessibleName(),
            "Вкладки страницы о программе, выбрано: О программе",
        )
        # Вкладка «Zapret KVN» удалена вместе с разделом о проекте автора.
        self.assertIn("О программе или Справка", widgets.tabs_pivot.accessibleDescription())
        self.assertNotIn("kvn", widgets.tabs_pivot.items)
        self.assertNotIn("support", widgets.tabs_pivot.items)
        self.assertEqual(
            widgets.tabs_pivot.items["about"].accessibleName(),
            "Вкладки страницы о программе: О программе, выбрано",
        )

        widgets.tabs_pivot.setCurrentItem("help")

        self.assertEqual(
            widgets.tabs_pivot.accessibleName(),
            "Вкладки страницы о программе, выбрано: Справка",
        )
        self.assertEqual(
            widgets.tabs_pivot.items["help"].accessibleName(),
            "Вкладки страницы о программе: Справка, выбрано",
        )

    def test_removed_sections_are_absent(self) -> None:
        """Подписка, кнопки Premium и KVN, раздел «Обучение» удалены."""
        widgets = _build_about(QWidget())

        for removed in (
            "premium_btn",
            "kvn_btn",
            "sub_status_label",
            "sub_status_icon",
            "sub_desc_label",
            "about_section_subscription_label",
            "course_group",
            "youtube_course_card",
            "youtube_playlist_card",
        ):
            self.assertIsNone(getattr(widgets, removed, None), removed)

    def test_version_block_is_still_built(self) -> None:
        widgets = _build_about(QWidget())

        self.assertIsNotNone(widgets.update_btn)
        self.assertIsNotNone(widgets.about_version_value_label)
        self.assertIsNotNone(widgets.about_app_name_label)


if __name__ == "__main__":
    unittest.main()
