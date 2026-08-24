"""Блокировка MAX пишет в hosts своё имя, а чужое умеет убирать.

Владелец приложения открыл `C:\\Windows\\System32\\drivers\\etc\\hosts` и
увидел там «# MAX BLOCKED BY ZAPRET GUI» — имя проекта, из которого net67
сделан. Файл системный, его открывают блокнотом, и вычистить оттуда
чужое имя важнее, чем из любого места в коде.

Просто переименовать метку было нельзя. У всех, кто уже включал
блокировку, в hosts лежит блок со старой меткой. Снятие блокировки ищет
метку — и с новой прошло бы мимо старого блока. Домены MAX остались бы
перенаправлены на 127.0.0.1 навсегда, а понять, кто это сделал, стало бы
не по чему.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class MarkerTests(unittest.TestCase):
    def _module(self):
        try:
            from windows_features import max_blocker
        except Exception as exc:  # pragma: no cover - модуль требует winreg
            raise unittest.SkipTest(f"max_blocker недоступен: {exc}") from exc
        return max_blocker

    def test_written_marker_carries_our_name(self) -> None:
        module = self._module()

        self.assertIn("net67", module.HOSTS_MARKER_BEGIN)
        self.assertNotIn("ZAPRET", module.HOSTS_MARKER_BEGIN.upper())

    def test_blocking_file_carries_our_name(self) -> None:
        """Файл-заглушка в папке установки MAX — его тоже открывают."""
        module = self._module()

        self.assertIn("net67", module.BLOCKING_FILE_CONTENT)
        self.assertNotIn("ZAPRET", module.BLOCKING_FILE_CONTENT.upper())

    def test_old_marker_is_still_recognised(self) -> None:
        module = self._module()

        self.assertTrue(module._hosts_block_starts("# MAX BLOCKED BY ZAPRET GUI"))

    def test_new_marker_is_recognised(self) -> None:
        module = self._module()

        self.assertTrue(module._hosts_block_starts(module.HOSTS_MARKER_BEGIN))

    def test_other_lines_are_left_alone(self) -> None:
        """В hosts живут чужие записи, и трогать их нельзя."""
        module = self._module()

        for line in ("127.0.0.1 localhost", "# user comment", ""):
            with self.subTest(line=line):
                self.assertFalse(module._hosts_block_starts(line))

    def test_legacy_list_is_not_empty(self) -> None:
        """Опустеет — и старые блоки станет нечем находить."""
        module = self._module()

        self.assertTrue(module.LEGACY_HOSTS_MARKERS)


if __name__ == "__main__":
    unittest.main()
