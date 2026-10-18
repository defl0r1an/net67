"""Пустой ответ про hosts в настройке не превращается в умолчания на следующем запуске.

18 октября 2026 владелец снял в туре все галочки вопроса «что должно
работать без VPN». Пустой выбор ушёл в ветку «каталог сервисов пуст»,
отметка версии умолчаний не поставилась, и следующий запуск сам прописал
бы в hosts 34 сервиса — ИИ и соцсети, которые человек только что снял.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from hosts import first_run_defaults  # noqa: E402


class EmptySetupChoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.version = 0
        self.writes = []

        def _set_version(value) -> None:
            self.version = int(value)

        def _apply(_runtime, selection):
            self.writes.append(dict(selection))
            raise AssertionError("пустой выбор не должен писать в hosts")

        for target, replacement in (
            ("settings.store.set_hosts_defaults_version", _set_version),
            ("settings.store.get_hosts_defaults_version", lambda: self.version),
            ("settings.store.get_wizard_completed", lambda: True),
            ("hosts.public.apply_service_profiles", _apply),
            ("hosts.public.create_hosts_runtime", lambda: object()),
        ):
            patcher = patch(target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_empty_choice_is_an_answer_not_a_failure(self) -> None:
        ok, message = first_run_defaults.apply_now({})

        self.assertTrue(ok, message)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.version, first_run_defaults.DEFAULTS_VERSION)

    def test_next_start_does_not_write_defaults_after_empty_choice(self) -> None:
        first_run_defaults.apply_now({})

        self.assertFalse(first_run_defaults.is_needed())

    def test_empty_catalog_on_start_is_still_a_failure(self) -> None:
        with patch("hosts.defaults.load_default_selection", lambda: {}):
            ok, message = first_run_defaults.apply_now(None)

        self.assertFalse(ok)
        self.assertIn("каталог сервисов пуст", message)
        self.assertEqual(self.version, 0)


class WizardHostsAnswerTests(unittest.TestCase):
    """Пустой ответ и непрочитанный каталог — разные вещи для мастера."""

    def _apply(self, **kwargs):
        from wizard.apply import WizardWriters, apply_wizard

        written = []
        writers = WizardWriters(
            set_gui_autostart_enabled=lambda _v: "",
            set_dpi_autostart=lambda _v: None,
            set_tray_close_mode=lambda _v: None,
            apply_hosts=lambda profiles: written.append(dict(profiles)) or "",
            set_wizard_services=lambda _v: None,
            set_wizard_completed=lambda _v: None,
            set_telegram_proxy_with_bypass=lambda _v: "",
            add_telegram_hosts=lambda: "",
        )
        result = apply_wizard(
            selection=set(), autostart_with_windows=False, minimize_to_tray=False, writers=writers, **kwargs
        )
        return written, result

    def test_no_groups_is_passed_on_as_an_empty_answer(self) -> None:
        written, result = self._apply(hosts_groups=set())

        self.assertEqual(written, [{}])
        self.assertEqual(tuple(result.warnings), ())

    def test_unread_catalog_is_not_recorded_as_an_empty_answer(self) -> None:
        with patch("wizard.apply.hosts_service_profiles", lambda _groups: {}):
            written, result = self._apply(hosts_groups={"ai"})

        self.assertEqual(written, [])
        self.assertTrue(any("не прочитан" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
