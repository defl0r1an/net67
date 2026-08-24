"""Переключатель вкладок внутри страницы должен быть виден.

На странице VPN две вкладки — «Amnezia» и «VPN». В окне на их месте был
пустой тёмный прямоугольник: надписи не рисовались. Переключиться было
не на что, человек оставался на первой вкладке и видел её тексты —
«Подключение через AmneziaWG или WireGuard» на вкладке ссылок.

## Причина

Таблица стилей Qt каскадом уходит в потомков. Одна строка `background:`
на родителе перекрывает собственную таблицу qfluentwidgets, а именно ею
и задан цвет надписей SegmentedItem.

Замер на одной и той же полосе:

    родитель без стилей   — 15742 светлых пикселя
    родитель с background —    69

Поэтому цвет задаётся у нас, в shell/theme.py, а не берётся у
библиотеки. Тест меряет ровно это: под нашей таблицей стилей надписи
обязаны остаться видимыми.
"""

from __future__ import annotations

import os
import sys
import unittest
from collections import Counter
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


#: Ниже этого числа светлых пикселей надписи считаем пропавшими.
#: Целых надписей примерно пятнадцать тысяч, пустой полосы — семь
#: десятков; порог взят с большим запасом от обоих значений.
VISIBLE_PIXELS_MIN = 2000


def _light_pixels(stylesheet: str) -> int:
    from PyQt6.QtWidgets import QVBoxLayout, QWidget
    from qfluentwidgets import SegmentedWidget, Theme, setTheme

    setTheme(Theme.DARK)

    host = QWidget()
    host.resize(700, 90)
    host.setStyleSheet(stylesheet)
    layout = QVBoxLayout(host)
    tabs = SegmentedWidget(host)
    for key, title in (("amnezia", "Amnezia"), ("links", "VPN")):
        tabs.addItem(key, title, lambda: None)
    tabs.setCurrentItem("amnezia")
    layout.addWidget(tabs)
    host.show()
    _APP.processEvents()

    image = host.grab().toImage()
    counter = Counter(
        image.pixelColor(x, y).name()
        for x in range(0, host.width(), 2)
        for y in range(0, host.height(), 2)
    )
    host.deleteLater()
    return sum(count for colour, count in counter.items() if int(colour[1:3], 16) > 120)


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class SegmentedTabsTests(unittest.TestCase):
    def test_labels_survive_our_stylesheet(self) -> None:
        from shell.theme import palette, shell_qss

        visible = _light_pixels(shell_qss(palette(True)))

        self.assertGreater(visible, VISIBLE_PIXELS_MIN)

    def test_a_bare_background_rule_is_what_used_to_erase_them(self) -> None:
        """Проверка самой причины: без нашего правила надписи пропадают.

        Если однажды qfluentwidgets перестанет так реагировать на каскад,
        этот тест упадёт — и правило в теме можно будет убрать.
        """
        self.assertLess(_light_pixels("background: #101010;"), VISIBLE_PIXELS_MIN)

    def test_theme_styles_the_item_class_by_name(self) -> None:
        from shell.theme import palette, shell_qss

        qss = shell_qss(palette(True))

        self.assertIn("SegmentedItem", qss)
        self.assertIn("SegmentedItem:checked", qss)


if __name__ == "__main__":
    unittest.main()
