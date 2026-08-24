"""Главная кнопка: цвет по состоянию, отклик на нажатие, счётчик времени.

Человек сказал прямо: «при нажатии на кнопку включить защиту нет никакой
анимации, а это самое важное». Кнопка выглядела одинаково выключенной и
работающей, нажатие ничего не меняло на глаз, а сколько защита работает,
узнать было негде.

Здесь три отдельных требования, и тесты держат каждое по отдельности:
цвет круга различает состояния, нажатие меняет размер, а время идёт
внутри самого круга, а не строкой под ним.
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
    def _button(self):
        import qfluentwidgets

        from oneclick.ui.button import OneClickButton

        qfluentwidgets.setTheme(qfluentwidgets.Theme.DARK)
        button = OneClickButton()
        button.resize(420, 320)
        button.show()
        self.addCleanup(button.deleteLater)
        return button

    @staticmethod
    def _fill(widget) -> str:
        """Цвет заливки круга.

        Раньше он читался из таблицы стилей. Теперь круг рисует себя сам
        — с переходом от блика сверху к тени снизу и кольцом по краю, —
        потому что плоское пятно одного цвета человек назвал монотонным.
        Таблица стилей задаёт только прозрачный текст.
        """
        return str(widget.button._net67_fill).lower()

    @staticmethod
    def _ring(widget) -> str:
        return str(widget.button._net67_ring).lower()

    def test_colour_differs_between_off_and_running(self) -> None:
        """Иначе состояние приходится вычитывать из подписи."""
        from oneclick.state import OneClickState

        widget = self._button()

        widget._apply_state(OneClickState.OFF, "")
        off = self._fill(widget)
        widget._apply_state(OneClickState.RUNNING, "")
        running = self._fill(widget)

        self.assertNotEqual(off, running)

    def test_running_uses_the_shell_accent(self) -> None:
        """Один акцент на всё приложение, а не свой цвет у каждой кнопки."""
        from oneclick.state import OneClickState
        from shell.theme import DARK

        widget = self._button()

        widget._apply_state(OneClickState.RUNNING, "")

        self.assertEqual(self._fill(widget), DARK.accent.lower())

    def test_error_is_red(self) -> None:
        """Ошибку человек должен видеть, не читая мелкий текст."""
        from oneclick.state import OneClickState

        widget = self._button()

        widget._apply_state(OneClickState.ERROR, "")
        red, green, blue = (
            int(self._fill(widget).lstrip("#")[index : index + 2], 16)
            for index in (0, 2, 4)
        )

        self.assertGreater(red, green + 0x40)
        self.assertGreater(red, blue + 0x40)

    def test_ring_lights_up_under_the_press(self) -> None:
        """Отклик на нажатие не только в размере: кольцо вспыхивает."""
        from oneclick.state import OneClickState

        widget = self._button()
        widget._apply_state(OneClickState.RUNNING, "")

        widget.button.pressed.emit()
        values = []
        deadline = time.time() + 0.35
        while time.time() < deadline:
            _APP.processEvents()
            values.append(widget.button._net67_glow)
            time.sleep(0.01)

        self.assertGreater(max(values), 0.5)

    def test_icon_makes_a_full_turn_when_state_flips(self) -> None:
        """Полный оборот, а не половина: состояний два, вид должен быть один."""
        from oneclick.state import OneClickState

        widget = self._button()
        widget._apply_state(OneClickState.OFF, "")

        widget._apply_state(OneClickState.RUNNING, "")
        angles = []
        deadline = time.time() + 0.8
        while time.time() < deadline:
            _APP.processEvents()
            angles.append(widget.button._net67_spin)
            time.sleep(0.01)

        self.assertGreater(max(angles), 300.0)
        self.assertEqual(widget.button._net67_spin, 0.0)

    def test_circle_is_not_a_flat_patch(self) -> None:
        """Заливка с переходом: у круга должен читаться объём."""
        from oneclick.state import OneClickState

        widget = self._button()
        widget._apply_state(OneClickState.OFF, "")
        _APP.processEvents()

        image = widget.button.grab().toImage()
        top = image.pixelColor(44, 12).lightnessF()
        bottom = image.pixelColor(44, 80).lightnessF()

        self.assertGreater(top, bottom)

    def test_press_shrinks_the_circle_and_release_restores_it(self) -> None:
        """То самое ощущение удара по кнопке, которого человек не находил."""
        from oneclick.state import OneClickState

        widget = self._button()
        widget._apply_state(OneClickState.RUNNING, "")
        before = widget.button.width()

        widget.button.pressed.emit()
        sizes = self._drain(widget, seconds=0.4)

        self.assertLess(min(sizes), before)

        widget.button.released.emit()
        self._drain(widget, seconds=0.4)

        self.assertEqual(widget.button.width(), before)

    def test_press_is_animated_not_instant(self) -> None:
        """Скачок между двумя размерами читается как дефект отрисовки."""
        from oneclick.state import OneClickState

        widget = self._button()
        widget._apply_state(OneClickState.RUNNING, "")

        widget.button.pressed.emit()
        sizes = self._drain(widget, seconds=0.4)

        self.assertGreaterEqual(len(set(sizes)), 3)

    @staticmethod
    def _drain(widget, *, seconds: float) -> list[int]:
        sizes: list[int] = []
        deadline = time.time() + seconds
        while time.time() < deadline:
            _APP.processEvents()
            sizes.append(widget.button.width())
            time.sleep(0.01)
        return sizes

    def test_timer_lives_inside_the_circle(self) -> None:
        """Просили «прям на кнопке», а не строкой под ней."""
        from oneclick.state import OneClickState

        widget = self._button()

        widget._apply_state(OneClickState.RUNNING, "")

        self.assertIs(widget.uptime_label.parent(), widget.button)
        self.assertFalse(widget.uptime_label.isHidden())
        self.assertEqual(widget.uptime_label.text(), "0:00")

    def test_icon_steps_aside_for_the_digits(self) -> None:
        """В круге 88 пикселей значок и цифры вместе не читаются."""
        from oneclick.state import OneClickState

        widget = self._button()

        widget._apply_state(OneClickState.OFF, "")
        self.assertFalse(widget.button.icon().isNull())

        widget._apply_state(OneClickState.RUNNING, "")
        self.assertTrue(widget.button.icon().isNull())

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

    def test_digits_follow_the_circle_when_it_shrinks(self) -> None:
        """Иначе на нажатии время выезжает за край круга."""
        from oneclick.state import OneClickState

        widget = self._button()
        widget._apply_state(OneClickState.RUNNING, "")

        widget._set_hero_size(70)

        self.assertEqual(widget.uptime_label.width(), 70)


if __name__ == "__main__":
    unittest.main()
