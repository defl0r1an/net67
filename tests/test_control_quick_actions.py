from __future__ import annotations

import inspect
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QPixmap
from PyQt6.QtWidgets import QApplication, QGraphicsOpacityEffect, QVBoxLayout, QWidget

import presets.ui.control.zapret2.sections_build as zapret2_sections
import ui.widgets.motion_icon as motion_module
import ui.widgets.tile_grid as tile_module
from app.ui_texts import tr as tr_catalog
from presets.ui.control.quick_actions import (
    QUICK_ACTION_MAX_WIDTH,
    apply_quick_actions_language,
    build_quick_actions,
    quick_action_specs,
)
from presets.ui.control.simple_view import HIDDEN_IN_SIMPLE_VIEW
from ui.widgets.motion_icon import GESTURE_BOUNCE

KEYS = ["tour", "bypass_tour", "internet_cleanup", "folder", "docs", "updates", "source"]


def _tr(language: str):
    return lambda key, default: tr_catalog(key, language=language, default=default)


class QuickActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        for module in (tile_module, motion_module):
            patcher = mock.patch.object(module, "are_live_animations_enabled", return_value=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.calls: list[str] = []
        self.host = QWidget()
        self.addCleanup(self.host.deleteLater)
        self.widgets = build_quick_actions(
            tr_fn=_tr("ru"),
            text_prefix="page.winws2_control",
            handlers={key: (lambda key=key: self.calls.append(key)) for key in KEYS},
            parent=self.host,
        )
        layout = QVBoxLayout(self.host)
        layout.addWidget(self.widgets.title_label)
        layout.addWidget(self.widgets.grid)

    def _tiles(self):
        return [self.widgets.tiles[key] for key in KEYS]

    def test_every_tile_runs_its_own_action(self) -> None:
        for tile in self._tiles():
            tile.click()

        self.assertEqual(self.calls, KEYS)

    def test_tiles_are_buttons_for_keyboard_and_screen_reader(self) -> None:
        tile = self.widgets.tiles["source"]

        self.assertEqual(tile.focusPolicy(), Qt.FocusPolicy.StrongFocus)
        self.assertEqual(tile.accessibleName(), "Открыть исходный код net67 на GitHub")
        self.assertEqual(tile.property("screenReaderStateText"), "Открыть исходный код net67 на GitHub")
        self.assertIn("GitHub", tile.accessibleDescription())
        self.assertIn("Enter или Пробел", tile.accessibleDescription())

        tile.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(self.calls, ["source"])

    def test_busy_tile_fades_and_ignores_clicks(self) -> None:
        tile = self.widgets.tiles["internet_cleanup"]
        tile.setEnabled(False)

        tile.click()
        self.assertEqual(self.calls, [])
        self.assertIsInstance(tile.graphicsEffect(), QGraphicsOpacityEffect)
        self.assertEqual(tile.accessibleName(), "Сбросить сеть Windows, недоступно")

        tile.setEnabled(True)
        self.assertIsNone(tile.graphicsEffect())
        self.assertEqual(tile.accessibleName(), "Сбросить сеть Windows")
        tile.click()
        self.assertEqual(self.calls, ["internet_cleanup"])

    def test_language_switch_retranslates_tiles_and_title(self) -> None:
        apply_quick_actions_language(
            tr_fn=_tr("en"),
            text_prefix="page.winws2_control",
            title_label=self.widgets.title_label,
            tiles=self.widgets.tiles,
        )

        tour = self.widgets.tiles["tour"]
        self.assertEqual(self.widgets.title_label.text(), "Quick actions")
        self.assertEqual(tour.title(), "How to use the app")
        self.assertEqual(tour.accessibleName(), "Show the guided tour")
        self.assertEqual(self.widgets.tiles["source"].title(), "Source code")

    def test_wide_window_keeps_tiles_equal_and_capped(self) -> None:
        # Окно владельца — 1900 пикселей: все семь в ряд, не шире предела.
        self.host.resize(1900, 600)
        self.host.show()
        QApplication.processEvents()
        grid = self.widgets.grid

        self.assertEqual(grid.columns(), 7)
        self.assertEqual(len({tile.width() for tile in self._tiles()}), 1)
        self.assertLessEqual(self._tiles()[0].width(), QUICK_ACTION_MAX_WIDTH)
        self.assertEqual(len({tile.height() for tile in self._tiles()}), 1)

    def test_narrow_window_wraps_with_aligned_edges(self) -> None:
        self.host.resize(820, 700)
        self.host.show()
        QApplication.processEvents()
        grid = self.widgets.grid
        tiles = self.widgets.tiles

        self.assertEqual(grid.columns(), 4)
        self.assertEqual(tiles["docs"].x(), tiles["tour"].x())
        self.assertEqual(tiles["docs"].width(), tiles["tour"].width())

    def test_hidden_reset_tile_gives_its_place_to_neighbours(self) -> None:
        self.host.resize(1900, 600)
        self.host.show()
        QApplication.processEvents()
        tiles = self.widgets.tiles

        tiles["internet_cleanup"].setVisible(False)
        QApplication.processEvents()

        # «Открыть папку» встала сразу за «Как работает обход» — на место скрытой.
        bypass = tiles["bypass_tour"]
        self.assertEqual(tiles["folder"].x(), bypass.x() + bypass.width() + 12)

    def test_narrow_tile_grows_taller_for_wrapped_text(self) -> None:
        tile = self.widgets.tiles["internet_cleanup"]
        self.assertTrue(tile.hasHeightForWidth())
        self.assertGreater(tile.heightForWidth(170), tile.heightForWidth(420))

    def test_hover_bounces_icon_and_tile_glows_with_its_own_color(self) -> None:
        self.host.resize(1200, 600)
        self.host.show()
        QApplication.processEvents()
        tile = self.widgets.tiles["folder"]

        tile.enterEvent(None)

        self.assertEqual(tile._icon.gesture(), GESTURE_BOUNCE)
        self.assertEqual(tile.accent_color(), QColor("#f5c04d"))
        self.assertLess(tile.chevron_center_y(), tile.height() / 2)

        tile._hover_t = 1.0
        image = QPixmap(tile.size())
        image.fill(QColor(0, 0, 0, 0))
        tile.render(image)
        self.assertFalse(image.isNull())

    def test_specs_order_and_no_connection_test(self) -> None:
        # «Тест соединения» не взят: проверку сети у net67 делает BlockCheck.
        specs = {spec.key: spec for spec in quick_action_specs("page.winws2_control")}
        self.assertEqual(list(specs), KEYS)
        self.assertTrue(specs["folder"].accessible_name[0].startswith("page.winws2_control"))

    def test_icon_is_darker_in_light_theme_and_follows_theme_switch(self) -> None:
        from qfluentwidgets import Theme, setTheme

        tile = self.widgets.tiles["tour"]
        tile._start_icon()
        self.addCleanup(setTheme, Theme.DARK)

        setTheme(Theme.DARK)
        self.assertEqual(tile.shown_icon_color(), QColor("#b39ddb"))
        setTheme(Theme.LIGHT)
        light = tile.shown_icon_color()
        self.assertLess(light.lightness(), QColor("#b39ddb").lightness())
        tile._apply_icon(force=True)
        self.assertFalse(tile._icon.pixmap().isNull())

    def test_simple_view_hides_only_the_reset_tile(self) -> None:
        self.assertIn("internet_cleanup_card", HIDDEN_IN_SIMPLE_VIEW)
        for name in ("onboarding_tour_card", "bypass_tour_card", "folder_card", "docs_card"):
            self.assertNotIn(name, HIDDEN_IN_SIMPLE_VIEW)


class ProgramSettingsGroupTests(unittest.TestCase):
    def test_state_media_toggle_lives_with_other_windows_blocks(self) -> None:
        source = inspect.getsource(zapret2_sections)
        self.assertIn("program_settings_card.addSettingCard(state_media_block_toggle)", source)
        self.assertNotIn("extra_card", source)


if __name__ == "__main__":
    unittest.main()
