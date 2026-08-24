from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class WizardSelectionTests(unittest.TestCase):
    def test_default_selection_is_not_empty(self) -> None:
        from wizard.plans import default_selection

        self.assertTrue(default_selection())

    def test_unknown_keys_are_dropped(self) -> None:
        """Старый конфиг с исчезнувшим сервисом не должен ломать мастер."""
        from wizard.plans import normalize_selection

        self.assertEqual(normalize_selection(["video", "нет-такого"]), frozenset({"video"}))

    def test_legacy_keys_are_migrated(self) -> None:
        """У прошедших старый мастер выбор не должен обнулиться."""
        from wizard.plans import normalize_selection

        self.assertEqual(
            normalize_selection(["youtube", "telegram", "spotify"]),
            frozenset({"video", "messengers", "music"}),
        )

    def test_none_selection_is_safe(self) -> None:
        from wizard.plans import normalize_selection

        self.assertEqual(normalize_selection(None), frozenset())


class WizardProbeUrlTests(unittest.TestCase):
    def test_probe_urls_follow_selection(self) -> None:
        from wizard.plans import build_probe_urls

        urls = build_probe_urls({"video"})

        self.assertEqual(len(urls), 1)
        self.assertIn("youtube", urls[0])

    def test_selection_without_urls_falls_back(self) -> None:
        """Telegram проверяется прокси, а не HTTP — но проверить что-то надо."""
        from wizard.plans import build_probe_urls

        urls = build_probe_urls({"games"})

        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith("https://"))

    def test_empty_selection_still_probes_something(self) -> None:
        from wizard.plans import build_probe_urls

        self.assertTrue(build_probe_urls(set()))


class WizardHostsTests(unittest.TestCase):
    def test_hosts_untouched_without_adobe(self) -> None:
        from wizard.plans import build_hosts_entries

        # Категория «Игры» не трогает hosts: игры открывает обход DPI.
        self.assertEqual(build_hosts_entries({"games"}), {})

    def test_adobe_selection_produces_hosts_entries(self) -> None:
        from wizard.plans import build_hosts_entries

        profiles = build_hosts_entries({"adobe"})

        self.assertTrue(profiles)
        self.assertTrue(any("adobe" in domain for domain in profiles))


class WizardRequestTests(unittest.TestCase):
    def test_telegram_reaches_oneclick_request(self) -> None:
        from wizard.plans import build_oneclick_request

        request = build_oneclick_request({"messengers"})

        self.assertIn("messengers", request.services)
        self.assertTrue(request.needs_telegram_proxy)

    def test_request_without_adobe_has_no_hosts_step(self) -> None:
        from oneclick.plans import build_enable_plan
        from oneclick.state import StepKey
        from wizard.plans import build_oneclick_request

        # «Игры» не трогают hosts, в отличие от «Видео» с Twitch.
        plan = build_enable_plan(build_oneclick_request({"games"}))

        self.assertNotIn(StepKey.HOSTS, [s.key for s in plan])

    def test_adobe_selection_adds_hosts_step(self) -> None:
        from oneclick.plans import build_enable_plan
        from oneclick.state import StepKey
        from wizard.plans import build_oneclick_request

        plan = build_enable_plan(build_oneclick_request({"adobe"}))

        self.assertIn(StepKey.HOSTS, [s.key for s in plan])

    def test_telegram_selection_adds_proxy_step(self) -> None:
        from oneclick.plans import build_enable_plan
        from oneclick.state import StepKey
        from wizard.plans import build_oneclick_request

        plan = build_enable_plan(build_oneclick_request({"messengers"}))

        self.assertIn(StepKey.TELEGRAM_PROXY, [s.key for s in plan])


class WizardSettingsPlanTests(unittest.TestCase):
    def test_autostart_enables_both_app_and_protection(self) -> None:
        """Запускать программу, которая ничего не делает, бессмысленно."""
        from wizard.plans import build_settings_plan

        plan = build_settings_plan(autostart_with_windows=True, minimize_to_tray=False)

        self.assertTrue(plan.gui_autostart_enabled)
        self.assertTrue(plan.dpi_autostart)

    def test_tray_mode_switches_with_toggle(self) -> None:
        from wizard.plans import TRAY_MODE_MINIMIZE, TRAY_MODE_NORMAL, build_settings_plan

        to_tray = build_settings_plan(autostart_with_windows=False, minimize_to_tray=True)
        normal = build_settings_plan(autostart_with_windows=False, minimize_to_tray=False)

        self.assertEqual(to_tray.tray_close_mode, TRAY_MODE_MINIMIZE)
        self.assertEqual(normal.tray_close_mode, TRAY_MODE_NORMAL)

    def test_tray_modes_are_accepted_by_settings_schema(self) -> None:
        """Режим должен пройти валидацию настроек, иначе молча откатится."""
        from settings.schema import VALID_TRAY_CLOSE_MODES
        from wizard.plans import TRAY_MODE_MINIMIZE, TRAY_MODE_NORMAL

        self.assertIn(TRAY_MODE_MINIMIZE, VALID_TRAY_CLOSE_MODES)
        self.assertIn(TRAY_MODE_NORMAL, VALID_TRAY_CLOSE_MODES)


class WizardNavigationTests(unittest.TestCase):
    def test_navigation_is_clamped_at_both_ends(self) -> None:
        from wizard.plans import WIZARD_STEPS, is_last_step, next_step_index, prev_step_index

        last = len(WIZARD_STEPS) - 1

        self.assertEqual(prev_step_index(0), 0)
        self.assertEqual(next_step_index(last), last)
        self.assertTrue(is_last_step(last))
        self.assertFalse(is_last_step(0))


class WizardSettingsPersistenceTests(unittest.TestCase):
    def test_wizard_flags_survive_normalization(self) -> None:
        from settings.normalize import normalize_settings

        normalized = normalize_settings(
            {"ui_state": {"wizard_completed": True, "wizard_services": ["video", "video", "adobe"]}}
        )

        self.assertTrue(normalized["ui_state"]["wizard_completed"])
        self.assertEqual(normalized["ui_state"]["wizard_services"], ["adobe", "video"])

    def test_fresh_install_needs_wizard(self) -> None:
        from settings.normalize import normalize_settings

        self.assertFalse(normalize_settings({})["ui_state"]["wizard_completed"])

    def test_garbage_services_are_filtered(self) -> None:
        from settings.normalize import normalize_settings

        normalized = normalize_settings({"ui_state": {"wizard_services": ["ok", 5, None, "  "]}})

        self.assertEqual(normalized["ui_state"]["wizard_services"], ["ok"])


if __name__ == "__main__":
    unittest.main()


class CategoryChoicesTests(unittest.TestCase):
    """Первый экран — категории, а не отдельные приложения.

    Список приложений у людей разный, а способов обхода всего три.
    Человек отмечает «Нейросети», а приложение само решает, что для них
    нужен hosts, а не обход DPI.
    """

    def test_every_choice_has_examples(self) -> None:
        from wizard.plans import SERVICE_CHOICES

        for choice in SERVICE_CHOICES:
            with self.subTest(choice.key):
                self.assertTrue(choice.title.strip())
                self.assertTrue(
                    choice.description.strip(),
                    "под заголовком категории должны быть примеры",
                )

    def test_titles_are_categories_not_single_apps(self) -> None:
        """Заголовок не должен быть названием одного приложения."""
        from wizard.plans import SERVICE_CHOICES

        single_apps = {"youtube", "discord", "telegram", "spotify", "notion"}
        offenders = [
            choice.title
            for choice in SERVICE_CHOICES
            if choice.title.strip().lower() in single_apps
        ]
        self.assertEqual(offenders, [], "в заголовке отдельное приложение вместо категории")

    def test_examples_are_listed_in_description(self) -> None:
        from wizard.plans import SERVICE_CHOICES

        by_key = {c.key: c for c in SERVICE_CHOICES}
        self.assertIn("Telegram", by_key["messengers"].description)
        self.assertIn("ChatGPT", by_key["ai"].description)

    def test_keys_are_unique(self) -> None:
        from wizard.plans import SERVICE_CHOICES

        keys = [choice.key for choice in SERVICE_CHOICES]
        self.assertEqual(len(keys), len(set(keys)))

    def test_hosts_services_exist_in_catalog(self) -> None:
        from hosts.proxy_domains import get_all_services
        from wizard.plans import SERVICE_CHOICES

        catalog = set(get_all_services())
        if not catalog:
            self.skipTest("каталог hosts недоступен")

        missing = [
            name
            for choice in SERVICE_CHOICES
            for name in choice.hosts_services
            if name not in catalog
        ]
        self.assertEqual(missing, [], "категория ссылается на сервис, которого нет в каталоге")

    def test_ai_category_produces_hosts_entries(self) -> None:
        from wizard.plans import build_hosts_entries

        entries = build_hosts_entries(["ai"])
        if not entries:
            self.skipTest("каталог hosts недоступен")

        self.assertTrue(any("chatgpt" in host for host in entries))
        for host, ip in entries.items():
            self.assertTrue(host.strip())
            self.assertTrue(ip.strip())

    def test_video_category_does_not_touch_hosts_for_youtube(self) -> None:
        """YouTube открывается обходом DPI, а не подменой адреса."""
        from wizard.plans import build_hosts_entries

        entries = build_hosts_entries(["video"])

        self.assertFalse(
            any("youtube" in host or "googlevideo" in host for host in entries),
            "домены YouTube не должны попадать в hosts",
        )

    def test_nothing_selected_leaves_hosts_alone(self) -> None:
        from wizard.plans import build_hosts_entries

        self.assertEqual(build_hosts_entries([]), {})

    def test_adobe_uses_builtin_domains(self) -> None:
        from wizard.plans import build_hosts_entries

        entries = build_hosts_entries(["adobe"])
        self.assertTrue(any("adobe" in host for host in entries))

    def test_messengers_enable_telegram_proxy(self) -> None:
        from oneclick.plans import StepKey, build_enable_plan
        from wizard.plans import build_oneclick_request

        keys = [s.key for s in build_enable_plan(build_oneclick_request(["messengers"]))]
        self.assertIn(StepKey.TELEGRAM_PROXY, keys)

    def test_ai_adds_hosts_step(self) -> None:
        from oneclick.plans import StepKey, build_enable_plan
        from wizard.plans import build_oneclick_request

        request = build_oneclick_request(["ai"])
        if not request.hosts_entries:
            self.skipTest("каталог hosts недоступен")

        keys = [s.key for s in build_enable_plan(request)]
        self.assertIn(StepKey.HOSTS, keys)

    def test_games_only_needs_dpi(self) -> None:
        from oneclick.plans import StepKey, build_enable_plan
        from wizard.plans import build_oneclick_request

        keys = [s.key for s in build_enable_plan(build_oneclick_request(["games"]))]
        self.assertNotIn(StepKey.HOSTS, keys)
        self.assertNotIn(StepKey.TELEGRAM_PROXY, keys)
