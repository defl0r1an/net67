"""У каждого сервиса hosts свой значок, а не запасной глобус.

41 сервис показывался одинаковым глобусом, и плитки редактора hosts
различались только подписью. В zapret 21.1.6.43 значки получили все
сервисы; каталог net67 в JSON, и значки вписаны в него.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CATALOG = Path(__file__).resolve().parents[1] / "json" / "hosts_catalog"


class CatalogIconsTests(unittest.TestCase):
    def test_no_service_falls_back_to_globe(self) -> None:
        globes = []
        for path in sorted(list((CATALOG / "dns").glob("*.json")) + list((CATALOG / "hosts").glob("*.json"))):
            data = json.loads(path.read_text(encoding="utf-8"))
            icon = str(data.get("icon") or "")
            if not icon or "globe" in icon:
                globes.append(data.get("name", path.name))
        self.assertEqual(globes, [])

    def test_icons_have_a_colour(self) -> None:
        # null — только у одноцветных логотипов (Grok, Manus): плитка рисует
        # их цветом текста темы, иначе на светлой или тёмной теме они пропадут.
        colourless = []
        for path in sorted(list((CATALOG / "dns").glob("*.json")) + list((CATALOG / "hosts").glob("*.json"))):
            data = json.loads(path.read_text(encoding="utf-8"))
            color = data.get("icon_color")
            if color is None and str(data.get("icon") or "").startswith("own:"):
                continue
            if not str(color or "").startswith("#"):
                colourless.append(data.get("name", path.name))
        self.assertEqual(colourless, [])

    def test_every_own_logo_is_drawn(self) -> None:
        """Логотипы, которых нет в Simple Icons (OpenAI убрали оттуда), — свои SVG."""
        from profile.ui.own_icons import OWN_ICON_SVGS

        names = {}
        for path in sorted(list((CATALOG / "dns").glob("*.json")) + list((CATALOG / "hosts").glob("*.json"))):
            data = json.loads(path.read_text(encoding="utf-8"))
            icon = str(data.get("icon") or "")
            if icon.startswith("own:"):
                names[data.get("name", path.name)] = icon.removeprefix("own:").partition(":")[0]
        self.assertEqual(names.get("ChatGPT & Sora (OpenAI)"), "openai")
        self.assertEqual({name: slug for name, slug in names.items() if slug not in OWN_ICON_SVGS}, {})

    def test_every_brand_logo_is_in_the_bundle(self) -> None:
        """Логотип, которого нет в бандле, рисуется квадратом с буквами.

        Бандл собирает tools/generate_profile_icon_bundle.py из пакета
        simplepycons: в самой программе пакета нет (3400 модулей, 2,6 с
        на импорт). Поменял значок сервиса — перезапусти генератор.
        """
        from profile.ui.simple_icons_bundle import SIMPLE_ICON_SVGS

        slugs = {}
        for path in sorted(list((CATALOG / "dns").glob("*.json")) + list((CATALOG / "hosts").glob("*.json"))):
            data = json.loads(path.read_text(encoding="utf-8"))
            icon = str(data.get("icon") or "")
            if icon.startswith("simple:"):
                slugs[data.get("name", path.name)] = icon.removeprefix("simple:").partition(":")[0]
        self.assertIn("discord", slugs.values())
        self.assertEqual({name: slug for name, slug in slugs.items() if slug not in SIMPLE_ICON_SVGS}, {})


    def test_no_service_uses_a_generic_font_icon(self) -> None:
        """Значок из шрифта — общий рисунок, а не логотип.

        Вентилятор у Dyson, корзина у Best Buy, чип сразу у Analog Devices,
        Arrow и Microchip, робот у шести нейросетей: 42 плитки различались
        только подписью. Логотипы из шрифта (fa5b.*) — настоящие, их можно.
        """
        generic = {}
        for path in sorted(list((CATALOG / "dns").glob("*.json")) + list((CATALOG / "hosts").glob("*.json"))):
            data = json.loads(path.read_text(encoding="utf-8"))
            icon = str(data.get("icon") or "")
            if icon.startswith("fa5s."):
                generic[data.get("name", path.name)] = icon
        self.assertEqual(generic, {})

    def test_every_brand_image_is_drawn(self) -> None:
        """Картинка "img:" есть в brand_images.py и читается Qt.

        Без картинки плитка молча рисует квадрат с буквами — опечатку в имени
        глазами на странице не заметить.
        """
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtGui import QGuiApplication

        from profile.ui.brand_images import BRAND_IMAGE_MASKS, BRAND_IMAGE_PNGS, BRAND_IMAGE_SOURCES
        from profile.ui.profile_icon import profile_icon_pixmap

        _app = QGuiApplication.instance() or QGuiApplication([])
        keys = {}
        for path in sorted(list((CATALOG / "dns").glob("*.json")) + list((CATALOG / "hosts").glob("*.json"))):
            data = json.loads(path.read_text(encoding="utf-8"))
            icon = str(data.get("icon") or "")
            if icon.startswith("img:"):
                keys[data.get("name", path.name)] = icon.removeprefix("img:").partition(":")[0]
        self.assertIn("lego", keys.values())
        self.assertEqual({name: key for name, key in keys.items() if key not in BRAND_IMAGE_PNGS}, {})
        self.assertEqual(set(BRAND_IMAGE_PNGS), set(BRAND_IMAGE_SOURCES))
        self.assertLessEqual(BRAND_IMAGE_MASKS, set(BRAND_IMAGE_PNGS))

        fallback = profile_icon_pixmap("profile-initials:XX", color="#123456", size=20).toImage()
        for key in sorted(set(keys.values())):
            image = profile_icon_pixmap(f"img:{key}:XX", color="#123456", size=20).toImage()
            self.assertEqual((image.width(), image.height()), (20, 20), key)
            self.assertNotEqual(image, fallback, key)

    def test_muted_brand_image_is_grey_and_keeps_transparency(self) -> None:
        """Выключенный сервис с цветной картинкой должен выглядеть выключенным.

        Одноцветный значок выключенной плитки приходит серым цветом, а
        картинка цвет не берёт: без серого варианта красный логотип LEGO
        выглядел одинаково и во включённом, и в выключенном виде.
        """
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtGui import QGuiApplication

        from profile.ui.profile_icon import profile_icon_pixmap

        _app = QGuiApplication.instance() or QGuiApplication([])
        bright = profile_icon_pixmap("img:lego:LE", color="#999999", size=20).toImage()
        muted = profile_icon_pixmap("img:lego:LE", color="#999999", size=20, muted=True).toImage()
        coloured = 0
        for y in range(20):
            for x in range(20):
                before, after = bright.pixelColor(x, y), muted.pixelColor(x, y)
                self.assertEqual(before.alpha(), after.alpha(), (x, y))
                if after.alpha():
                    self.assertEqual(after.red(), after.green(), (x, y))
                    self.assertEqual(after.green(), after.blue(), (x, y))
                if before.alpha() and abs(before.red() - before.green()) > 40:
                    coloured += 1
        self.assertGreater(coloured, 20)

    def test_dark_silhouette_takes_the_catalog_colour(self) -> None:
        """Чёрный призрак Aave на тёмной теме пропадал: силуэт красится цветом каталога."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtGui import QGuiApplication

        from profile.ui.profile_icon import profile_icon_pixmap

        _app = QGuiApplication.instance() or QGuiApplication([])
        image = profile_icon_pixmap("img:aave:AA", color="#B6509E", size=20).toImage()
        opaque = [image.pixelColor(x, y) for y in range(20) for x in range(20) if image.pixelColor(x, y).alpha() > 200]
        self.assertGreater(len(opaque), 20)
        # ±2 на канал — округление при умножении на прозрачность в QPixmap.
        target = (0xB6, 0x50, 0x9E)
        for c in opaque:
            self.assertLessEqual(max(abs(a - b) for a, b in zip(c.getRgb()[:3], target)), 2, c.name())
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)


if __name__ == "__main__":
    unittest.main()
