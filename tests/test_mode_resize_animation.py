"""Размер окна при смене режима: едет, а не прыгает.

Смена режима — единственное место, где окно меняет размер само, без
руки человека, и скачок на четыреста пикселей читался как сбой
отрисовки: было одно окно, стало другое, промежутка не было.

Две вещи здесь неочевидны, и обе уже ломались.

Порядок минимума. Растущему окну минимум ставится в конце: поставь
первым — Qt мгновенно растянет окно до него, и анимировать станет
нечего. Сжимающемуся, наоборот, в начале: минимум прежнего режима
обрезал бы каждый кадр, и окно застряло бы на полпути.

Отказ. Анимация не берётся за развёрнутое окно и не работает при
выключенных анимациях, и в обоих случаях обязана сказать об этом
вызывающему: размер тогда ставит прежний путь. Молчаливый отказ оставил
бы окно от прежнего режима.
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

try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class ModeResizeTests(unittest.TestCase):
    def setUp(self) -> None:
        from config.window_metrics import get_min_size_for_mode, get_window_size_for_mode

        self.simple_min = get_min_size_for_mode(False)
        self.simple_size = get_window_size_for_mode(False)
        self.advanced_min = get_min_size_for_mode(True)
        self.advanced_size = get_window_size_for_mode(True)

    def _window(self, size, minimum):
        from PyQt6.QtWidgets import QWidget

        window = QWidget()
        window.setMinimumSize(*minimum)
        window.resize(*size)
        window.show()
        _APP.processEvents()
        self.addCleanup(window.deleteLater)
        return window

    def _drain(self, seconds: float, collect=lambda: None) -> list:
        values = []
        deadline = time.time() + seconds
        while time.time() < deadline:
            _APP.processEvents()
            values.append(collect())
            time.sleep(0.01)
        return values

    def test_shrinking_goes_through_frames(self) -> None:
        """Иначе это тот же скачок, только через анимацию."""
        from ui.window_mode_geometry import animate_window_size_for_mode

        window = self._window(self.advanced_size, self.advanced_min)

        self.assertTrue(animate_window_size_for_mode(window, False))
        widths = self._drain(0.8, lambda: window.width())

        self.assertGreaterEqual(len(set(widths)), 3)

    def test_shrinking_arrives_exactly(self) -> None:
        """Минимум прежнего режима держал бы окно на полпути."""
        from ui.window_mode_geometry import animate_window_size_for_mode

        window = self._window(self.advanced_size, self.advanced_min)

        animate_window_size_for_mode(window, False)
        self._drain(0.8)

        self.assertEqual((window.width(), window.height()), tuple(self.simple_size))
        self.assertEqual(window.minimumWidth(), self.simple_min[0])

    def test_growing_does_not_snap_on_the_first_frame(self) -> None:
        """Растущий минимум, поставленный сразу, съедает всю анимацию."""
        from ui.window_mode_geometry import animate_window_size_for_mode

        window = self._window(self.simple_size, self.simple_min)

        self.assertTrue(animate_window_size_for_mode(window, True))
        _APP.processEvents()

        self.assertLess(window.width(), self.advanced_size[0])
        self.assertEqual(window.minimumWidth(), self.simple_min[0])

    def test_growing_raises_the_minimum_at_the_end(self) -> None:
        """Забыть его — значит разрешить сжать расширенный вид до простого."""
        from ui.window_mode_geometry import animate_window_size_for_mode

        window = self._window(self.simple_size, self.simple_min)

        animate_window_size_for_mode(window, True)
        self._drain(0.8)

        self.assertEqual((window.width(), window.height()), tuple(self.advanced_size))
        self.assertEqual(window.minimumWidth(), self.advanced_min[0])

    def test_end_is_reported_once(self) -> None:
        """На конце висит сжатие окна: второй вызов запустил бы его дважды."""
        from ui.window_mode_geometry import animate_window_size_for_mode

        window = self._window(self.advanced_size, self.advanced_min)
        calls = []

        animate_window_size_for_mode(window, False, on_finished=lambda: calls.append(1))
        self._drain(0.9)

        self.assertEqual(calls, [1])

    def test_matching_size_still_fixes_the_minimum(self) -> None:
        """Ехать некуда, но минимум мог остаться от прежнего режима."""
        from ui.window_mode_geometry import animate_window_size_for_mode

        window = self._window(self.simple_size, (500, 500))
        calls = []

        self.assertTrue(
            animate_window_size_for_mode(window, False, on_finished=lambda: calls.append(1))
        )

        self.assertEqual(window.minimumWidth(), self.simple_min[0])
        self.assertEqual(calls, [1])

    def test_maximized_window_is_left_alone(self) -> None:
        """Развернул человек — значит так и хотел."""
        from ui.window_mode_geometry import animate_window_size_for_mode

        window = self._window(self.advanced_size, self.advanced_min)
        window.showMaximized()
        _APP.processEvents()

        self.assertFalse(animate_window_size_for_mode(window, False))

    def test_disabled_animations_hand_the_job_back(self) -> None:
        """Отказ обязан быть заметен: иначе окно останется от прежнего режима."""
        from ui import animation_policy
        from ui.window_mode_geometry import animate_window_size_for_mode

        window = self._window(self.advanced_size, self.advanced_min)
        original = animation_policy.are_animations_enabled
        animation_policy.are_animations_enabled = lambda: False
        self.addCleanup(setattr, animation_policy, "are_animations_enabled", original)

        self.assertFalse(animate_window_size_for_mode(window, False))
        self.assertEqual(window.width(), self.advanced_size[0])

    def test_second_switch_wins(self) -> None:
        """Две анимации тянули бы размер в разные стороны."""
        from ui.window_mode_geometry import animate_window_size_for_mode

        window = self._window(self.advanced_size, self.advanced_min)

        animate_window_size_for_mode(window, False)
        self._drain(0.1)
        animate_window_size_for_mode(window, True)
        self._drain(0.9)

        self.assertEqual((window.width(), window.height()), tuple(self.advanced_size))


class ModeSwitchOrderTests(unittest.TestCase):
    """Порядок шагов при переключении. Читаем исходник: окна тут не нужно."""

    def _toggle_source(self) -> str:
        return (
            PROJECT_SRC / "ui" / "navigation" / "advanced_toggle.py"
        ).read_text(encoding="utf-8")

    def test_window_grows_before_the_wave(self) -> None:
        """Волна в окне прежнего размера упёрлась бы в его край."""
        source = self._toggle_source()

        grow = source.index("_resize_window_for_mode(window, True)")
        wave = source.index("apply_simple_view(")

        self.assertLess(grow, wave)

    def test_window_shrinks_after_the_wave(self) -> None:
        """Схлопнись окно первым — волна доиграла бы за его краем."""
        source = self._toggle_source()

        self.assertIn(
            "on_settled=lambda: _resize_window_for_mode(window, False)",
            source,
        )

    def test_shrink_happens_even_without_a_control_page(self) -> None:
        """Иначе окно осталось бы размером с расширенный вид навсегда."""
        source = self._toggle_source()

        self.assertIn("if not next_value and not shrink_handed_over:", source)

    def test_refusal_falls_back_to_the_instant_size(self) -> None:
        """Развёрнутое окно и выключенные анимации — не повод не менять размер."""
        source = self._toggle_source()

        start = source.index("def _resize_window_for_mode(")
        end = source.index("def toggle_advanced_mode(")
        body = source[start:end]

        self.assertIn("if animate_window_size_for_mode(window, advanced):", body)
        self.assertIn("apply_window_size_for_mode(window, advanced)", body)


if __name__ == "__main__":
    unittest.main()
