"""Добавление моделей не заменяет выбранные человеком профили hosts."""

import unittest
from unittest.mock import patch

from hosts.commands import enable_hosts_services, disable_hosts_services
from hosts.page_snapshot import HostsPageSnapshot, HostsServiceEntry, CATEGORY_AI
from hosts.state import HostsApplyResult


class ModelHostsTests(unittest.TestCase):
    def test_disabling_models_preserves_other_services_and_does_not_write_when_unreadable(self):
        from dataclasses import replace
        from antigravity.ui.page import MODEL_HOSTS_SERVICES

        snapshot = self.snapshot({**{name: "geohide" for name in MODEL_HOSTS_SERVICES}, "Другой сервис": "astracat"})
        with (patch("hosts.commands.load_page_snapshot", return_value=snapshot) as load,
              patch("hosts.commands.apply_hosts_draft", return_value=HostsApplyResult(True)) as apply):
            self.assertTrue(disable_hosts_services(MODEL_HOSTS_SERVICES).success)
            apply.assert_called_once_with({"Другой сервис": "astracat"}, None)
            apply.reset_mock()
            load.return_value = replace(snapshot, readable=False)
            self.assertFalse(disable_hosts_services(MODEL_HOSTS_SERVICES).success)
            apply.assert_not_called()
    def test_model_keys_exist_and_adding_them_uses_real_catalog_profiles(self):
        from antigravity.ui.page import MODEL_HOSTS_SERVICES
        from hosts.page_snapshot import build_page_snapshot

        snapshot = build_page_snapshot(hosts_text="", hosts_path="example", hosts_exists=True,
                                       readable=True, read_only=False, ipv6_available=True)
        with (patch("hosts.commands.load_page_snapshot", return_value=snapshot),
              patch("hosts.commands.apply_hosts_draft", return_value=HostsApplyResult(True)) as apply):
            self.assertTrue(enable_hosts_services(MODEL_HOSTS_SERVICES).success)
        selection = apply.call_args.args[0]
        self.assertEqual(set(selection), set(MODEL_HOSTS_SERVICES))
        for name, profile in selection.items():
            self.assertTrue(snapshot.rows[(name, profile)])

    def snapshot(self, values):
        return HostsPageSnapshot(tuple(HostsServiceEntry(name, CATEGORY_AI, "fa5s.globe", None,
                                 ("astracat", "geohide"), value) for name, value in values.items()),
                                 (("geohide", "GeoHide"), ("astracat", "AstraCat")), None)

    def test_adding_missing_services_preserves_selected_profiles_and_other_services(self):
        snapshot = self.snapshot({"Gemini AI": "astracat", "Claude": None, "ChatGPT & Sora (OpenAI)": None,
                                  "Google Antigravity": "geohide", "Другой сервис": "astracat"})
        with (patch("hosts.commands.load_page_snapshot", return_value=snapshot),
              patch("hosts.commands.apply_hosts_draft", return_value=HostsApplyResult(True)) as apply):
            self.assertTrue(enable_hosts_services(("Gemini AI", "Claude", "ChatGPT & Sora (OpenAI)")).success)
        apply.assert_called_once_with({"Gemini AI": "astracat", "Claude": "geohide", "ChatGPT & Sora (OpenAI)": "geohide",
                                       "Google Antigravity": "geohide", "Другой сервис": "astracat"}, None)

    def test_already_enabled_services_do_not_write_and_missing_service_fails_without_write(self):
        snapshot = self.snapshot({"Gemini AI": "astracat", "Claude": "geohide", "ChatGPT & Sora (OpenAI)": "geohide"})
        with (patch("hosts.commands.load_page_snapshot", return_value=snapshot),
              patch("hosts.commands.apply_hosts_draft") as apply):
            self.assertTrue(enable_hosts_services(("Gemini AI", "Claude", "ChatGPT & Sora (OpenAI)")).success)
            self.assertFalse(enable_hosts_services(("Нет в каталоге",)).success)
            apply.assert_not_called()

    def test_unreadable_hosts_never_replaces_existing_selection_with_models(self):
        from dataclasses import replace

        snapshot = replace(self.snapshot({"Gemini AI": None, "Claude": None, "ChatGPT & Sora (OpenAI)": None}), readable=False)
        with (patch("hosts.commands.load_page_snapshot", return_value=snapshot),
              patch("hosts.commands.apply_hosts_draft") as apply):
            self.assertFalse(enable_hosts_services(("Gemini AI", "Claude", "ChatGPT & Sora (OpenAI)")).success)
            apply.assert_not_called()
