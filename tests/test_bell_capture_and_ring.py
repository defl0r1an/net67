"""Все плашки попадают в колокольчик, а колокольчик качается на новое.

Плашки страниц показывались напрямую, мимо центра уведомлений, и в
колокольчик не попадали — гасли, и найти их было негде. А сам колокольчик
молча менял цифру.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402


def _wait(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()


class InfoBarCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        from ui.infobar_inbox_capture import install_infobar_capture

        install_infobar_capture()

    def _window(self):
        window = QWidget()
        window.window_notification_center = Mock()
        page = QWidget(window)
        window.resize(600, 400)
        self.addCleanup(window.deleteLater)
        return window, page

    def test_page_infobar_goes_to_bell_instead_of_screen(self) -> None:
        from qfluentwidgets import InfoBar

        window, page = self._window()
        bar = InfoBar.success(title="Пресет сохранён", content="Стандартный 1", parent=page, duration=100)

        # Плашек нет: забрана в колокольчик и на экран не вышла.
        self.assertFalse(bar.isVisible())
        record = window.window_notification_center.take_infobar
        record.assert_called_once()
        payload = record.call_args.args[0]
        self.assertEqual(payload["level"], "success")
        self.assertEqual(payload["title"], "Пресет сохранён")
        self.assertEqual(payload["content"], "Стандартный 1")
        self.assertTrue(payload["source"].startswith("infobar."))

    def test_error_level_is_kept(self) -> None:
        from qfluentwidgets import InfoBar

        window, page = self._window()
        InfoBar.error(title="Не записалось", content="нет прав", parent=page, duration=100)
        self.assertEqual(window.window_notification_center.take_infobar.call_args.args[0]["level"], "error")

    def test_center_own_infobar_is_not_recorded_twice(self) -> None:
        from qfluentwidgets import InfoBar

        from ui.infobar_inbox_capture import center_owned_infobar

        window, page = self._window()
        with center_owned_infobar():
            InfoBar.warning(title="t", content="c", parent=page, duration=100)
        window.window_notification_center.take_infobar.assert_not_called()

    def test_infobar_outside_a_window_with_bell_is_left_alone(self) -> None:
        from qfluentwidgets import InfoBar

        lonely = QWidget()
        lonely.show()
        self.addCleanup(lonely.deleteLater)
        bar = InfoBar.info(title="t", content="c", parent=lonely, duration=100)
        # Окну без колокольчика плашку показывают как раньше.
        self.assertTrue(bar.isVisible())

    def test_capture_is_installed_once(self) -> None:
        from ui.infobar_inbox_capture import install_infobar_capture

        self.assertFalse(install_infobar_capture())


class CenterRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_taken_error_lights_counter_and_rings(self) -> None:
        from ui.window_notification_center import WindowNotificationCenter

        center = WindowNotificationCenter.__new__(WindowNotificationCenter)
        from ui.notification_inbox import NotificationInbox

        center.inbox = NotificationInbox()
        center._bell = Mock()
        center._bell.set_state = Mock()

        taken = WindowNotificationCenter.take_infobar(
            center, {"level": "error", "title": "Не записалось", "content": "", "source": "infobar.HostsPage"}
        )

        self.assertTrue(taken)
        self.assertEqual(len(center.inbox.entries()), 1)
        self.assertEqual(center.inbox.unread_count(), 1)
        center._bell.ring.assert_called_once_with(strong=True)

    def test_without_bell_nothing_is_taken(self) -> None:
        from ui.notification_inbox import NotificationInbox
        from ui.window_notification_center import WindowNotificationCenter

        center = WindowNotificationCenter.__new__(WindowNotificationCenter)
        center.inbox = NotificationInbox()
        center._bell = None
        self.assertFalse(WindowNotificationCenter.take_infobar(center, {"level": "error", "title": "t"}))
        self.assertEqual(center.inbox.entries(), [])


class BellRingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _bell(self):
        from ui.widgets.notification_bell import NotificationBell

        for name in ("are_live_animations_enabled", "are_animations_enabled"):
            item = patch(f"ui.animation_policy.{name}", return_value=True)
            item.start()
            self.addCleanup(item.stop)
        bell = NotificationBell()
        bell.show()
        self.addCleanup(bell.deleteLater)
        # Первая отрисовка грузит шрифт значков и держит цикл событий дольше
        # кадра; в окне программы колокольчик давно отрисован.
        _wait(0.3)
        return bell

    def test_ring_swings_and_settles(self) -> None:
        bell = self._bell()
        bell.set_state(1, "error")
        bell.ring(strong=True)
        self.assertTrue(bell.is_ringing())
        _wait(0.08)
        self.assertGreater(abs(bell.ring_angle()), 0.5)
        self.assertGreater(bell.ring_scale(), 1.0)
        self.assertFalse(bell.grab().isNull())
        _wait(1.8)
        self.assertFalse(bell.is_ringing())
        self.assertEqual(bell.ring_angle(), 0.0)
        self.assertEqual(bell.ring_scale(), 1.0)

    def test_soft_ring_is_smaller_but_still_visible(self) -> None:
        """«Готово» качало на градус-другой: низ значка сдвигался на пиксель."""
        from ui.widgets.notification_bell import RING_SOFT_DEG, RING_STRONG_DEG, ring_angle

        peak_soft = max(abs(ring_angle(i / 200, RING_SOFT_DEG)) for i in range(201))
        peak_strong = max(abs(ring_angle(i / 200, RING_STRONG_DEG)) for i in range(201))
        self.assertLess(peak_soft, peak_strong)
        self.assertEqual(ring_angle(1.0, RING_STRONG_DEG), 0.0)
        # Значок 15 px: при 15 градусах его низ уходит на четыре пикселя —
        # меньше глаз на заголовке не ловит.
        self.assertGreater(peak_soft, 15.0)

    def test_ring_does_not_end_before_the_eye_gets_there(self) -> None:
        from ui.widgets.notification_bell import RING_MS, ring_angle

        self.assertGreaterEqual(RING_MS, 1200)
        # Через полсекунды колокольчик ещё заметно качается.
        late = max(abs(ring_angle(t / 100, 34.0)) for t in range(30, 45))
        self.assertGreater(late, 4.0)

    def test_every_notification_leaves_a_dot_until_the_list_is_opened(self) -> None:
        """«Готово» только качало: моргнул — и следа нет."""
        bell = self._bell()
        bell.set_state(0, "")
        self.assertFalse(bell.has_fresh())
        bell.ring(strong=False)
        self.assertTrue(bell.has_fresh())
        self.assertTrue(bell.is_ringing())
        bell.mark_seen()
        self.assertFalse(bell.has_fresh())

    def test_ring_while_hidden_plays_when_the_window_is_shown(self) -> None:
        """Уведомление пришло, пока окно в трее, — колокольчик молчал навсегда."""
        from ui.widgets.notification_bell import NotificationBell

        for name in ("are_live_animations_enabled", "are_animations_enabled"):
            item = patch(f"ui.animation_policy.{name}", return_value=True)
            item.start()
            self.addCleanup(item.stop)
        bell = NotificationBell()
        self.addCleanup(bell.deleteLater)
        bell.ring(strong=True)
        self.assertFalse(bell.is_ringing())
        self.assertTrue(bell.has_fresh())
        bell.show()
        _wait(0.8)
        self.assertTrue(bell.is_ringing())

    def test_no_swing_but_a_flash_when_live_animations_are_off(self) -> None:
        """Просьба убрать движение — не просьба убрать сигнал."""
        from ui.widgets.notification_bell import NotificationBell

        with (
            patch("ui.animation_policy.are_live_animations_enabled", return_value=False),
            patch("ui.animation_policy.are_animations_enabled", return_value=True),
        ):
            bell = NotificationBell()
            bell.show()
            self.addCleanup(bell.deleteLater)
            bell.ring(strong=True)
            self.assertTrue(bell.is_ringing())
            _wait(0.08)
            self.assertEqual(bell.ring_angle(), 0.0)
            self.assertEqual(bell.ring_scale(), 1.0)

    def test_nothing_moves_when_windows_animations_are_off(self) -> None:
        from ui.widgets.notification_bell import NotificationBell

        with (
            patch("ui.animation_policy.are_live_animations_enabled", return_value=False),
            patch("ui.animation_policy.are_animations_enabled", return_value=False),
        ):
            bell = NotificationBell()
            bell.show()
            self.addCleanup(bell.deleteLater)
            bell.ring(strong=True)
        self.assertFalse(bell.is_ringing())
        # Точка остаётся и здесь: это не движение.
        self.assertTrue(bell.has_fresh())


if __name__ == "__main__":
    unittest.main()
