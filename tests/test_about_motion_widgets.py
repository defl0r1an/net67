from __future__ import annotations

import os
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

import ui.widgets.stagger_float_in as float_module
import ui.widgets.turning_globe as globe_module
from ui.widgets.stagger_float_in import attach_stagger_float_in, skip_float_in
from ui.widgets.turning_globe import GLOBE_ICONS, TurningGlobe


def _wait(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()


class StaggerFloatInTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        patcher = mock.patch.object(float_module, "are_live_animations_enabled", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.container = QWidget()
        self.addCleanup(self.container.deleteLater)
        layout = QVBoxLayout(self.container)
        self.cards = [QLabel(f"card {index}") for index in range(3)]
        self.own_entrance = skip_float_in(QLabel("motto"))
        layout.addWidget(self.own_entrance)
        for card in self.cards:
            layout.addWidget(card)
        self.container.resize(300, 200)
        self.controller = attach_stagger_float_in(self.container)

    def test_cards_float_in_one_after_another_then_effects_are_removed(self) -> None:
        self.container.show()
        _wait(0.12)

        self.assertTrue(self.controller.is_running())
        self.assertIsNone(self.own_entrance.graphicsEffect())
        progress = [card.graphicsEffect()._progress for card in self.cards]
        self.assertGreater(progress[0], progress[2])
        self.container.grab()

        _wait((float_module.FLOAT_IN_DURATION_MS + 3 * float_module.FLOAT_IN_STEP_MS) / 1000 + 0.2)
        self.assertFalse(self.controller.is_running())
        self.assertTrue(all(card.graphicsEffect() is None for card in self.cards))

    def test_nothing_floats_when_live_animations_are_off(self) -> None:
        with mock.patch.object(float_module, "are_live_animations_enabled", return_value=False):
            self.container.show()
            _wait(0.05)
        self.assertFalse(self.controller.is_running())
        self.assertTrue(all(card.graphicsEffect() is None for card in self.cards))

    def test_showing_again_mid_flight_does_not_restart_from_the_bottom(self) -> None:
        """Движение продолжается с того места, где его застали."""
        self.container.show()
        _wait(0.12)
        before = [card.graphicsEffect()._progress for card in self.cards]
        self.container.hide()
        # Скрытие доводит всё до конца; повторный показ сразу после —
        # новое выплывание, а не прыжок назад у недоехавших карточек.
        self.controller.play()
        self.container.show()
        QApplication.processEvents()
        effects_mid = [card.graphicsEffect() for card in self.cards]
        # Показ, пока карточки едут, не перезапускает их.
        self.controller.play()
        self.assertEqual([card.graphicsEffect() for card in self.cards], effects_mid)
        self.assertTrue(any(value > 0.0 for value in before))

    def test_spring_curve_is_smooth_and_lands_exactly(self) -> None:
        values = [float_module._critically_damped(step / 100) for step in range(101)]
        self.assertEqual(values[0], 0.0)
        self.assertAlmostEqual(values[-1], 1.0, places=9)
        # Без перелёта: путь только растёт и не выходит за место.
        self.assertTrue(all(b >= a for a, b in zip(values, values[1:])))
        self.assertLessEqual(max(values), 1.0 + 1e-9)
        # Последняя десятая времени — доводка, а не резкая остановка.
        self.assertLess(values[-1] - values[90], 0.01)

    def test_page_content_floats_in_on_every_page(self) -> None:
        from ui.pages.base_page import BasePage

        page = BasePage("Проверка", "подзаголовок")
        self.addCleanup(page.deleteLater)
        self.assertIsNotNone(page.content.__dict__.get(float_module._CONTROLLER_ATTR))

    def test_hiding_finishes_immediately(self) -> None:
        self.container.show()
        _wait(0.05)
        self.container.hide()
        QApplication.processEvents()
        self.assertFalse(self.controller.is_running())
        self.assertTrue(all(card.graphicsEffect() is None for card in self.cards))


class TurningGlobeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_globe_turns_to_next_continent_and_stops_when_hidden(self) -> None:
        with mock.patch.object(globe_module, "are_live_animations_enabled", return_value=True), \
                mock.patch.object(globe_module, "TURN_PERIOD_MS", 1000), \
                mock.patch.object(globe_module, "TURN_DURATION_MS", 300):
            globe = TurningGlobe(size=32)
            self.addCleanup(globe.deleteLater)
            globe.show()
            self.assertTrue(globe.is_animating())
            self.assertEqual(globe.current_icon(), GLOBE_ICONS[0])
            _wait(1.2)
            globe.grab()
            self.assertEqual(globe.current_icon(), GLOBE_ICONS[1])
            globe.hide()
            self.assertFalse(globe.is_animating())

    def test_globe_stands_still_when_live_animations_are_off(self) -> None:
        with mock.patch.object(globe_module, "are_live_animations_enabled", return_value=False):
            globe = TurningGlobe(size=32)
            self.addCleanup(globe.deleteLater)
            globe.show()
            self.assertFalse(globe.is_animating())


class KvnLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])



class AboutPageMotionWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])



if __name__ == "__main__":
    unittest.main()
