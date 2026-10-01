"""Оформление установщика и видимое окно при обновлении.

Установщик был стандартным: светлое окно, синий компьютер, «Вас
приветствует Мастер установки» — рядом с чёрно-белой программой он
выглядел чужим. А обновление из программы шло совсем без окна, и со
стороны программа просто исчезала.

Эти вещи легко потерять молча: уберёшь строку #include — установщик
соберётся и заработает, только снова станет стандартным; вернёшь
/VERYSILENT — обновление снова пройдёт без окна. Сборка об этом не
скажет, скажет тест.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer"

#: Цвет окна установщика в его тёмной теме. Им же залиты картинки.
WINDOW = (43, 43, 43)
SCALES = (100, 125, 150, 200, 250)


class LookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.iss = (INSTALLER / "net67.iss").read_text(encoding="utf-8")
        cls.look = (INSTALLER / "look.iss").read_text(encoding="utf-8")

    def test_installer_uses_the_look_file(self) -> None:
        self.assertIn('#include "look.iss"', self.iss)
        # Стиль задаётся в одном месте: две строки WizardStyle — и какая
        # победит, зависит от порядка.
        self.assertNotIn("WizardStyle=", self.iss)

    def test_window_is_dark_with_our_images(self) -> None:
        style = re.search(r"(?m)^WizardStyle=(.+)$", self.look)
        self.assertIsNotNone(style)
        words = style.group(1).split()
        for word in ("modern", "dark", "includetitlebar"):
            self.assertIn(word, words)
        self.assertRegex(self.look, r"(?m)^WizardImageFile=\{#ArtDir\}\\side-\*\.png$")
        self.assertRegex(self.look, r"(?m)^WizardSmallImageFile=\{#ArtDir\}\\small-\*\.png$")

    def test_no_second_background_colour(self) -> None:
        """Свой фон окна давал три оттенка серого: окно, заголовок, значок."""
        self.assertNotRegex(self.look, r"(?m)^WizardBackColor=")

    def test_welcome_page_is_on_and_speaks_our_words(self) -> None:
        self.assertRegex(self.look, r"(?m)^DisableWelcomePage=no$")
        self.assertIn("russian.WelcomeLabel1=Установка [name]", self.look)
        self.assertIn("russian.FinishedHeadingLabel=[name] установлен", self.look)
        messages = self.look.split("[Messages]", 1)[1]
        self.assertNotIn("Мастер установки", messages)

    def test_images_exist_for_every_screen_scale(self) -> None:
        for scale in SCALES:
            for kind in ("side", "small"):
                with self.subTest(file=f"{kind}-{scale}.png"):
                    self.assertTrue((INSTALLER / "art" / f"{kind}-{scale}.png").is_file())

    def test_images_are_painted_in_the_window_colour(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("нет Pillow")
        for scale in SCALES:
            for kind in ("side", "small"):
                with self.subTest(file=f"{kind}-{scale}.png"):
                    image = Image.open(INSTALLER / "art" / f"{kind}-{scale}.png")
                    # Без прозрачности: под прозрачным установщик
                    # подкладывал свой цвет, и значок стоял на светлом
                    # квадрате.
                    self.assertEqual(image.mode, "RGB")
                    width, height = image.size
                    for point in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
                        self.assertEqual(image.getpixel(point), WINDOW)

    def test_side_image_keeps_the_ratio_the_installer_needs(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("нет Pillow")
        for scale in SCALES:
            width, height = Image.open(INSTALLER / "art" / f"side-{scale}.png").size
            with self.subTest(scale=scale):
                self.assertAlmostEqual(width / height, 164 / 314, delta=0.01)


class VisibleUpdateTests(unittest.TestCase):
    def test_updater_shows_the_installer_window(self) -> None:
        source = (ROOT / "src" / "updater" / "update_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('"/SILENT"', source)
        self.assertNotIn('"/VERYSILENT"', source)
        # Без вопросов и без отмены: окно только показывает ход.
        for flag in ('"/AUTOUPDATE"', '"/SUPPRESSMSGBOXES"', '"/NOCANCEL"'):
            self.assertIn(flag, source)

    def test_update_window_says_what_to_do(self) -> None:
        iss = (INSTALLER / "net67.iss").read_text(encoding="utf-8")
        self.assertIn("procedure CurPageChanged(CurPageID: Integer);", iss)
        self.assertIn("'Обновление net67'", iss)
        self.assertIn("откроется сама", iss)

    def test_notice_before_closing_mentions_the_window(self) -> None:
        from importlib import import_module
        import sys

        if str(ROOT / "src") not in sys.path:
            sys.path.insert(0, str(ROOT / "src"))
        notice = import_module("updater.ui.closing_notice")
        _title, body = notice.closing_notice_text("0.14.67")
        self.assertIn("окно установки", body)
        self.assertIn("откроется сам", body)


if __name__ == "__main__":
    unittest.main()
