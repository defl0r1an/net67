"""Главная кнопка: цвет по состоянию, отклик на нажатие, счётчик времени.

Человек сказал прямо: «при нажатии на кнопку включить защиту нет никакой
анимации, а это самое важное». Кнопка выглядела одинаково выключенной и
работающей, нажатие ничего не меняло на глаз, а сколько защита работает,
узнать было негде.

Здесь три отдельных требования, и тесты держат каждое по отдельности:
цвет кнопки различает состояния, нажатие видно, а время работы стоит
рядом с состоянием.

26 октября 2026 круг заменила сцена в духе zapret (ui/widgets/bypass_scene.py):
кнопка питания в стене блокировки. Требования те же, держат их теперь
цвет и фаза сцены, просадка кнопки под нажатием и плашка времени у
заголовка.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class UptimeFormatTests(unittest.TestCase):
    """Формат времени проверяем без Qt: это чистая функция."""

    def _format(self, seconds: float) -> str:
        from oneclick.ui.button import OneClickButton

        return OneClickButton.format_uptime(seconds)

    def test_seconds_are_always_shown(self) -> None:
        """Без секунд первые минуты выглядят застывшими."""
        self.assertEqual(self._format(0), "0:00")
        self.assertEqual(self._format(7), "0:07")

    def test_minutes_roll_over(self) -> None:
        self.assertEqual(self._format(75), "1:15")

    def test_hours_appear_only_when_needed(self) -> None:
        """Ведущий ноль часов в первые минуты — лишний шум."""
        self.assertNotIn(":", self._format(59)[:-3])
        self.assertEqual(self._format(3725), "1:02:05")

    def test_negative_time_does_not_produce_garbage(self) -> None:
        """Монотонные часы прыгать не должны, но проверка дешевле разбора."""
        self.assertEqual(self._format(-10), "0:00")


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class HeroButtonTests(unittest.TestCase):
    def setUp(self) -> None:
        # Общие часы обхода — одни на процесс: другой тест мог оставить
        # их идущими, и круг показал бы не «0:00».
        from ui import launch_uptime

        launch_uptime.clear()
        self.addCleanup(launch_uptime.clear)

    def _button(self):
        import qfluentwidgets

        from oneclick.ui.button import OneClickButton

        qfluentwidgets.setTheme(qfluentwidgets.Theme.DARK)
        button = OneClickButton()
        button.resize(420, 320)
        button.show()
        self.addCleanup(button.deleteLater)
        return button

    def test_colour_and_phase_follow_the_state(self) -> None:
        """Выключено — серое, запуск — янтарь, работает — зелёный, сбой — красный."""
        from oneclick.state import OneClickState
        from oneclick.ui import button as module

        widget = self._button()
        scene = widget.button
        for state, phase, color in (
            (OneClickState.OFF, "stopped", module.SCENE_COLOR_STOPPED),
            (OneClickState.PREPARING, "starting", module.SCENE_COLOR_BUSY),
            (OneClickState.CHECKING, "starting", module.SCENE_COLOR_BUSY),
            (OneClickState.RUNNING, "running", module.SCENE_COLOR_RUNNING),
            (OneClickState.ERROR, "failed", module.SCENE_COLOR_FAILED),
        ):
            with self.subTest(state=state):
                widget._apply_state(state, "")
                self.assertEqual(scene.phase(), phase)
                self.assertEqual(scene.target_color().name(), color)

    def test_stopping_runs_the_comet_backwards(self) -> None:
        """Остановка — своя фаза: комета идёт против часовой стрелки, кнопка «выдыхает»."""
        from oneclick.state import OneClickState

        widget = self._button()
        widget._apply_state(OneClickState.RUNNING, "")
        widget._stopping = True
        widget._apply_state(OneClickState.PREPARING, "")

        self.assertEqual(widget.button.phase(), "stopping")
        self.assertEqual(widget.state_label.text(), "Останавливаем...")

    def test_busy_button_does_not_take_a_second_press(self) -> None:
        """Две изменяющие систему команды одновременно запускать нельзя."""
        from oneclick.state import OneClickState

        widget = self._button()
        widget._apply_state(OneClickState.PREPARING, "")
        self.assertFalse(widget.button.is_click_enabled())

        widget._apply_state(OneClickState.RUNNING, "")
        self.assertTrue(widget.button.is_click_enabled())

    def test_press_shrinks_the_button_and_release_clicks_it(self) -> None:
        """Отклик на нажатие: кнопка в стене проседает, отпускание — это и есть нажатие."""
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent

        widget = self._button()
        scene = widget.button
        clicks: list[int] = []
        scene.clicked.connect(lambda: clicks.append(1))
        center = QPointF(scene.gate_center())

        def send(kind):
            event = QMouseEvent(kind, center, center, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            if kind == QEvent.Type.MouseButtonPress:
                scene.mousePressEvent(event)
            else:
                scene.mouseReleaseEvent(event)

        send(QEvent.Type.MouseButtonPress)
        self.assertTrue(scene.is_pressed())
        send(QEvent.Type.MouseButtonRelease)
        self.assertFalse(scene.is_pressed())
        self.assertEqual(clicks, [1])

    def test_off_state_is_calm_grey_not_an_alarm(self) -> None:
        """Красный на каждом открытии программы читался как ошибка."""
        from PyQt6.QtGui import QColor

        from oneclick.ui import button as module

        stopped = QColor(module.SCENE_COLOR_STOPPED)
        self.assertLess(stopped.hsvSaturation(), 40)
        self.assertNotEqual(module.SCENE_COLOR_STOPPED, module.SCENE_COLOR_FAILED)

    def test_only_the_power_button_flies_into_the_title_badge(self) -> None:
        """Снимок полёта вписывается в квадрат: сцена целиком сплющивалась в полоску."""
        from shell.launch_badge_handoff import LaunchBadgeHandoff

        widget = self._button()
        knob = widget.handoff_circle()

        self.assertIs(knob, widget.button.knob)
        self.assertEqual(knob.width(), knob.height())
        self.assertTrue(knob.geometry().contains(widget.button.gate_center()))

        class _Page:
            oneclick_button = widget

        with __import__("unittest").mock.patch("ui.window_adapter.get_loaded_page", return_value=_Page()):
            page, circle = LaunchBadgeHandoff._default_locate(object())
        self.assertIs(circle, knob)

    def test_text_stands_in_the_middle_of_the_scene_height(self) -> None:
        """Лишняя высота карточки не растаскивает заголовок и пояснение по краям."""
        from PyQt6.QtWidgets import QApplication

        from oneclick.state import OneClickState

        widget = self._button()
        widget.resize(1000, 200)
        widget._apply_state(OneClickState.RUNNING, "Работает, проверенные сайты открываются")
        QApplication.processEvents()

        title = widget.state_label.geometry()
        detail = widget.detail_label.geometry()
        self.assertLessEqual(detail.top() - title.bottom(), 12)
        middle = (title.top() + detail.bottom()) / 2
        self.assertAlmostEqual(middle, widget.button.geometry().center().y(), delta=8)

    def test_scene_is_the_main_button_for_tour_and_title_badge(self) -> None:
        """Тур и метка в заголовке ищут главную кнопку по имени ``button``."""
        from ui.widgets.bypass_scene import BypassScene

        widget = self._button()

        self.assertIsInstance(widget.button, BypassScene)
        self.assertTrue(widget.button.is_clickable())

    def test_timer_stands_next_to_the_state(self) -> None:
        """Время работы — плашкой у заголовка «Обход работает»."""
        from oneclick.state import OneClickState

        widget = self._button()

        widget._apply_state(OneClickState.RUNNING, "")

        self.assertIs(widget.uptime_label.parentWidget(), widget.card)
        self.assertFalse(widget.uptime_label.isHidden())
        self.assertEqual(widget.uptime_label.text(), "0:00")
        self.assertEqual(widget.state_label.text(), "Обход работает")

    def test_timer_disappears_when_protection_stops(self) -> None:
        """Застывшее время на выключенной защите — прямая ложь."""
        from oneclick.state import OneClickState

        widget = self._button()

        widget._apply_state(OneClickState.RUNNING, "")
        widget._apply_state(OneClickState.OFF, "")

        self.assertTrue(widget.uptime_label.isHidden())
        self.assertEqual(widget.uptime_label.text(), "")
        self.assertFalse(widget._uptime_timer.isActive())

    def test_countdown_restarts_from_zero(self) -> None:
        """Второй запуск считает своё время, а не продолжает прежнее."""
        from oneclick.state import OneClickState

        widget = self._button()

        widget._apply_state(OneClickState.RUNNING, "")
        widget._running_since -= 600
        widget._refresh_uptime()
        self.assertEqual(widget.uptime_label.text(), "10:00")

        widget._apply_state(OneClickState.OFF, "")
        widget._apply_state(OneClickState.RUNNING, "")

        self.assertEqual(widget.uptime_label.text(), "0:00")

    def test_narrow_window_puts_the_scene_above_the_text(self) -> None:
        """В узком окне сцена встаёт отдельной строкой на всю ширину."""
        from PyQt6.QtWidgets import QApplication

        widget = self._button()
        widget.resize(1000, 200)
        QApplication.processEvents()
        self.assertFalse(widget.card.is_stacked())

        widget.resize(500, 300)
        QApplication.processEvents()
        self.assertTrue(widget.card.is_stacked())
        self.assertTrue(widget.button.is_stretched())

if __name__ == "__main__":
    unittest.main()
