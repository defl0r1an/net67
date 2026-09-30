"""Широкие значки qtawesome не срезаются и не выпирают из ряда.

Владелец показал «съехавшие» значки: ntc.party, Supercell, Destiny 2 в
редакторе hosts и «Онлайн-игры» в подборе стратегии. Все они — глифы
шире квадрата, которые qtawesome рисовал с обрезанными краями.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

SIZE = 20


def _ink(name: str) -> tuple[int, int, int, int]:
    """Границы закрашенного (левый, правый, верх, низ) в квадрате SIZE."""
    import qtawesome

    image = qtawesome.icon(name, color="#ffffff").pixmap(SIZE, SIZE).toImage()
    xs, ys = [], []
    for x in range(image.width()):
        for y in range(image.height()):
            if image.pixelColor(x, y).alpha() > 40:
                xs.append(x)
                ys.append(y)
    return (min(xs), max(xs), min(ys), max(ys))


class WideGlyphFitTests(unittest.TestCase):
    def setUp(self) -> None:
        import qtawesome

        from ui import qta_fit

        self._qta_icon = qtawesome.icon
        self._saved = qta_fit._ORIGINAL_ICON
        # Меряем из чистого состояния: приложение ставит обёртку при запуске.
        if qta_fit._ORIGINAL_ICON is not None:
            qtawesome.icon = qta_fit._ORIGINAL_ICON
            qta_fit._ORIGINAL_ICON = None

    def tearDown(self) -> None:
        import qtawesome

        from ui import qta_fit

        qtawesome.icon = self._qta_icon
        qta_fit._ORIGINAL_ICON = self._saved

    def _install(self) -> None:
        from ui.qta_fit import install_wide_glyph_fit

        self.assertTrue(install_wide_glyph_fit())

    def test_wide_glyphs_were_clipped_and_now_fit_like_regular_ones(self) -> None:
        regular_left, regular_right, _t, _b = _ink("fa5b.telegram")
        regular_width = regular_right - regular_left + 1

        for name in ("fa5s.gamepad", "fa5s.network-wired", "fa5b.discord"):
            with self.subTest(name=name, stage="до"):
                left, right, _t, _b = _ink(name)
                # Упирается в оба края — значит, срезан.
                self.assertEqual((left, right), (0, SIZE - 1))

        self._install()
        for name in ("fa5s.gamepad", "fa5s.network-wired", "fa5b.discord"):
            with self.subTest(name=name, stage="после"):
                left, right, _t, _b = _ink(name)
                self.assertGreaterEqual(left, 1)
                self.assertLessEqual(right, SIZE - 2)
                self.assertLessEqual(abs((right - left + 1) - regular_width), 1)

    def test_regular_glyphs_are_untouched(self) -> None:
        import qtawesome

        before = {
            name: qtawesome.icon(name, color="#ffffff").pixmap(SIZE, SIZE).toImage()
            for name in ("fa5b.telegram", "fa5s.globe-europe", "mdi.robot")
        }
        self._install()
        for name, image in before.items():
            with self.subTest(name=name):
                after = qtawesome.icon(name, color="#ffffff").pixmap(SIZE, SIZE).toImage()
                self.assertEqual(after, image)

    def test_explicit_scale_factor_wins(self) -> None:
        from ui.qta_fit import fit_scale_factor, glyph_width_ratio

        self.assertAlmostEqual(glyph_width_ratio("fa5s.gamepad"), 1.25, places=2)
        self.assertEqual(fit_scale_factor(1.0), 1.0)
        self.assertLess(fit_scale_factor(1.25), 1.0)

        import qtawesome

        self._install()
        explicit = qtawesome.icon("fa5s.gamepad", color="#ffffff", scale_factor=1.0)
        image = explicit.pixmap(SIZE, SIZE).toImage()
        xs = [x for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 40]
        self.assertEqual((min(xs), max(xs)), (0, SIZE - 1))


if __name__ == "__main__":
    unittest.main()
