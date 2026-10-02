"""Описания выпусков лежат в репозитории и попадают в выпуск на GitHub.

Окно «Доступно обновление» показывает описание выпуска. GitHub сам пишет
туда одну строку «Full Changelog» со ссылкой на сравнение коммитов —
человеку читать нечего. Поэтому текст пишется руками в
``release-notes/<версия>.md``, а сборка по тегу кладёт его в выпуск.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_SRC = ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

NOTES_DIR = ROOT / "release-notes"
WORKFLOW = ROOT / ".github" / "workflows" / "windows-release.yml"


class ReleaseNotesFilesTests(unittest.TestCase):
    def test_every_file_is_named_by_its_version(self) -> None:
        files = sorted(NOTES_DIR.glob("*.md"))

        self.assertTrue(files, "нет ни одного описания выпуска")
        for path in files:
            with self.subTest(file=path.name):
                self.assertRegex(path.stem, r"^\d+(\.\d+){1,3}$")

    def test_every_file_renders_into_a_list_of_changes(self) -> None:
        from updater.release_notes import clean_release_notes, notes_html

        for path in sorted(NOTES_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                html = notes_html(clean_release_notes(text), accent_hex="#00aaff")
                self.assertGreaterEqual(html.count("<li"), 2)
                # Заметки для владельца («вставь это в описание…») людям не показываем.
                self.assertNotIn("Вставь", text)
                self.assertNotIn("Full Changelog", text)
                self.assertNotIn("**", re.sub(r"<[^>]+>", "", html), "жирное осталось звёздочками")

    def test_current_version_has_its_notes(self) -> None:
        """Версия, которую сборка считает текущей, не должна выйти без описания."""
        match = re.search(r'FALLBACK_VERSION = "([^"]+)"', WORKFLOW.read_text(encoding="utf-8"))

        self.assertIsNotNone(match)
        self.assertTrue((NOTES_DIR / f"{match.group(1)}.md").is_file())

    def test_workflow_puts_the_file_into_the_release(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("release-notes", text)
        self.assertIn("body_path: ${{ steps.notes.outputs.path }}", text)
        # Автоматическое описание остаётся только запасным — когда файла нет.
        self.assertIn("generate_release_notes: ${{ steps.notes.outputs.path == '' }}", text)


if __name__ == "__main__":
    unittest.main()
