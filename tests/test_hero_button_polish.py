"""Главная кнопка: переход цвета, блик по кольцу, дыхание на работе.

Человек попросил сделать кнопку «более привлекательной», отдельно
оговорив, что главная фишка — проворот значка при переключении —
должна остаться. Отсюда три требования, и каждое проверяется само по
себе.

Цвет. Раньше круг менял цвет мгновенно: только что серый, уже синий.
Кадра перехода не было, и главный элемент экрана переключался беднее,
чем тумблер в настройках. Теперь заданный цвет и показываемый — разные
величины, и вторая доезжает до первой.

Блик по кольцу. Своей анимации у него нет: он берёт угол у прокрута,
поэтому появляется ровно на переключении и гаснет вместе с ним. Тест
следит за тем, чтобы отрисовка не падала ни на одном угле, включая
границы 0 и 360.

Дыхание. Статичная кнопка выглядит одинаково и когда обход поднят, и
когда запуск застрял на полпути. Но дыхание идёт часами, поэтому оно
обязано засыпать вместе с окном.

Базовый класс здесь — обычный QPushButton, а не кнопка qfluentwidgets:
проверяется отрисовка круга, и лишняя зависимость только сузила бы
круг машин, где тест вообще запускается.
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
class HeroButtonPolishTests(unittest.TestCase):
    def _button(self):
        from PyQt6.QtWidgets import QPushButton

        from ui.widgets.hero_control import HERO_BUTTON_SIZE, make_round_button_class

        button = make_round_button_class(QPushButton)("Включить обход")
        button.setFixedSize(HERO_BUTTON_SIZE, HERO_BUTTON_SIZE)
        button.show()
        _APP.processEvents()
        self.addCleanup(button.deleteLater)
        return button

    @staticmethod
    def _drain(seconds: float, collect):
        values = []
        deadline = time.time() + seconds
        while time.time() < deadline:
            _APP.processEvents()
            values.append(collect())
            time.sleep(0.01)
        return values

    # ── цвет ─────────────────────────────────────────────────────────
    def test_first_colour_is_instant(self) -> None:
        """До первой смены состояния переходить не от чего.

        Плавный въезд из ниоткуда выглядел бы как подгрузка окна.
        """
        from PyQt6.QtGui import QColor

        button = self._button()
        button.set_hero_colors(fill="#42454d", ring="#a8a8a8")

        self.assertEqual(button._net67_fill_shown, QColor("#42454d"))

    def test_target_colour_is_readable_at_once(self) -> None:
        """Заданный цвет — не анимация: его читают сразу после смены состояния."""
        button = self._button()
        button.set_hero_colors(fill="#42454d", ring="#a8a8a8")

        button.set_hero_colors(fill="#2f6fed", ring="#2f6fed")

        self.assertEqual(button._net67_fill, "#2f6fed")

    def test_shown_colour_travels_in_frames(self) -> None:
        """Скачок между двумя цветами читается как дефект отрисовки."""
        button = self._button()
        button.set_hero_colors(fill="#42454d", ring="#a8a8a8")

        button.set_hero_colors(fill="#2f6fed", ring="#2f6fed")
        names = self._drain(0.2, lambda: button._net67_fill_shown.name())

        self.assertGreaterEqual(len(set(names)), 3)

    def test_repeated_target_does_not_restart_the_travel(self) -> None:
        """Просадка круга под нажатием пересчитывает цвет на каждом кадре.

        Без этой защиты переход растягивался бы ровно столько, сколько
        палец держит кнопку.
        """
        button = self._button()
        button.set_hero_colors(fill="#42454d", ring="#a8a8a8")
        button.set_hero_colors(fill="#2f6fed", ring="#2f6fed")
        running = button._net67_color_animation

        button.set_hero_colors(fill="#2f6fed", ring="#2f6fed")

        self.assertIs(button._net67_color_animation, running)

    def test_shown_colour_arrives_exactly(self) -> None:
        """Недоехавший цвет — это тихо другой акцент у главной кнопки."""
        from PyQt6.QtGui import QColor

        button = self._button()
        button.set_hero_colors(fill="#42454d", ring="#a8a8a8")

        button.set_hero_colors(fill="#2f6fed", ring="#2f6fed")
        self._drain(0.7, lambda: None)

        self.assertEqual(button._net67_fill_shown, QColor("#2f6fed"))

    # ── объём ────────────────────────────────────────────────────────
    def test_circle_keeps_its_volume(self) -> None:
        """Блик сверху, тень снизу: круг не должен стать плоским пятном."""
        button = self._button()
        button.set_hero_colors(fill="#42454d", ring="#a8a8a8")
        _APP.processEvents()

        image = button.grab().toImage()

        self.assertGreater(
            image.pixelColor(44, 12).lightnessF(),
            image.pixelColor(44, 80).lightnessF(),
        )

    def test_volume_survives_flash_and_breathing(self) -> None:
        """Вспышка кольца и дыхание складываются в яркость. Вместе — тоже."""
        button = self._button()
        button.set_hero_colors(fill="#2f6fed", ring="#2f6fed")
        button.set_glow(1.0)
        button.set_pulse(1.0)
        _APP.processEvents()

        image = button.grab().toImage()

        self.assertGreater(
            image.pixelColor(44, 12).lightnessF(),
            image.pixelColor(44, 80).lightnessF(),
        )

    # ── блик по кольцу ───────────────────────────────────────────────
    def test_sweep_draws_at_every_angle(self) -> None:
        """Границы 0 и 360 — те самые углы, на которых прокрут начинается и кончается."""
        button = self._button()
        button.set_hero_colors(fill="#2f6fed", ring="#2f6fed")

        for angle in (0.0, 1.0, 90.0, 180.0, 359.0, 360.0):
            with self.subTest(angle=angle):
                button.set_spin(angle)
                _APP.processEvents()
                self.assertFalse(button.grab().isNull())

    # ── дыхание ──────────────────────────────────────────────────────
    def test_breathing_reaches_full_swing(self) -> None:
        """Дыхание, которого не видно, — это просто лишняя перерисовка."""
        button = self._button()
        button.set_hero_colors(fill="#2f6fed", ring="#2f6fed")

        button.start_pulse()
        peak = max(self._drain(1.6, lambda: button._net67_pulse))
        button.stop_pulse()

        self.assertGreater(peak, 0.5)

    def test_breathing_stops_and_resets(self) -> None:
        """Остаться на середине вдоха — значит навсегда подсветить выключенный обход."""
        button = self._button()
        button.set_hero_colors(fill="#2f6fed", ring="#2f6fed")
        button.start_pulse()
        self._drain(0.3, lambda: None)

        button.stop_pulse()

        self.assertIsNone(button._net67_pulse_animation)
        self.assertEqual(button._net67_pulse, 0.0)

    def test_breathing_sleeps_with_the_window(self) -> None:
        """Дышать за свёрнутым окном — греть процессор часами впустую."""
        button = self._button()
        button.start_pulse()

        button.hide()
        _APP.processEvents()
        self.assertIsNone(button._net67_pulse_animation)

        button.show()
        _APP.processEvents()
        self.assertIsNotNone(button._net67_pulse_animation)

        button.stop_pulse()

    def test_breathing_is_tied_to_the_running_state(self) -> None:
        """Иначе кнопка дышала бы и на застрявшем запуске, и на ошибке."""
        import inspect

        from oneclick.ui import button as button_module

        source = inspect.getsource(button_module.OneClickButton._apply_state)

        self.assertIn("start_pulse", source)
        self.assertIn("stop_pulse", source)


if __name__ == "__main__":
    unittest.main()
