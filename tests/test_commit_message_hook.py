"""Служебные строки Claude не попадают в историю.

23 октября 2026 четыре коммита ушли со строками «Co-Authored-By: Claude» и
«Claude-Session: …», и GitHub записал Claude в участники проекта. Убрать
его удалось только переписыванием main, dev и тега v0.26.67. Правило было
записано и раньше — его не соблюли, поэтому теперь строки вырезает хук
.githooks/commit-msg, а этот тест падает, если они всё-таки пролезли.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "commit-msg"
TRAILER = re.compile(r"^\s*(co-authored-by:.*(anthropic\.com|claude)|claude-session:)", re.IGNORECASE | re.MULTILINE)


class CommitMessageHookTests(unittest.TestCase):
    def _run_hook(self, text: str) -> str:
        sh = shutil.which("sh")
        if sh is None:
            self.skipTest("нет sh")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "COMMIT_EDITMSG"
            path.write_bytes(text.encode("utf-8"))
            subprocess.run([sh, str(HOOK), str(path)], check=True, timeout=30)
            return path.read_bytes().decode("utf-8")

    def test_claude_lines_are_cut_and_nothing_else(self) -> None:
        result = self._run_hook(
            "Тема\n\nТело с причиной.\n\n"
            "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
            "Claude-Session: https://claude.ai/code/session_x\n"
        )
        self.assertEqual(result, "Тема\n\nТело с причиной.\n")

    def test_human_co_author_is_kept(self) -> None:
        text = "Тема\n\nCo-authored-by: Иван <ivan@example.com>\n"
        self.assertEqual(self._run_hook(text), text)

    def test_history_has_no_claude_lines(self) -> None:
        git = shutil.which("git")
        if git is None or not (ROOT / ".git").exists():
            self.skipTest("нет git или репозитория")
        done = subprocess.run(
            [git, "log", "--format=%H%n%B", "HEAD"],
            cwd=ROOT, capture_output=True, timeout=60,
        )
        if done.returncode != 0:
            self.skipTest("история недоступна")
        found = TRAILER.findall(done.stdout.decode("utf-8", "replace"))
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
