"""Надписи вкладок остаются читаемыми при каскаде таблицы стилей.

Общая площадь светлых пикселей не проверяет буквы: в неё попадали
подложка выбранного пункта и прозрачный белый. Сравниваем одну и ту же
полосу с текстом и без него, отдельно для каждого пункта.
"""

from __future__ import annotations

import os
import sys
import unittest
import functools
import json
import subprocess
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_APP = None


# Считается контрастный след каждой надписи относительно полосы без текста.
# Светлая подложка выбранного пункта не должна подменять видимость букв.
VISIBLE_PIXELS_MIN = 20


def _caption_pixels(stylesheet: str) -> dict[str, int]:
    from PyQt6.QtCore import QPoint, QRect, Qt
    from PyQt6.QtGui import QFont, QFontDatabase
    from PyQt6.QtWidgets import QVBoxLayout, QWidget
    from qfluentwidgets import SegmentedWidget, Theme, setTheme

    from PyQt6.QtTest import QTest
    setTheme(Theme.DARK, save=False)
    # Offscreen на Windows не загружает системные шрифты сам. Без этого
    # прежний замер подтверждал светлую подложку даже при отсутствующих буквах.
    font_id = -1
    if sys.platform == "win32":
        font_id = QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"))

    host = QWidget()
    host.setObjectName("net67Window")
    host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    host.resize(700, 90)
    host.setStyleSheet(stylesheet)
    layout = QVBoxLayout(host)
    tabs = SegmentedWidget(host)
    for key, title in (("amnezia", "Amnezia"), ("links", "VPN")):
        tabs.addItem(key, title, lambda: None)
        tabs.widget(key).setFont(QFont("Segoe UI", 10) if sys.platform == "win32" else _APP.font())
    tabs.setCurrentItem("amnezia")
    layout.addWidget(tabs)
    host.show()
    QTest.qWait(300)

    image = host.grab().toImage().copy()
    regions = {}
    tabs.setFixedSize(tabs.size())
    for key in ("amnezia", "links"):
        item = tabs.widget(key)
        regions[key] = QRect(item.mapTo(host, QPoint(0, 0)), item.size()).adjusted(8, 6, -8, -6)
        item.setFixedSize(item.size())
        item.setText("")
    QTest.qWait(30)
    blank = host.grab().toImage()
    visible = {}
    def brightness(color):
        # У прозрачного белого RGB тоже равен 255. Считаем видимый цвет
        # на тёмной подложке, иначе тест «видит» невидимые пиксели.
        alpha = color.alphaF()
        return color.lightness() * alpha + 16 * (1 - alpha)
    for key, rect in regions.items():
        visible[key] = sum(
            abs(brightness(image.pixelColor(x, y)) - brightness(blank.pixelColor(x, y))) > 60
            for x in range(rect.left(), rect.right())
            for y in range(rect.top(), rect.bottom())
        )
    host.deleteLater()
    if font_id >= 0:
        QFontDatabase.removeApplicationFont(font_id)
    return visible


@functools.lru_cache(maxsize=1)
def _measurements():
    # Полный набор оставляет глобальные стили/таймеры Qt от других страниц.
    # Проверяем настоящий каскад в свежем процессе, как при запуске программы.
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--measure"],
                               capture_output=True, text=True, encoding="utf-8", timeout=30,
                               env=dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1"),
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout.strip().splitlines()[-1])


class SegmentedTabsTests(unittest.TestCase):
    def test_labels_survive_our_stylesheet(self) -> None:
        visible = _measurements()["native"]

        self.assertTrue(all(value > VISIBLE_PIXELS_MIN for value in visible.values()), visible)

    def test_our_rules_restore_captions_over_inherited_wrong_colours(self) -> None:
        hidden = _measurements()["hidden"]
        restored = _measurements()["restored"]
        self.assertTrue(any(value < VISIBLE_PIXELS_MIN for value in hidden.values()), hidden)
        self.assertTrue(all(value > VISIBLE_PIXELS_MIN for value in restored.values()), restored)

    def test_theme_styles_the_item_class_by_name(self) -> None:
        from shell.theme import palette, shell_qss

        qss = shell_qss(palette(True))

        self.assertIn("SegmentedItem", qss)
        self.assertIn("SegmentedItem:checked", qss)


if __name__ == "__main__":
    if "--measure" in sys.argv:
        from PyQt6.QtCore import QCoreApplication, QEvent
        from PyQt6.QtWidgets import QApplication
        from shell.theme import palette, shell_qss
        _APP = QApplication([])
        inherited = "SegmentedWidget SegmentedItem { background: #101010; color: #101010; }"
        result = {"native": _caption_pixels(shell_qss(palette(True))),
                  "hidden": _caption_pixels(inherited),
                  "restored": _caption_pixels(inherited + shell_qss(palette(True)))}
        _APP.closeAllWindows()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        print(json.dumps(result), flush=True)
        # Пиксели и cleanup уже проверены; общий обход деструкторов PyQt на
        # Windows здесь не проверяется и не должен убивать соседний прогон.
        os._exit(0)
    unittest.main()
