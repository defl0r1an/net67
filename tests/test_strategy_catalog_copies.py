"""Две копии каталога готовых стратегий не расходятся.

Программа и сборка (scripts/build_local.ps1, CI) берут каталог из
src/profile/strategy_catalogs, а правки, приходящие слиянием, и часть тестов —
из src/system/strategy_catalogs. Переименование 760 стратегий легло в
src/system, и тест названий был зелёным, хотя программа показывала бы
старые имена: копию, которую она читает, никто не тронул.
"""

from __future__ import annotations

import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
PROGRAM_COPY = SRC / "profile" / "strategy_catalogs"
MERGE_COPY = SRC / "system" / "strategy_catalogs"


class StrategyCatalogCopiesTests(unittest.TestCase):
    def test_program_copy_matches_merge_copy_byte_for_byte(self) -> None:
        program = {path.relative_to(PROGRAM_COPY).as_posix() for path in PROGRAM_COPY.glob("*/*.txt")}
        merge = {path.relative_to(MERGE_COPY).as_posix() for path in MERGE_COPY.glob("*/*.txt")}
        self.assertIn("winws2/tcp.txt", program)
        self.assertEqual(program, merge)
        differ = [
            rel for rel in sorted(program) if (PROGRAM_COPY / rel).read_bytes() != (MERGE_COPY / rel).read_bytes()
        ]
        self.assertEqual(differ, [])


if __name__ == "__main__":
    unittest.main()
