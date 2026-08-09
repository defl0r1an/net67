from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, PushButton, SettingCardGroup

from dns.ui.force_dns_build import build_force_dns_card_ui
from dns.ui.force_dns_ui import update_dns_selection_block_state
from ui.fluent_widgets import (
    enable_setting_card_group_auto_height,
    insert_widget_into_setting_card_group,
)
from ui.theme import get_theme_tokens
from ui.widgets.win11_controls import Win11ToggleRow


class ForceDnsBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_reset_button_uses_fluent_icon_keyword_for_plain_push_button(self) -> None:
        parent = QWidget()
        added_widgets = []
        section_titles = []

        _active, widgets = build_force_dns_card_ui(
            parent=parent,
            content_parent=parent,
            add_section_title_fn=lambda **kwargs: section_titles.append(kwargs),
            tr_fn=lambda _key, default: default,
            add_widget_fn=added_widgets.append,
            get_theme_tokens_fn=get_theme_tokens,
            get_force_dns_status_fn=lambda: False,
            setting_card_group_cls=SettingCardGroup,
            caption_label_cls=CaptionLabel,
            action_button_cls=PushButton,
            win11_toggle_row_cls=Win11ToggleRow,
            qwidget_cls=QWidget,
            qvbox_layout_cls=QVBoxLayout,
            qhbox_layout_cls=QHBoxLayout,
            qt_namespace=Qt,
            insert_widget_into_setting_card_group_fn=insert_widget_into_setting_card_group,
            enable_setting_card_group_auto_height_fn=enable_setting_card_group_auto_height,
            on_toggle=lambda: None,
            on_confirm_reset=lambda: None,
        )

        self.assertEqual(1, len(added_widgets))
        self.assertEqual([], section_titles)
        self.assertFalse(widgets.reset_button.icon().isNull())

    def test_force_dns_actions_include_custom_dns_button_without_toggle_row(self) -> None:
        parent = QWidget()
        custom_clicks: list[bool] = []

        _active, widgets = build_force_dns_card_ui(
            parent=parent,
            content_parent=parent,
            add_section_title_fn=lambda **_kwargs: None,
            tr_fn=lambda _key, default: default,
            add_widget_fn=lambda _widget: None,
            get_theme_tokens_fn=get_theme_tokens,
            get_force_dns_status_fn=lambda: False,
            setting_card_group_cls=SettingCardGroup,
            caption_label_cls=CaptionLabel,
            action_button_cls=PushButton,
            win11_toggle_row_cls=Win11ToggleRow,
            qwidget_cls=QWidget,
            qvbox_layout_cls=QVBoxLayout,
            qhbox_layout_cls=QHBoxLayout,
            qt_namespace=Qt,
            insert_widget_into_setting_card_group_fn=insert_widget_into_setting_card_group,
            enable_setting_card_group_auto_height_fn=enable_setting_card_group_auto_height,
            on_toggle=lambda: None,
            on_confirm_reset=lambda: None,
            on_custom_dns=lambda: custom_clicks.append(True),
        )

        self.assertIsNone(widgets.force_button)
        self.assertEqual(widgets.reset_button.text(), "Вернуть DNS автоматически")
        self.assertEqual(widgets.custom_button.text(), "Добавить свой DNS")
        self.assertEqual(widgets.card.actions_layout.count(), 2)
        self.assertFalse(hasattr(widgets, "toggle"))
        widgets.custom_button.click()
        self.assertEqual(custom_clicks, [True])

    def test_manual_dns_actions_do_not_show_force_button_when_old_state_is_true(self) -> None:
        parent = QWidget()

        _active, widgets = build_force_dns_card_ui(
            parent=parent,
            content_parent=parent,
            add_section_title_fn=lambda **_kwargs: None,
            tr_fn=lambda _key, default: default,
            add_widget_fn=lambda _widget: None,
            get_theme_tokens_fn=get_theme_tokens,
            get_force_dns_status_fn=lambda: True,
            setting_card_group_cls=SettingCardGroup,
            caption_label_cls=CaptionLabel,
            action_button_cls=PushButton,
            win11_toggle_row_cls=Win11ToggleRow,
            qwidget_cls=QWidget,
            qvbox_layout_cls=QVBoxLayout,
            qhbox_layout_cls=QHBoxLayout,
            qt_namespace=Qt,
            insert_widget_into_setting_card_group_fn=insert_widget_into_setting_card_group,
            enable_setting_card_group_auto_height_fn=enable_setting_card_group_auto_height,
            on_toggle=lambda: None,
            on_confirm_reset=lambda: None,
            on_custom_dns=lambda: None,
        )

        self.assertFalse(_active)
        self.assertIsNone(widgets.force_button)
        self.assertEqual(widgets.card.actions_layout.count(), 2)

    def test_reset_button_has_screen_reader_text(self) -> None:
        parent = QWidget()

        _active, widgets = build_force_dns_card_ui(
            parent=parent,
            content_parent=parent,
            add_section_title_fn=lambda **_kwargs: None,
            tr_fn=lambda _key, default: default,
            add_widget_fn=lambda _widget: None,
            get_theme_tokens_fn=get_theme_tokens,
            get_force_dns_status_fn=lambda: False,
            setting_card_group_cls=SettingCardGroup,
            caption_label_cls=CaptionLabel,
            action_button_cls=PushButton,
            win11_toggle_row_cls=Win11ToggleRow,
            qwidget_cls=QWidget,
            qvbox_layout_cls=QVBoxLayout,
            qhbox_layout_cls=QHBoxLayout,
            qt_namespace=Qt,
            insert_widget_into_setting_card_group_fn=insert_widget_into_setting_card_group,
            enable_setting_card_group_auto_height_fn=enable_setting_card_group_auto_height,
            on_toggle=lambda: None,
            on_confirm_reset=lambda: None,
            on_custom_dns=lambda: None,
        )

        self.assertIsNone(widgets.force_button)
        self.assertEqual(widgets.reset_button.accessibleName(), "Вернуть DNS автоматически")
        self.assertEqual(widgets.reset_button.property("screenReaderStateText"), "Вернуть DNS автоматически")
        self.assertIn("DNS будет снова получаться автоматически", widgets.reset_button.accessibleDescription())
        self.assertEqual(widgets.custom_button.accessibleName(), "Добавить свой DNS")
        self.assertEqual(widgets.custom_button.property("screenReaderStateText"), "Добавить свой DNS")
        self.assertIn("Открывает окно", widgets.custom_button.accessibleDescription())

    def test_manual_dns_actions_ignore_old_force_active_state(self) -> None:
        parent = QWidget()

        _active, widgets = build_force_dns_card_ui(
            parent=parent,
            content_parent=parent,
            add_section_title_fn=lambda **_kwargs: None,
            tr_fn=lambda _key, default: default,
            add_widget_fn=lambda _widget: None,
            get_theme_tokens_fn=get_theme_tokens,
            get_force_dns_status_fn=lambda: True,
            setting_card_group_cls=SettingCardGroup,
            caption_label_cls=CaptionLabel,
            action_button_cls=PushButton,
            win11_toggle_row_cls=Win11ToggleRow,
            qwidget_cls=QWidget,
            qvbox_layout_cls=QVBoxLayout,
            qhbox_layout_cls=QHBoxLayout,
            qt_namespace=Qt,
            insert_widget_into_setting_card_group_fn=insert_widget_into_setting_card_group,
            enable_setting_card_group_auto_height_fn=enable_setting_card_group_auto_height,
            on_toggle=lambda: None,
            on_confirm_reset=lambda: None,
            on_custom_dns=lambda: None,
        )

        self.assertFalse(_active)
        self.assertIsNone(widgets.force_button)

    def test_force_dns_opacity_is_not_applied_twice_to_nested_custom_dns_row(self) -> None:
        dns_container = QWidget()
        custom_row = QWidget(dns_container)

        update_dns_selection_block_state(
            blocked=True,
            dns_cards_container=dns_container,
            custom_card=custom_row,
        )

        self.assertIsNotNone(dns_container.graphicsEffect())
        self.assertIsNone(custom_row.graphicsEffect())


if __name__ == "__main__":
    unittest.main()
