"""Панель колокольчика вырастает из него и уходит обратно.

Раньше панель появлялась и пропадала рывком, а щелчок по колокольчику
при открытой панели закрывал её и тут же открывал снова.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

from ui import popup_motion  # noqa: E402
from ui.popup_motion import PopupMotion, Spring  # noqa: E402


def _wait(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()


class SpringTests(unittest.TestCase):
    def test_critically_damped_spring_settles_without_overshoot(self) -> None:
        spring = Spring(0.0)
        spring.retarget(1.0)
        peak = 0.0
        for _ in range(120):
            spring.step(1 / 60)
            peak = max(peak, spring.value)
        self.assertTrue(spring.settled())
        self.assertLessEqual(peak, 1.0 + 1e-6)

    def test_retarget_keeps_value_and_velocity(self) -> None:
        """Развернули на полпути — движение не прыгает и не упирается в стену."""
        spring = Spring(0.0)
        spring.retarget(1.0)
        for _ in range(6):
            spring.step(1 / 60)
        value, velocity = spring.value, spring.velocity
        self.assertGreater(velocity, 0.0)

        spring.retarget(0.0)

        self.assertEqual(spring.value, value)
        self.assertEqual(spring.velocity, velocity)
        spring.step(1 / 60)
        # Ещё по инерции чуть вперёд, а не сразу назад.
        self.assertGreater(spring.value, value)

    def test_large_frame_gap_does_not_blow_up(self) -> None:
        spring = Spring(0.0)
        spring.retarget(1.0)
        spring.step(0.5)
        self.assertLess(abs(spring.value - 1.0), 0.05)


class _Panel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Уведомления"))
        self.resize(300, 160)


class PopupMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _motion(self, mode: str = "spring"):
        item = patch.object(popup_motion, "popup_motion_mode", return_value=mode)
        item.start()
        self.addCleanup(item.stop)
        owner = QWidget()
        self.addCleanup(owner.deleteLater)
        panel = _Panel()
        self.addCleanup(panel.deleteLater)
        panel.move(400, 300)
        return PopupMotion(owner), panel

    def test_panel_is_live_at_once_and_visible_when_ghost_lands(self) -> None:
        motion, panel = self._motion()

        motion.open(panel, QPoint(680, 300))

        # Панель уже на месте и ловит щелчки, видно пока призрак.
        self.assertTrue(panel.isVisible())
        self.assertEqual(panel.windowOpacity(), 0.0)
        self.assertTrue(motion.ghost().isVisible())
        self.assertEqual(motion.ghost().geometry(), panel.geometry())

        _wait(0.08)
        self.assertGreater(motion.progress, 0.0)
        self.assertLess(motion.progress, 1.0)

        _wait(1.2)
        self.assertFalse(motion.is_moving())
        self.assertEqual(panel.windowOpacity(), 1.0)
        self.assertFalse(motion.ghost().isVisible())

    def test_ghost_grows_from_anchor(self) -> None:
        motion, panel = self._motion()
        motion.open(panel, QPoint(680, 300))
        ghost = motion.ghost()
        self.assertEqual(ghost.origin.toPoint(), QPoint(680, 300) - panel.geometry().topLeft())
        self.assertFalse(ghost.grab().isNull())

    def test_close_mid_opening_reverses_from_where_it_is(self) -> None:
        motion, panel = self._motion()
        motion.open(panel, QPoint(680, 300))
        _wait(0.08)
        before = motion.progress

        panel.hide()
        motion.close(panel, QPoint(680, 300))

        self.assertEqual(motion.progress, before)
        self.assertTrue(motion.ghost().isVisible())
        _wait(1.2)
        self.assertEqual(motion.progress, 0.0)
        self.assertFalse(motion.ghost().isVisible())

    def test_no_motion_when_animations_are_off(self) -> None:
        motion, panel = self._motion("none")
        motion.open(panel, QPoint(680, 300))
        self.assertEqual(panel.windowOpacity(), 1.0)
        self.assertFalse(motion.is_moving())
        self.assertTrue(motion.ghost() is None or not motion.ghost().isVisible())

    def test_fade_without_scale_when_only_live_animations_are_off(self) -> None:
        motion, panel = self._motion("fade")
        motion.open(panel, QPoint(680, 300))
        self.assertFalse(motion.ghost().scale_motion)
        _wait(1.2)
        self.assertEqual(panel.windowOpacity(), 1.0)


class BellToggleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _center(self):
        from ui.widgets.notification_bell import NotificationBell
        from ui.window_notification_actions import WindowNotificationRuntimeActions
        from ui.window_notification_center import WindowNotificationCenter

        window = QWidget()
        self.addCleanup(window.deleteLater)
        noop = lambda *a, **k: None  # noqa: E731
        center = WindowNotificationCenter(
            window,
            startup_state=None,
            runtime_actions=WindowNotificationRuntimeActions(
                is_available=lambda: True,
                cancel_start_after_conflict_prompt=noop,
                execute_windivert_autofix=noop,
                install_windows_server_wlanapi=noop,
                prepare_launch_conflict_resolution=noop,
                continue_start_after_conflict_resolution=noop,
            ),
            create_open_url_worker=noop,
            create_notification_action_worker=noop,
            show_tray_notification=lambda *a: False,
            show_page=noop,
            is_window_visible=lambda: True,
            is_window_minimized=lambda: False,
        )
        bell = NotificationBell(window)
        center.attach_bell(bell)
        return center

    def test_click_that_closed_panel_on_bell_does_not_reopen_it(self) -> None:
        center = self._center()
        center.open_inbox_panel()
        first = center._inbox_panel

        center._on_inbox_panel_closing(first, True)
        center.open_inbox_panel()

        self.assertIs(center._inbox_panel, first)
        first.close()

    def test_next_click_opens_again(self) -> None:
        center = self._center()
        center.open_inbox_panel()
        first = center._inbox_panel
        center._on_inbox_panel_closing(first, True)
        center.open_inbox_panel()

        center.open_inbox_panel()

        self.assertIsNot(center._inbox_panel, first)
        center._inbox_panel.close()

    def test_closing_elsewhere_does_not_block_bell(self) -> None:
        center = self._center()
        center.open_inbox_panel()
        first = center._inbox_panel
        center._on_inbox_panel_closing(first, False)

        center.open_inbox_panel()

        self.assertIsNot(center._inbox_panel, first)
        center._inbox_panel.close()


if __name__ == "__main__":
    unittest.main()
