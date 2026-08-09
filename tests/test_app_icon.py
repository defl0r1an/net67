"""Значок приложения.

Знак «67» на тёмной плашке — из макета логотипа. Проверяется не
красота, а то, что ломается молча: пропавший размер, съехавший центр,
слишком мелкий знак на 16 пикселях и рассинхрон двух копий файла.

## Почему копий две

`ico/net67.ico` берёт сборщик exe и установщик, `src/ico/net67.ico` —
приложение в режиме разработки. Разойтись они могут незаметно: сборка
покажет новый значок, а запуск из исходников — старый. Поэтому файлы
сверяются побайтово.

## Про размеры

Windows сам уменьшит 256 до 16, но своим алгоритмом, и тонкие штрихи
Barlow Condensed при этом сливаются. Каждый размер нарисован отдельно,
и тест следит, чтобы набор не поредел.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Приложение Qt создаётся один раз при импорте модуля — так же, как в
# остальных тестах с Qt. Создание внутри теста роняло весь прогон:
# к тому моменту Qt уже поднят соседними файлами, и второй вызов
# обрывает процесс, а не возвращает ошибку.
try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]

BUILD_ICON = PROJECT_ROOT / "ico" / "net67.ico"
DEV_ICON = PROJECT_ROOT / "src" / "ico" / "net67.ico"

#: Размеры, которые обязаны быть внутри .ico.
REQUIRED_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

#: Цвета из макета логотипа.
PLATE = (23, 23, 23)
GLYPH_MIN_BRIGHTNESS = 200


def _frame(path: Path, size: int):
    from PIL import Image

    image = Image.open(path)
    image.size = (size, size)
    return image.convert("RGBA")


def _ink_bounds(image) -> tuple[int, int, int, int]:
    """Границы светлого знака внутри плашки."""
    width, height = image.size
    pixels = image.load()
    points = [
        (x, y)
        for x in range(width)
        for y in range(height)
        if pixels[x, y][0] >= GLYPH_MIN_BRIGHTNESS and pixels[x, y][3] > 128
    ]
    assert points, "знак не найден: плашка пустая"
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (min(xs), min(ys), max(xs), max(ys))


class FilesTests(unittest.TestCase):
    def test_both_copies_exist(self) -> None:
        for path in (BUILD_ICON, DEV_ICON):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), path)

    def test_copies_are_identical(self) -> None:
        """Разойдясь, они дают разный значок в сборке и при разработке."""
        self.assertEqual(BUILD_ICON.read_bytes(), DEV_ICON.read_bytes())

    def test_builder_script_is_kept(self) -> None:
        """Значок должен пересобираться, а не править́ся в редакторе."""
        self.assertTrue((PROJECT_ROOT / "scripts" / "build_icon.py").is_file())


class SizesTests(unittest.TestCase):
    def test_every_required_size_is_inside(self) -> None:
        from PIL import Image

        sizes = {size for size in Image.open(BUILD_ICON).info.get("sizes", ())}

        for size in REQUIRED_SIZES:
            with self.subTest(size=size):
                self.assertIn((size, size), sizes)


class MarkTests(unittest.TestCase):
    def test_plate_colour_matches_the_layout(self) -> None:
        image = _frame(BUILD_ICON, 256)
        pixels = image.load()

        self.assertEqual(pixels[128, 6][:3], PLATE)

    def test_corners_are_rounded(self) -> None:
        """Плашка приложения в макете со скруглением, а не квадрат."""
        image = _frame(BUILD_ICON, 256)
        pixels = image.load()

        self.assertEqual(pixels[0, 0][3], 0)
        self.assertEqual(pixels[128, 6][3], 255)

    def test_mark_is_centred(self) -> None:
        """Первая версия центрировала строку, а не краску.

        Приподнятая шестёрка утаскивала знак вверх: замер давал 50
        пикселей сверху против 67 снизу.
        """
        for size in (32, 48, 256):
            with self.subTest(size=size):
                image = _frame(BUILD_ICON, size)
                left, top, right, bottom = _ink_bounds(image)
                centre = (size - 1) / 2.0

                self.assertLessEqual(abs((left + right) / 2.0 - centre), size * 0.02)
                self.assertLessEqual(abs((top + bottom) / 2.0 - centre), size * 0.02)

    def test_mark_is_readable_at_tray_size(self) -> None:
        """На 16 пикселях знак должен занимать не меньше 40% плашки.

        При пропорции макета (56%) на 16 пикселях цифры выходили в 9
        пикселей высотой и переставали читаться, поэтому мелкие размеры
        рисуются с более крупным знаком.
        """
        image = _frame(BUILD_ICON, 16)
        left, top, right, bottom = _ink_bounds(image)

        self.assertGreaterEqual(right - left + 1, 7)
        self.assertGreaterEqual(bottom - top + 1, 7)

    def test_mark_does_not_touch_the_edges(self) -> None:
        """Знак впритык к краю выглядит обрезанным на скруглении."""
        for size in (16, 32, 256):
            with self.subTest(size=size):
                image = _frame(BUILD_ICON, size)
                left, top, right, bottom = _ink_bounds(image)

                self.assertGreater(left, 0)
                self.assertGreater(top, 0)
                self.assertLess(right, size - 1)
                self.assertLess(bottom, size - 1)


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class QtTests(unittest.TestCase):
    def test_qt_can_read_every_size(self) -> None:
        """Приложение берёт значок через QIcon; битый файл там молчит."""
        from PyQt6.QtGui import QIcon

        icon = QIcon(str(BUILD_ICON))

        self.assertFalse(icon.isNull())
        available = {(size.width(), size.height()) for size in icon.availableSizes()}
        for size in REQUIRED_SIZES:
            with self.subTest(size=size):
                self.assertIn((size, size), available)


if __name__ == "__main__":
    unittest.main()
