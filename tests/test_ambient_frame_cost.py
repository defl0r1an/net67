"""Фоновые пятна не должны съедать кадр.

Слой лежит под прозрачным содержимым окна. Значит, перерисовывают его
не четыре раза в секунду по своему таймеру, а на каждый кадр любой
анимации: Qt обязан восстановить фон под тем, что движется.

Замер на окне 1440×1000 до правки:

    4.1 мс на кадр — четверть бюджета 16.7 мс,

и это за фон, который меняется за секунду на доли пикселя. После —
готовая картинка вместо растеризации двух радиальных градиентов:

    0.27 мс на кадр

Картинка пересобирается при смене размера, темы и такта таймера. Между
тактами кадр один и тот же, и глаз этого не видит: пятна ползут с
периодом в полминуты.
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


#: Потолок на кадр. Бюджет при 60 к/с — 16.7 мс, и фон не имеет права
#: забирать больше десятой части. Замер даёт 0.27 мс, запас
#: шестикратный: машина, на которой идут тесты, медленнее рабочей.
FRAME_BUDGET_MS = 1.7

WIDTH, HEIGHT = 1440, 1000


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class AmbientFrameCostTests(unittest.TestCase):
    def _layer(self):
        from shell.ambient import AmbientLayer

        layer = AmbientLayer()
        layer.resize(WIDTH, HEIGHT)
        layer.show()
        _APP.processEvents()
        self.addCleanup(layer.deleteLater)
        return layer

    def _measure(self, layer, repeats: int = 30) -> float:
        from PyQt6.QtGui import QPainter, QPixmap

        target = QPixmap(WIDTH, HEIGHT)

        def frame() -> None:
            painter = QPainter(target)
            layer.render(painter)
            painter.end()

        frame()
        frame()

        started = time.perf_counter()
        for _ in range(repeats):
            frame()
        return (time.perf_counter() - started) / repeats * 1000

    def test_repeat_frame_is_cheap(self) -> None:
        self.assertLess(self._measure(self._layer()), FRAME_BUDGET_MS)

    def test_cache_is_reused_between_frames(self) -> None:
        layer = self._layer()
        self._measure(layer, repeats=2)

        first = layer._cache
        self._measure(layer, repeats=2)

        self.assertIs(layer._cache, first)

    def test_tick_rebuilds_the_picture(self) -> None:
        """Иначе пятна замерли бы навсегда."""
        layer = self._layer()
        self._measure(layer, repeats=2)
        before = layer._cache_key

        layer._tick()
        self._measure(layer, repeats=2)

        self.assertNotEqual(layer._cache_key, before)

    def test_resize_rebuilds_the_picture(self) -> None:
        """Растянутая картинка выдала бы себя мылом на краях."""
        layer = self._layer()
        self._measure(layer, repeats=2)
        before = layer._cache_key

        layer.resize(WIDTH // 2, HEIGHT // 2)
        _APP.processEvents()
        self._measure(layer, repeats=2)

        self.assertNotEqual(layer._cache_key, before)

    def test_theme_change_rebuilds_the_picture(self) -> None:
        """В светлой теме свечение чёрное, в тёмной белое."""
        layer = self._layer()
        self._measure(layer, repeats=2)
        before = layer._cache_key

        layer.set_dark(not layer._dark)
        self._measure(layer, repeats=2)

        self.assertNotEqual(layer._cache_key, before)


if __name__ == "__main__":
    unittest.main()
