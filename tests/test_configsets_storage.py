from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


def _settings() -> dict:
    return {
        "version": 1,
        "program": {"dpi_autostart": True},
        "appearance": {"theme": "dark"},
        "telegram_proxy": {"enabled": True, "upstream_pass": "s3cret"},
        "window": {"geometry": "1920x1080"},
    }


class ConfigNameTests(unittest.TestCase):
    def test_unsafe_characters_are_removed(self) -> None:
        from configsets.storage import normalize_name

        self.assertEqual(normalize_name("Офис / отдел 3"), "Офис отдел 3")

    def test_cyrillic_names_are_allowed(self) -> None:
        """В отличие от имени службы, здесь это просто имя файла."""
        from configsets.storage import normalize_name

        self.assertEqual(normalize_name("Домашний"), "Домашний")

    def test_empty_name_is_empty(self) -> None:
        from configsets.storage import normalize_name

        self.assertEqual(normalize_name("///"), "")

    def test_name_is_truncated(self) -> None:
        from configsets.storage import normalize_name

        self.assertLessEqual(len(normalize_name("и" * 200)), 48)


class ConfigStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_directory_gives_empty_list(self) -> None:
        from configsets.storage import list_configs

        self.assertEqual(list_configs(self.root), [])

    def test_save_and_list(self) -> None:
        from configsets.storage import list_configs, save_config

        ok, message = save_config(self.root, name="Офис", settings=_settings())
        self.assertTrue(ok, message)

        items = list_configs(self.root)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "Офис")
        self.assertTrue(items[0].saved_at > 0)

    def test_empty_name_is_refused(self) -> None:
        from configsets.storage import save_config

        ok, message = save_config(self.root, name="  ", settings=_settings())

        self.assertFalse(ok)
        self.assertIn("название", message.lower())

    def test_saved_set_has_no_secrets_by_default(self) -> None:
        """Набор нужен для переключения режимов, а не для хранения паролей."""
        import json

        from configsets.storage import config_path, save_config

        save_config(self.root, name="Офис", settings=_settings())
        raw = json.loads(config_path(self.root, "Офис").read_text(encoding="utf-8"))

        self.assertEqual(raw["sections"]["telegram_proxy"]["upstream_pass"], "")

    def test_saving_reports_that_secrets_were_skipped(self) -> None:
        from configsets.storage import save_config

        _ok, message = save_config(self.root, name="Офис", settings=_settings())

        self.assertIn("учётные данные", message.lower())

    def test_apply_restores_saved_values(self) -> None:
        from configsets.storage import apply_config, config_path, save_config

        save_config(self.root, name="Офис", settings=_settings())

        current = _settings()
        current["appearance"]["theme"] = "light"
        result, message = apply_config(config_path(self.root, "Офис"), current=current)

        self.assertIsNotNone(result, message)
        self.assertEqual(result["appearance"]["theme"], "dark")

    def test_apply_does_not_wipe_password(self) -> None:
        from configsets.storage import apply_config, config_path, save_config

        save_config(self.root, name="Офис", settings=_settings())
        result, _ = apply_config(config_path(self.root, "Офис"), current=_settings())

        self.assertEqual(result["telegram_proxy"]["upstream_pass"], "s3cret")

    def test_corrupted_file_is_skipped_not_fatal(self) -> None:
        from configsets.storage import CONFIG_FILE_SUFFIX, configs_dir, list_configs, save_config

        save_config(self.root, name="Хороший", settings=_settings())
        broken = configs_dir(self.root) / f"Битый{CONFIG_FILE_SUFFIX}"
        broken.write_text("{не json", encoding="utf-8")

        items = list_configs(self.root)

        self.assertEqual([i.name for i in items], ["Хороший"])

    def test_apply_missing_file_reports_error(self) -> None:
        from configsets.storage import apply_config

        result, message = apply_config(self.root / "нет.json", current=_settings())

        self.assertIsNone(result)
        self.assertTrue(message)

    def test_delete_removes_set(self) -> None:
        from configsets.storage import config_path, delete_config, list_configs, save_config

        save_config(self.root, name="Офис", settings=_settings())
        ok, _ = delete_config(config_path(self.root, "Офис"))

        self.assertTrue(ok)
        self.assertEqual(list_configs(self.root), [])

    def test_delete_missing_file_is_not_an_error(self) -> None:
        from configsets.storage import delete_config

        self.assertTrue(delete_config(self.root / "нет.json")[0])

    def test_resaving_same_name_overwrites(self) -> None:
        from configsets.storage import list_configs, save_config

        save_config(self.root, name="Офис", settings=_settings())
        changed = _settings()
        changed["appearance"]["theme"] = "light"
        save_config(self.root, name="Офис", settings=changed)

        self.assertEqual(len(list_configs(self.root)), 1)


if __name__ == "__main__":
    unittest.main()
