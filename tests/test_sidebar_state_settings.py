from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class SidebarStateSettingsTests(unittest.TestCase):
    def test_normalize_settings_keeps_sidebar_expanded_state(self) -> None:
        from settings.normalize import normalize_settings

        normalized = normalize_settings({"ui_state": {"sidebar_expanded": True, "unknown": "ignored"}})

        # Проверяем сохранение значения и отбрасывание мусора, а не точный
        # набор ключей: сверка всего словаря ломалась при каждом новом поле.
        self.assertTrue(normalized["ui_state"]["sidebar_expanded"])
        self.assertNotIn("unknown", normalized["ui_state"])

    def test_normalize_settings_defaults_advanced_mode_to_simple(self) -> None:
        """Новая установка должна открываться в простом интерфейсе."""
        from settings.normalize import normalize_settings

        normalized = normalize_settings({})

        self.assertFalse(normalized["ui_state"]["advanced_mode"])

    def test_normalize_settings_keeps_advanced_mode_when_enabled(self) -> None:
        from settings.normalize import normalize_settings

        normalized = normalize_settings({"ui_state": {"advanced_mode": True}})

        self.assertTrue(normalized["ui_state"]["advanced_mode"])


if __name__ == "__main__":
    unittest.main()
