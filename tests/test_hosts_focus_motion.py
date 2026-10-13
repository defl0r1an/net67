"""Переход к группе плиток не выбирает профили и не оставляет анимацию жить."""

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from hosts.ui.services_tiles import HostsChoice, HostsTile, HostsTilesGrid


class HostsFocusMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.grid = HostsTilesGrid()
        self.grid.resize(960, 300)
        self.keys = ("Gemini AI", "Claude", "ChatGPT & Sora (OpenAI)")
        self.grid.set_tiles([HostsTile(kind="tile", key=name, title=name,
                            choices=(HostsChoice("geo", "GeoHide", "fa5s.globe", "#888888"),), selected="geo")
                            for name in self.keys])
        self.grid.show()
        self.app.processEvents()
        self.addCleanup(self.grid.deleteLater)
        self.addCleanup(self.grid.hide)

    def test_three_tiles_move_and_glow_without_profile_changes(self):
        activated = Mock()
        chosen = Mock()
        self.grid.activated.connect(activated)
        self.grid.profile_chosen.connect(chosen)
        with patch("hosts.ui.services_tiles.are_live_animations_enabled", return_value=True):
            self.assertTrue(self.grid.focus_tiles(self.keys))
            self.grid._focus_anim.setCurrentTime(190)
            self.assertEqual(set(self.grid._focus_values), set(self.keys))
            for strength, lift in self.grid._focus_values.values():
                self.assertGreater(strength, 0.8)
                self.assertGreater(lift, 4.0)
                self.assertLessEqual(lift, 6.0)
            self.grid._focus_anim.setCurrentTime(self.grid.FOCUS_MS)
        self.assertFalse(self.grid._focus_values)
        self.assertEqual([tile.selected for tile in self.grid.tiles()], ["geo"] * 3)
        activated.assert_not_called()
        chosen.assert_not_called()

    def test_repeat_continues_from_current_position_and_hide_stops_motion(self):
        with patch("hosts.ui.services_tiles.are_live_animations_enabled", return_value=True):
            self.grid.focus_tiles(self.keys)
            self.grid._focus_anim.setCurrentTime(160)
            previous = dict(self.grid._focus_values)
            self.grid.focus_tiles(self.keys)
            self.assertEqual(self.grid._focus_values, previous)
            self.grid.hide()
        self.assertFalse(self.grid._focus_values)
        self.assertEqual(self.grid._focus_anim.state().name, "Stopped")

    def test_disabled_motion_keeps_group_feedback_without_lift(self):
        with patch("hosts.ui.services_tiles.are_live_animations_enabled", return_value=False):
            self.grid.focus_tiles(self.keys)
        self.assertEqual(self.grid._focus_values, {key: (1.0, 0.0) for key in self.keys})
        self.assertEqual(self.grid._focus_anim.state().name, "Stopped")

    def test_visible_rect_in_viewport_and_lazy_paint(self):
        from PyQt6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.resize(800, 400)
        scroll.setWidget(self.grid)
        scroll.show()
        self.app.processEvents()
        self.addCleanup(scroll.deleteLater)
        self.addCleanup(scroll.hide)

        visible = self.grid._visible_rect_in_viewport()
        self.assertTrue(visible.isValid())
        self.assertGreater(visible.width(), 0)
        self.assertGreater(visible.height(), 0)

