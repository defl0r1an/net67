"""Фоновое свечение: заметно глазу, незаметно процессору.

Приём подсмотрен в чужом оформлении, но написан заново: там CSS для
Electron, в Qt он не вставляется, а числа и правила защите не подлежат.

Два требования тянут в разные стороны. Свечение должно быть на грани
различимости — пятно, которое видно как пятно, это брак. И оно лежит под
всем содержимым, поэтому каждая его перерисовка тянет за собой
перерисовку всего окна: ровно на этом обжигались песчинки, из-за которых
интерфейс шёл «пятнадцатью кадрами».
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


class MotionTests(unittest.TestCase):
    """Движение проверяется без окна: это арифметика."""

    def test_blobs_start_in_opposite_corners(self) -> None:
        """По диагонали, чтобы неоднородность прошла через всё окно."""
        from shell.ambient import blob_center

        first = blob_center(0.0, width=1000, height=600)
        second = blob_center(0.0, width=1000, height=600, second=True)

        self.assertGreater(first[0], 500)
        self.assertLess(first[1], 300)
        self.assertLess(second[0], 500)
        self.assertGreater(second[1], 300)

    def test_blobs_actually_move(self) -> None:
        from shell.ambient import blob_center

        start = blob_center(0.0, width=1000, height=600)
        later = blob_center(13.0, width=1000, height=600)

        self.assertGreater(abs(start[0] - later[0]), 50)

    def test_paths_do_not_repeat_each_other(self) -> None:
        """С одинаковым периодом дрейф читался бы как дыхание."""
        from shell.ambient import PERIOD_A, PERIOD_B

        self.assertNotEqual(PERIOD_A, PERIOD_B)

    def test_blob_reaches_beyond_the_window(self) -> None:
        """Иначе видно границу круга, и приём превращается в «круг на фоне»."""
        from shell.ambient import BLOB_SCALE

        self.assertGreater(BLOB_SCALE, 1.0)

    def test_glow_stays_below_the_threshold_of_noticing(self) -> None:
        from shell.ambient import BLOB_ALPHA

        self.assertLess(BLOB_ALPHA, 0.09)
        self.assertGreater(BLOB_ALPHA, 0.02)

    def test_refresh_is_slow_on_purpose(self) -> None:
        """Слой под содержимым: его кадр стоит перерисовки всего окна.

        Замер на окне 1280×800 с полусотней кнопок: 12.9 мс на кадр. При
        шестидесяти кадрах это съело бы три четверти бюджета ради
        движения в доли пикселя. Четыре кадра дают то же самое за 52 мс
        на секунду работы.
        """
        from shell.ambient import TICK_MS

        self.assertGreaterEqual(TICK_MS, 200)


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class PaintTests(unittest.TestCase):
    def _host(self, dark: bool = True):
        from PyQt6.QtWidgets import QWidget

        from shell.ambient import AmbientLayer
        from shell.theme import palette

        host = QWidget()
        host.setStyleSheet(f"background: {palette(dark).content};")
        host.resize(1000, 640)
        layer = AmbientLayer(host, dark=dark)
        layer.setGeometry(host.rect())
        layer.show()
        host.show()
        _APP.processEvents()
        self.addCleanup(host.deleteLater)
        return host, layer

    @staticmethod
    def _brightness(host, x: int, y: int) -> int:
        return host.grab().toImage().pixelColor(x, y).red()

    def test_glow_lifts_the_background(self) -> None:
        from shell.theme import DARK

        host, _layer = self._host()
        plain = int(DARK.content.lstrip("#")[0:2], 16)

        near_blob = self._brightness(host, 960, 30)

        self.assertGreater(near_blob, plain)

    def test_glow_falls_off_across_the_window(self) -> None:
        """Ровная засветка — это просто другой фон, а не глубина."""
        host, _layer = self._host()

        near = self._brightness(host, 960, 30)
        far = self._brightness(host, 960, 610)

        self.assertGreater(near, far)

    def test_glow_is_subtle(self) -> None:
        """Разница в полтона: заметно, но не читается как пятно."""
        from shell.theme import DARK

        host, _layer = self._host()
        plain = int(DARK.content.lstrip("#")[0:2], 16)

        self.assertLess(self._brightness(host, 960, 30) - plain, 40)

    def test_light_theme_darkens_instead_of_lighting(self) -> None:
        """Белое свечение на белом фоне не видно вовсе."""
        from shell.theme import LIGHT

        host, _layer = self._host(dark=False)
        plain = int(LIGHT.content.lstrip("#")[0:2], 16)

        self.assertLess(self._brightness(host, 960, 30), plain)

    def test_layer_ignores_the_mouse(self) -> None:
        """Слой лежит поверх окна, но кликать надо по тому, что под ним."""
        from PyQt6.QtCore import Qt

        _host, layer = self._host()

        self.assertTrue(
            layer.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        )

    def test_hidden_layer_stops_ticking(self) -> None:
        """Невидимый слой не должен будить окно четыре раза в секунду."""
        _host, layer = self._host()
        self.assertTrue(layer._timer.isActive())

        layer.hide()
        _APP.processEvents()

        self.assertFalse(layer._timer.isActive())

    def test_frame_cost_stays_within_the_measured_budget(self) -> None:
        """Сторож той самой ошибки: слой под содержимым дорог по определению."""
        host, layer = self._host()

        samples = []
        for _ in range(6):
            started = time.perf_counter()
            layer._tick()
            _APP.processEvents()
            samples.append((time.perf_counter() - started) * 1000)

        average = sum(samples) / len(samples)
        from shell.ambient import TICK_MS

        # Доля времени, которую слой отнимает у процессора.
        share = average / TICK_MS
        self.assertLess(share, 0.25, f"свечение съедает {share:.0%} времени")


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class WiringTests(unittest.TestCase):
    def _window(self):
        import qfluentwidgets

        from shell.app_window import AppShellWindow

        qfluentwidgets.setTheme(qfluentwidgets.Theme.DARK)
        window = AppShellWindow()
        window.resize(900, 600)
        window.show()
        _APP.processEvents()
        self.addCleanup(window.deleteLater)
        return window

    def test_window_has_the_layer(self) -> None:
        window = self._window()

        self.assertIsNotNone(getattr(window, "ambient", None))

    def test_layer_covers_the_window(self) -> None:
        window = self._window()

        self.assertEqual(window.ambient.size(), window.size())

    def test_content_is_transparent_so_the_glow_shows(self) -> None:
        """Сплошная заливка содержимого перекрыла бы слой целиком."""
        from shell.theme import DARK, shell_qss

        qss = shell_qss(DARK)
        block = qss[qss.index("#net67Content") :]
        block = block[: block.index("}")]

        self.assertIn("transparent", block)


if __name__ == "__main__":
    unittest.main()
