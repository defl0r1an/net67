"""Акцент приложения: один на весь интерфейс, и он не библиотечный.

История. Кнопка «Включить» была ярко-бирюзовой, и найти этот цвет в
проекте не удавалось: в branding.py лежал свой акцент, а на экране
светился #29f1ff. Оказалось, фирменный акцент при старте не применялся
вообще — оставалось умолчание самого qfluentwidgets (#009faa), которое
тёмная тема осветляет до бирюзы.

Потом облик взяли у плеера Nora, и требование «всё серое» отпало: у неё
графитовый фон и сиреневый акцент. Проверка на серость заменена на
проверку согласия — акцент branding и акцент оболочки обязаны быть
одного тона. Иначе повторяется то, что человек увидел на экране:
выделенный пункт панели сиреневый, а кнопка рядом бирюзовая.

Файл называется по-старому намеренно: переименование потеряло бы связь
с историей правок.
"""

from __future__ import annotations

import colorsys
import re
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

QT_RUNTIME = PROJECT_SRC / "main" / "qt_runtime.py"


def _channels(value: str) -> tuple[int, int, int]:
    raw = str(value).strip().lstrip("#")
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def _hue(value: str) -> float:
    red, green, blue = (channel / 255.0 for channel in _channels(value))
    return colorsys.rgb_to_hsv(red, green, blue)[0] * 360.0


class AccentTests(unittest.TestCase):
    def test_accent_agrees_with_the_shell(self) -> None:
        """Правая часть берёт цвет из branding, левая — из shell.theme."""
        from branding import PALETTE_LIGHT
        from shell.theme import DARK

        self.assertLess(abs(_hue(PALETTE_LIGHT.accent) - _hue(DARK.accent)), 12.0)

    def test_accent_is_not_the_library_default(self) -> None:
        """#009faa — умолчание qfluentwidgets, а не выбор приложения."""
        from branding import PALETTE_DARK, PALETTE_LIGHT

        for palette in (PALETTE_LIGHT, PALETTE_DARK):
            red, green, blue = _channels(palette.accent)
            with self.subTest(accent=palette.accent):
                self.assertFalse(green > red and blue > red, "акцент снова сине-зелёный")

    def test_ramp_gets_darker_monotonically(self) -> None:
        """Иначе наведение окажется темнее нажатия."""
        from branding import ACCENT_RAMP

        brightness = [
            sum(_channels(ACCENT_RAMP[step])) for step in sorted(ACCENT_RAMP)
        ]

        self.assertEqual(brightness, sorted(brightness, reverse=True))


class NeutralRampTests(unittest.TestCase):
    """Нейтральная шкала осталась серой: на ней держатся статусы."""

    def test_neutral_ramp_is_truly_grey(self) -> None:
        """Неравные каналы дают цветной налёт после осветления темой.

        Это не придирка: значение #6e6e76, где синий канал выше на
        восемь единиц, дало заметный лиловый налёт на белой кнопке.
        """
        from branding import NEUTRAL_RAMP

        for step, value in NEUTRAL_RAMP.items():
            red, green, blue = _channels(value)
            with self.subTest(step=step, value=value):
                self.assertEqual({red, green, blue}, {red})


class StartupTests(unittest.TestCase):
    def test_brand_accent_applies_without_a_user_choice(self) -> None:
        """Без этой ветки светилась бирюза — умолчание qfluentwidgets."""
        source = QT_RUNTIME.read_text(encoding="utf-8")

        block = source[source.index("load_accent_color") :]
        block = block[: block.index("emit_startup_metric")]

        self.assertIn("if not accent_hex:", block)
        self.assertIn("PALETTE_LIGHT.accent", block)

    def test_user_choice_still_wins(self) -> None:
        """Свой акцент из «Оформления» важнее фирменного умолчания."""
        source = QT_RUNTIME.read_text(encoding="utf-8")

        block = source[source.index("load_accent_color") :]
        block = block[: block.index("emit_startup_metric")]

        self.assertLess(block.index("if not accent_hex:"), block.index("PALETTE_LIGHT.accent"))


class LeftoverTests(unittest.TestCase):
    def test_the_old_cyan_is_gone_from_widgets(self) -> None:
        """#5fcdfe светился в подсветке выбранного DNS-профиля."""
        source = (PROJECT_SRC / "ui" / "fluent_widgets.py").read_text(encoding="utf-8")

        self.assertEqual(re.findall(r"#5[fF][cC][dD][fF][eE]", source), [])


if __name__ == "__main__":
    unittest.main()
