"""«Пропустить» в туре первого запуска не меняет настроек человека.

Раньше пропуск записывал то, что стояло на карточках, как «Готово»:
автозапуск с Windows, сворачивание в трей, прокси Telegram, нейросети в
hosts. Человек ни на что не отвечал, а программа ответила за него «да» на
всё. Теперь пишутся только отметки, без которых пропуск не держится.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class SkipKeepsSettingsTests(unittest.TestCase):
    def _store(self):
        from settings import store as settings_store

        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch("settings.store.MAIN_DIRECTORY", str(temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        settings_store.prepare_settings_database()
        self.addCleanup(settings_store.close_settings_database)
        return settings_store

    def test_skip_changes_only_the_three_marks(self) -> None:
        from ui.onboarding.setup_choices import SetupAnswers, mark_setup_skipped

        store = self._store()
        before = store.read_settings()
        answers = SetupAnswers()

        # Мастер и запись hosts при пропуске не зовутся вовсе.
        with (
            patch("wizard.apply.apply_wizard", side_effect=AssertionError("пропуск не пишет ответы")),
            patch("hosts.first_run_defaults.apply_now", side_effect=AssertionError("пропуск не трогает hosts")),
        ):
            self.assertTrue(mark_setup_skipped(answers))

        after = store.read_settings()
        self.assertTrue(store.get_wizard_completed())
        self.assertTrue(store.get_onboarding_tour_done())
        self.assertTrue(answers.applied)

        def without_marks(data: dict) -> dict:
            clean = {key: (dict(value) if isinstance(value, dict) else value) for key, value in data.items()}
            for section, key in (
                ("ui_state", "hosts_defaults_version"),
                ("ui_state", "wizard_completed"),
                ("warnings", "onboarding_tour_done"),
            ):
                if isinstance(clean.get(section), dict):
                    clean[section].pop(key, None)
            return clean

        self.assertEqual(without_marks(after), without_marks(before))

    def test_next_start_does_not_write_hosts_defaults_after_skip(self) -> None:
        """Без отметки версии запуск после пропуска сам включил бы группы hosts."""
        from hosts import first_run_defaults
        from ui.onboarding.setup_choices import mark_setup_skipped

        self._store()
        self.assertTrue(mark_setup_skipped())
        self.assertFalse(first_run_defaults.is_needed())

    def test_done_still_writes_answers(self) -> None:
        """«Готово» по-прежнему записывает ответы — меняется только пропуск."""
        from ui.onboarding import setup_choices

        answers = setup_choices.SetupAnswers()
        with (
            patch.object(setup_choices, "apply_provider_answer"),
            patch("wizard.apply.apply_wizard") as apply_wizard,
            patch("settings.store.set_onboarding_tour_done"),
            patch("main.post_startup_wizard.resync_open_pages"),
        ):
            apply_wizard.return_value.saved = True
            apply_wizard.return_value.warnings = ()
            self.assertTrue(setup_choices.apply_setup_answers(None, answers))
        apply_wizard.assert_called_once()


class OverlaySkipRoutingTests(unittest.TestCase):
    def test_overlay_skip_calls_mark_not_apply(self) -> None:
        source = (SRC / "ui" / "onboarding" / "overlay.py").read_text(encoding="utf-8")
        finish = source.split("def finish(", 1)[1].split("\n    def ", 1)[0]
        self.assertIn('reason == "done"', finish)
        self.assertIn("mark_setup_skipped(self._answers)", finish)
        self.assertNotIn('reason in ("done", "skipped")', finish)


if __name__ == "__main__":
    unittest.main()
