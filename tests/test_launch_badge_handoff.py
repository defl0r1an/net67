"""Метка в заголовке — продолжение главного круга, а не второй выключатель.

Пока круг на главной виден, метки нет; ушёл круг — прокруткой или
переходом в другой раздел — и он улетает в метку. Вернулся — метка
улетает обратно в него тем же путём.
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

from PyQt6.QtCore import QRectF, Qt  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from shell import launch_badge_handoff as handoff  # noqa: E402


def _wait(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)


class PureRulesTests(unittest.TestCase):
    def test_visible_fraction(self) -> None:
        view = QRectF(0, 100, 400, 300)
        self.assertEqual(handoff.visible_fraction(QRectF(10, 150, 80, 80), view), 1.0)
        self.assertAlmostEqual(handoff.visible_fraction(QRectF(10, 60, 80, 80), view), 0.5)
        self.assertEqual(handoff.visible_fraction(QRectF(10, 0, 80, 80), view), 0.0)

    def test_badge_only_when_circle_is_gone_with_hysteresis(self) -> None:
        wanted = handoff.badge_wanted
        self.assertTrue(wanted(0.9, page_current=False, shown_now=False))
        self.assertFalse(wanted(0.5, page_current=True, shown_now=False))
        self.assertTrue(wanted(0.0, page_current=True, shown_now=False))
        # Показалась кромка круга — метка ещё держится, иначе край
        # прокрутки гонял бы снимок туда-обратно.
        self.assertTrue(wanted(0.02, page_current=True, shown_now=True))
        self.assertFalse(wanted(0.02, page_current=True, shown_now=False))
        self.assertFalse(wanted(0.2, page_current=True, shown_now=True))

    def test_clip_opens_from_page_edge_to_window_top(self) -> None:
        self.assertEqual(handoff.clip_top(120.0, 0.0), 120.0)
        self.assertEqual(handoff.clip_top(120.0, 1.0), 0.0)
        self.assertEqual(handoff.clip_top(120.0, 0.5), 60.0)

    def test_crossfade_is_monotonic_and_ends_on_the_badge(self) -> None:
        values = [handoff.crossfade(i / 20) for i in range(21)]
        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[-1], 1.0)
        self.assertEqual(values, sorted(values))

    def test_lerp_rect_ends(self) -> None:
        a, b = QRectF(0, 200, 88, 88), QRectF(900, 6, 120, 26)
        self.assertEqual(handoff.lerp_rect(a, b, 0.0), a)
        self.assertEqual(handoff.lerp_rect(a, b, 1.0), b)


class _Window(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.resize(900, 500)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.titleBar = QWidget(self)
        self.titleBar.setFixedHeight(40)
        self.titleBar.hBoxLayout = QHBoxLayout(self.titleBar)
        self.titleBar.hBoxLayout.addStretch(1)
        self.notificationBell = QPushButton("колокольчик", self.titleBar)
        self.titleBar.hBoxLayout.addWidget(self.notificationBell)
        outer.addWidget(self.titleBar)
        self.stackedWidget = QStackedWidget(self)
        outer.addWidget(self.stackedWidget, 1)
        self.page = QScrollArea()
        self.page.setWidgetResizable(True)
        content = QWidget()
        column = QVBoxLayout(content)
        self.circle = QPushButton("●")
        self.circle.setFixedSize(88, 88)
        column.addWidget(self.circle, 0, Qt.AlignmentFlag.AlignHCenter)
        tall = QWidget()
        tall.setFixedHeight(1600)
        column.addWidget(tall)
        self.page.setWidget(content)
        self.other = QWidget()
        self.stackedWidget.addWidget(self.page)
        self.stackedWidget.addWidget(self.other)


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _bind(self, mode: str):
        from ui.launch_title_badge import LaunchTitleBadge

        window = _Window()
        self.addCleanup(window.deleteLater)
        badge = LaunchTitleBadge(window.titleBar, language_provider=lambda: None)
        window.titleBar.hBoxLayout.insertWidget(1, badge)
        badge.set_state(phase="running", launch_method="zapret2_mode")
        window.show()
        _wait(0.05)
        patcher = patch.object(handoff, "popup_motion_mode", return_value=mode)
        patcher.start()
        self.addCleanup(patcher.stop)
        motion = handoff.LaunchBadgeHandoff(window, badge, locate_circle=lambda _w: (window.page, window.circle))
        _wait(0.05)
        return window, badge, motion

    def test_badge_is_hidden_while_the_circle_is_on_screen(self) -> None:
        window, badge, motion = self._bind("none")
        self.assertFalse(motion.is_badge_wanted())
        self.assertTrue(badge.isHidden())
        # Места в заголовке спрятанная метка не занимает: на главной
        # между вкладками и колокольчиком оставалась дыра.
        self.assertFalse(badge.sizePolicy().retainSizeWhenHidden())
        self.assertEqual(badge.slot(), 0.0)

    def test_first_decision_does_not_fly(self) -> None:
        """Страница строится после метки: запуск не должен начинаться с полёта."""
        window, _badge, motion = self._bind("spring")
        self.assertFalse(motion._ghost.isVisible())
        self.assertFalse(motion._timer.isActive())

    def test_scrolling_the_circle_away_brings_the_badge(self) -> None:
        window, badge, _motion = self._bind("none")
        bar = window.page.verticalScrollBar()
        bar.setValue(bar.maximum())
        _wait(0.05)
        self.assertFalse(badge.isHidden())
        self.assertEqual(badge.presence(), 1.0)
        bar.setValue(0)
        _wait(0.05)
        self.assertTrue(badge.isHidden())

    def test_leaving_the_page_flies_the_circle_into_the_badge(self) -> None:
        window, badge, motion = self._bind("spring")
        window.stackedWidget.setCurrentWidget(window.other)
        _wait(0.12)
        # В пути: снимок летит, настоящей метки нет — двух меток на экране
        # быть не должно. Но место под неё уже раздвигается: вкладки
        # отъезжают плавно, а не прыгают, когда снимок сел.
        self.assertTrue(motion._ghost.isVisible())
        self.assertEqual(badge.presence(), 0.0)
        self.assertGreater(badge.slot(), 0.0)
        self.assertLess(badge.slot(), 1.0)
        self.assertLess(badge.width(), badge.full_width())
        _wait(1.2)
        self.assertFalse(motion._ghost.isVisible())
        self.assertFalse(badge.isHidden())
        self.assertEqual(badge.presence(), 1.0)
        self.assertEqual(badge.width(), badge.full_width())

    def test_flight_lands_where_the_badge_will_stand(self) -> None:
        """Цель полёта — место метки целиком, а не её растущая щель."""
        window, badge, motion = self._bind("spring")
        window.stackedWidget.setCurrentWidget(window.other)
        _wait(0.12)
        target = motion._badge_rect()
        _wait(1.2)
        spot = badge.mapTo(window, badge.rect().topLeft())
        self.assertAlmostEqual(target.x(), spot.x(), delta=1.5)
        self.assertAlmostEqual(target.y(), spot.y(), delta=1.5)
        self.assertAlmostEqual(target.width(), badge.width(), delta=1.0)

    def test_real_circle_is_not_drawn_next_to_its_flying_snapshot(self) -> None:
        """На обратном пути на экране было два круга: настоящий и снимок."""
        window, badge, motion = self._bind("spring")
        window.stackedWidget.setCurrentWidget(window.other)
        _wait(1.2)
        # Круг «в метке»: настоящий невидим, пока метка стоит.
        effect = window.circle.graphicsEffect()
        self.assertIsNotNone(effect)
        self.assertEqual(effect.opacity(), 0.0)

        window.stackedWidget.setCurrentWidget(window.page)
        _wait(0.12)
        self.assertTrue(motion._ghost.isVisible())
        self.assertIsNotNone(window.circle.graphicsEffect())
        # Снимок круга для обратного пути не пустой, хотя сам круг спрятан.
        image = motion._ghost.circle.toImage()
        self.assertGreater(image.pixelColor(image.width() // 2, image.height() // 2).alpha(), 0)

        _wait(1.2)
        self.assertFalse(motion._ghost.isVisible())
        self.assertIsNone(window.circle.graphicsEffect())
        self.assertTrue(badge.isHidden())

    def test_reversal_continues_from_the_value_on_screen(self) -> None:
        window, _badge, motion = self._bind("spring")
        window.stackedWidget.setCurrentWidget(window.other)
        _wait(0.12)
        before = motion._spring.value
        self.assertGreater(before, 0.05)
        self.assertLess(before, 0.98)
        window.stackedWidget.setCurrentWidget(window.page)
        _wait(0.02)
        # Ни скачка к концу, ни возврата к началу: пружина развернулась
        # с той точки, где снимок был на экране.
        self.assertLess(abs(motion._spring.value - before), 0.12)
        self.assertEqual(motion._spring.target, 0.0)

    def test_fade_mode_shows_no_flight(self) -> None:
        window, badge, motion = self._bind("fade")
        window.stackedWidget.setCurrentWidget(window.other)
        _wait(0.08)
        self.assertFalse(motion._ghost.isVisible())
        _wait(1.2)
        self.assertEqual(badge.presence(), 1.0)

    def test_half_visible_badge_does_not_take_clicks(self) -> None:
        from ui.launch_title_badge import LaunchTitleBadge

        host = QWidget()
        self.addCleanup(host.deleteLater)
        badge = LaunchTitleBadge(host, language_provider=lambda: None)
        badge.set_state(phase="running", launch_method="zapret2_mode")
        badge.set_presence(0.5)
        self.assertTrue(badge.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        badge.set_presence(1.0)
        self.assertFalse(badge.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertFalse(badge.grab_full().isNull())


if __name__ == "__main__":
    unittest.main()
