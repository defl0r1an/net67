"""В settings.json не должно быть ключей от вырезанных возможностей.

Файл настроек виден человеку — его показывает раздел «Конфигурации» и он
же уезжает на другие машины при переносе. Каждый мёртвый ключ там это
вопрос «а это что и можно ли трогать», на который нет честного ответа.

Убрано:

* раздел `premium` целиком — подписки нет;
* раздел `orchestra` целиком, вместе с девятью типами трафика в четырёх
  картах — оркестратор вырезан;
* `appearance.garland_enabled` и `appearance.snowflakes_enabled` —
  гирлянда и снежинки из премиум-эффектов;
* `appearance.selected_theme` — раздел выбора тем вырезан;
* `appearance.rkn_background` и вариант `background_preset: rkn_chan` —
  фон из исходного проекта;
* `program.selected_source_preset_file_name_winws1` — движок winws1
  вырезан;
* `program.remove_github_api` и `hosts.bootstrap_signature` — разовая
  чистка api.github.com из hosts. Её единственным читателем был
  bootstrap в HostsManager, а он переписывал строки человека в hosts;
  в zapret его убрали вместе с новым редактором hosts.

Оставлено намеренно: `discord_auto_restart` (им управляет меню в трее),
`defender_disabled`.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from settings.normalize import normalize_settings  # noqa: E402
from settings.schema import VALID_BACKGROUND_PRESETS, build_default_settings  # noqa: E402


DEAD_SECTIONS = ("premium", "orchestra")

DEAD_FIELDS = {
    "appearance": ("garland_enabled", "snowflakes_enabled", "selected_theme", "rkn_background"),
    "program": ("selected_source_preset_file_name_winws1", "remove_github_api"),
    "hosts": ("bootstrap_signature",),
}

ALIVE_FIELDS = {
    "program": ("discord_auto_restart", "defender_disabled"),
}


class DefaultSettingsTests(unittest.TestCase):
    def test_dead_sections_are_gone(self) -> None:
        defaults = build_default_settings()

        for section in DEAD_SECTIONS:
            self.assertNotIn(section, defaults, f"раздел {section} должен быть удалён")

    def test_dead_fields_are_gone(self) -> None:
        defaults = build_default_settings()

        for section, fields in DEAD_FIELDS.items():
            for field in fields:
                self.assertNotIn(
                    field,
                    defaults.get(section, {}),
                    f"{section}.{field} должен быть удалён",
                )

    def test_alive_fields_stayed(self) -> None:
        """Эти выглядят подозрительно, но ими пользуются."""
        defaults = build_default_settings()

        for section, fields in ALIVE_FIELDS.items():
            for field in fields:
                self.assertIn(field, defaults[section], f"{section}.{field} убирать нельзя")

    def test_rkn_background_preset_is_not_selectable(self) -> None:
        self.assertNotIn("rkn_chan", VALID_BACKGROUND_PRESETS)
        self.assertIn("standard", VALID_BACKGROUND_PRESETS)


class NormalizationTests(unittest.TestCase):
    def test_old_settings_lose_the_dead_keys(self) -> None:
        """Файл со старой машины не тащит мёртвые ключи обратно."""
        old = build_default_settings()
        old["premium"] = {"device_id": "ABC-123"}
        old["orchestra"] = {"settings": {"strict_detection": True}}
        old["appearance"]["garland_enabled"] = True
        old["appearance"]["snowflakes_enabled"] = True
        old["appearance"]["selected_theme"] = "какая-то тема"
        old["appearance"]["rkn_background"] = "themes/картинка.png"
        old["program"]["selected_source_preset_file_name_winws1"] = "старый.txt"

        result = normalize_settings(json.loads(json.dumps(old)))

        for section in DEAD_SECTIONS:
            self.assertNotIn(section, result)
        for section, fields in DEAD_FIELDS.items():
            for field in fields:
                self.assertNotIn(field, result.get(section, {}))

    def test_rkn_background_preset_falls_back_to_standard(self) -> None:
        old = build_default_settings()
        old["appearance"]["background_preset"] = "rkn_chan"

        result = normalize_settings(json.loads(json.dumps(old)))

        self.assertEqual(result["appearance"]["background_preset"], "standard")

    def test_normalization_is_stable(self) -> None:
        defaults = build_default_settings()
        self.assertEqual(normalize_settings(json.loads(json.dumps(defaults))), defaults)


class StoreTests(unittest.TestCase):
    def test_dead_accessors_are_gone(self) -> None:
        import settings.store as store

        dead = [
            name
            for name in dir(store)
            if "orchestra" in name
            or "premium" in name
            or name.endswith(("garland_enabled", "snowflakes_enabled", "selected_theme", "rkn_background"))
        ]

        self.assertEqual(dead, [], f"в хранилище остались мёртвые функции: {dead}")


if __name__ == "__main__":
    unittest.main()
