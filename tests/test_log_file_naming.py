"""Журнал программы называется по-нашему, а прежние файлы не теряются.

Файл журнала назывался zapret_log_<время>.txt — имя досталось от zapret.
У тех, кто ставил прежние версии, такие файлы уже лежат в logs/.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class LogFileNamingTests(unittest.TestCase):
    def test_new_log_is_named_net67(self) -> None:
        from log.log import get_current_log_filename

        name = get_current_log_filename()
        self.assertTrue(name.startswith("net67_log_"), name)
        self.assertTrue(name.endswith(".txt"), name)

    def test_legacy_logs_are_listed_and_cleaned_separately(self) -> None:
        from log import commands
        from log.log import cleanup_old_logs

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            stamp = time.time() - 1000
            for index in range(3):
                for prefix in ("zapret_log_", "net67_log_"):
                    path = folder / f"{prefix}2026-09-0{index + 1}_10-00-00.txt"
                    path.write_text("x", encoding="utf-8")
                    os.utime(path, (stamp + index, stamp + index))

            # Лимит 2 — на каждое имя свой: свежие новые не вытесняются старыми.
            deleted, _errors, _total = cleanup_old_logs(str(folder), 2)
            self.assertEqual(deleted, 2)
            left = sorted(p.name for p in folder.iterdir())
            self.assertEqual(sum(n.startswith("net67_log_") for n in left), 2)
            self.assertEqual(sum(n.startswith("zapret_log_") for n in left), 2)

            with patch.object(commands, "LOGS_FOLDER", str(folder)):
                state = commands.list_logs(run_cleanup=False)
            names = {Path(entry["path"]).name for entry in state.entries}
            self.assertEqual(names, set(left))


if __name__ == "__main__":
    unittest.main()
