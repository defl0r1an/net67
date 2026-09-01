# tests/test_win11_toggle_indicator.py
"""Тумблер обязан выглядеть так, как он работает.

Поломка, ради которой написан этот файл, была молчаливой и оттого
неприятной: тумблер работал правильно, подпись говорила «Вкл.», а
нарисован он был выключенным. Человек видит выключенный тумблер и жмёт
его — то есть выключает то, что было включено.

Виновата чужая деталь: кружок ездит анимацией, а `QAbstractAnimation.
start()` на уже запущенной анимации молча ничего не делает. Полагаться
на неё при программной установке состояния нельзя. Здесь это и
проверяется — без окна, на голых объектах Qt.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class AnimationRestartTests(unittest.TestCase):
    """Причина поломки — поведение самого Qt, а не наша сборка.

    Проверка нужна, чтобы правку не откатили как «лишнюю»: если Qt
    когда-нибудь начнёт перезапускать анимацию, тест это заметит и
    расскажет, а не оставит в коде необъяснимый обходной приём.
    """

    def test_start_on_running_animation_does_nothing(self) -> None:
        from PyQt6.QtCore import QAbstractAnimation, QPropertyAnimation, QObject, pyqtProperty

        class Holder(QObject):
            def __init__(self):
                super().__init__()
                self._x = 5.0

            def get_x(self):
                return self._x

            def set_x(self, value):
                self._x = float(value)

            x = pyqtProperty(float, get_x, set_x)

        holder = Holder()
        animation = QPropertyAnimation(holder, b"x")
        animation.setDuration(120)
        animation.setStartValue(5.0)
        animation.setEndValue(5.0)
        animation.start()
        self.assertEqual(animation.state(), QAbstractAnimation.State.Running)

        # Так ведёт себя qfluentwidgets при смене состояния тумблера.
        animation.setEndValue(25.0)
        animation.start()

        # Вот оно: время не сброшено, анимация не начата заново. Именно
        # поэтому кружок не доезжал.
        self.assertEqual(animation.state(), QAbstractAnimation.State.Running)
        self.assertEqual(animation.currentTime(), 0)
        animation.stop()


class FreezeWidthTests(unittest.TestCase):
    """Замер ширины не имеет права трогать состояние переключателя."""

    def test_freeze_never_changes_checked_state(self) -> None:
        from ui.widgets.win11_controls import Win11ToggleRow

        class FakeLabel:
            def fontMetrics(self):
                class Metrics:
                    @staticmethod
                    def horizontalAdvance(text):
                        return 10 * len(text)

                return Metrics()

            def sizeHint(self):
                class Size:
                    @staticmethod
                    def width():
                        return 50

                return Size()

        class FakeToggle:
            """Считает любые попытки переключить себя."""

            def __init__(self):
                self.label = FakeLabel()
                self.checked = True
                self.set_checked_calls = 0
                self.minimum_width = None

            def isChecked(self):
                return self.checked

            def setChecked(self, value):
                self.set_checked_calls += 1
                self.checked = bool(value)

            def sizeHint(self):
                class Size:
                    @staticmethod
                    def width():
                        return 110

                return Size()

            def setMinimumWidth(self, width):
                self.minimum_width = int(width)

            def blockSignals(self, _value):
                return False

            def adjustSize(self):
                return None

        toggle = FakeToggle()
        Win11ToggleRow._freeze_switch_width(toggle)

        self.assertEqual(toggle.set_checked_calls, 0, "замер ширины переключил состояние")
        self.assertTrue(toggle.checked)

        # Ширина считается: рамка (110 − 50) плюс самая длинная подпись.
        self.assertIsNotNone(toggle.minimum_width)
        self.assertGreater(toggle.minimum_width, 60)


class SnapIndicatorTests(unittest.TestCase):
    """Кружок встаёт на место сразу, не дожидаясь анимации."""

    def _toggle(self, *, checked: bool, width: int = 42):
        class FakeAnimation:
            def __init__(self):
                self.stopped = False

            def stop(self):
                self.stopped = True

        class FakeIndicator:
            def __init__(self):
                self.slideAni = FakeAnimation()
                self.slider_x = 5

            def width(self):
                return width

            def setSliderX(self, value):
                self.slider_x = int(value)

        class FakeToggle:
            def __init__(self):
                self.indicator = FakeIndicator()

            def isChecked(self):
                return checked

        return FakeToggle()

    def test_checked_moves_the_circle_to_the_right(self) -> None:
        from ui.widgets.win11_controls import Win11ToggleRow

        toggle = self._toggle(checked=True)
        Win11ToggleRow._snap_indicator(toggle)

        # 42 − 12 (диаметр) − 5 (отступ) = 25, как в самой библиотеке.
        self.assertEqual(toggle.indicator.slider_x, 25)
        self.assertTrue(toggle.indicator.slideAni.stopped)

    def test_unchecked_returns_the_circle_to_the_left(self) -> None:
        from ui.widgets.win11_controls import Win11ToggleRow

        toggle = self._toggle(checked=False)
        Win11ToggleRow._snap_indicator(toggle)
        self.assertEqual(toggle.indicator.slider_x, 5)

    def test_position_follows_the_width_not_a_constant(self) -> None:
        """Размер переключателя задаёт библиотека, и он может измениться."""
        from ui.widgets.win11_controls import Win11ToggleRow

        toggle = self._toggle(checked=True, width=60)
        Win11ToggleRow._snap_indicator(toggle)
        self.assertEqual(toggle.indicator.slider_x, 60 - 12 - 5)

    def test_narrow_indicator_does_not_push_the_circle_off_the_left(self) -> None:
        from ui.widgets.win11_controls import Win11ToggleRow

        toggle = self._toggle(checked=True, width=10)
        Win11ToggleRow._snap_indicator(toggle)
        self.assertEqual(toggle.indicator.slider_x, 5)

    def test_missing_indicator_is_survived(self) -> None:
        """Имя поля — деталь чужой библиотеки; её отсутствие не повод падать."""
        from ui.widgets.win11_controls import Win11ToggleRow

        class Bare:
            def isChecked(self):
                return True

        Win11ToggleRow._snap_indicator(Bare())


if __name__ == "__main__":
    unittest.main()
