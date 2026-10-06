"""У каждого сервиса hosts свой значок, а не запасной глобус.

41 сервис показывался одинаковым глобусом, и плитки редактора hosts
различались только подписью. В zapret 21.1.6.43 значки получили все
сервисы; каталог net67 в JSON, и значки вписаны в него.
"""

from __future__ import annotations

import json
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


if __name__ == "__main__":
    unittest.main()
