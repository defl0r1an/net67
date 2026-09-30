"""У каждого сервиса hosts свой значок, а не запасной глобус.

41 сервис показывался одинаковым глобусом, и плитки редактора hosts
различались только подписью. В zapret 21.1.6.43 значки получили все
сервисы; каталог net67 в JSON, и значки вписаны в него.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

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
        colourless = []
        for path in sorted(list((CATALOG / "dns").glob("*.json")) + list((CATALOG / "hosts").glob("*.json"))):
            data = json.loads(path.read_text(encoding="utf-8"))
            if not str(data.get("icon_color") or "").startswith("#"):
                colourless.append(data.get("name", path.name))
        self.assertEqual(colourless, [])


if __name__ == "__main__":
    unittest.main()
