"""После установки включены «Напрямую из hosts» и «ИИ», и ровно один раз.

Сначала включались все 72 сервиса каталога, включая подмену DNS. Это
пришлось откатить: приложение рапортовало «обход работает», а сайты не
открывались. Потом откат оказался слишком широким — нейросети без
подмены адреса не работают вообще. Подробности — в hosts/defaults.py.

Однократность здесь не мелочь: если применять умолчания на каждом
запуске, тумблер, выключенный человеком осознанно, возвращался бы
обратно, и выключить его навсегда было бы нельзя.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class DefaultSelectionRuleTests(unittest.TestCase):
    """Правило проверяется без чтения каталога с диска."""

    def test_dns_substitution_service_is_not_enabled(self) -> None:
        """Обычный сервис с одной лишь подменой DNS в умолчания не попадает."""
        from hosts.defaults import build_default_selection

        selection = build_default_selection(
            ["Notion"],
            {"Notion": ["comss_dns", "xbox_dns", "zapret_dns"]},
        )

        self.assertEqual(selection, {})

    def test_preferred_profile_is_still_xbox_dns(self) -> None:
        """Выбор профиля — отдельное правило, оно нужно мастеру и странице."""
        from hosts.defaults import choose_profile

        self.assertEqual(choose_profile(["comss_dns", "xbox_dns", "zapret_dns"]), "xbox_dns")
        self.assertEqual(choose_profile(["comss_dns", "zapret_dns"]), "comss_dns")

    def test_falls_back_to_first_profile(self) -> None:
        """Сервисы «Напрямую из hosts» поддерживают только профиль hosts."""
        from hosts.defaults import build_default_selection

        selection = build_default_selection(["Discord"], {"Discord": ["hosts"]})

        self.assertEqual(selection, {"Discord": "hosts"})

    def test_service_without_profiles_is_skipped(self) -> None:
        from hosts.defaults import build_default_selection

        self.assertEqual(build_default_selection(["Пусто"], {"Пусто": []}), {})

    def test_ai_service_is_enabled_on_xbox_dns(self) -> None:
        """Нейросети — исключение, и включаются они именно на XBOX DNS."""
        from hosts.defaults import build_default_selection

        names = ["Claude", "Grok", "Notion"]
        profiles = {name: ["comss_dns", "xbox_dns", "zapret_dns"] for name in names}

        selection = build_default_selection(names, profiles)

        self.assertEqual(selection, {"Claude": "xbox_dns", "Grok": "xbox_dns"})

    def test_ai_service_without_xbox_dns_is_left_alone(self) -> None:
        """Подставить другой резолвер молча — включить не то, что обещано."""
        from hosts.defaults import build_default_selection

        selection = build_default_selection(["Claude"], {"Claude": ["comss_dns", "zapret_dns"]})

        self.assertEqual(selection, {})

    def test_ai_group_matches_the_page(self) -> None:
        """Список «что такое нейросеть» обязан быть один на всё приложение.

        Иначе группа «ИИ» на странице и умолчания разойдутся, и человек
        увидит в группе сервис, которого умолчания не касались.
        """
        from hosts import defaults
        from hosts.page_plans import is_ai_service

        for name in ("Claude", "Grok", "ChatGPT & Sora (OpenAI)", "Notion", "Discord"):
            with self.subTest(service=name):
                self.assertEqual(defaults.is_ai_service(name), is_ai_service(name))

    def test_youtube_stays_off(self) -> None:
        """YouTube сам предупреждает, что может сломаться от этого тумблера."""
        from hosts.defaults import build_default_selection

        name = "YouTube (иногда может не работать с ним! Отключите тумблер...)"
        selection = build_default_selection(
            [name, "Discord"],
            {name: ["hosts"], "Discord": ["hosts"]},
        )

        self.assertNotIn(name, selection)
        self.assertIn("Discord", selection)


class RealCatalogTests(unittest.TestCase):
    def test_dns_substitution_stays_off_outside_the_ai_group(self) -> None:
        """Подмена DNS вне группы «ИИ» ломает больше, чем чинит.

        Она прибивает домен к адресу, записанному в каталог при его
        сборке. У JetBrains таких адресов больше шестидесяти, у Naukri —
        за полсотни: это Akamai и AWS, они меняются неделями. Записанный
        в hosts адрес не обновится никогда, а устаревший убивает домен
        целиком — хуже блокировки, её DPI-обход вылечил бы сам.
        """
        from hosts.defaults import is_ai_service, load_default_selection

        selection = load_default_selection()
        self.assertTrue(selection, "по умолчанию не включено ничего")
        profiles = {
            profile for name, profile in selection.items() if not is_ai_service(name)
        }

        self.assertEqual(profiles, {"hosts"}, "подмена DNS попала за пределы группы «ИИ»")

    def test_every_ai_service_is_on_by_default(self) -> None:
        """Просьба была прямая: все нейронки на XBOX DNS из коробки."""
        from hosts.defaults import is_ai_service, load_default_selection
        from hosts.proxy_domains import get_all_services

        selection = load_default_selection()
        catalog_ai = [name for name in (get_all_services() or ()) if is_ai_service(name)]

        self.assertGreaterEqual(len(catalog_ai), 10)
        for name in catalog_ai:
            with self.subTest(service=name):
                self.assertEqual(selection.get(name), "xbox_dns")

    def test_no_default_points_at_a_service_address(self) -> None:
        """Локальные и приватные адреса в hosts убивают домен наверняка.

        Проверяем только доказуемое. Адрес вида 8.47.69.0 сюда не
        относится, хотя выглядит подозрительно: он стоит основным сразу
        у четырёх несвязанных сервисов, то есть это общая точка входа, а
        последний ноль вне границы /24 — обычный адрес хоста. Отсеять
        его значило бы выдать догадку за факт. Настоящий мусор в
        каталоге есть — 127.0.0.1 у Deezer, 172.16.2.22 у Naukri; его и
        ловим.
        """
        import ipaddress

        from hosts.defaults import load_default_selection
        from hosts.proxy_domains import get_service_domain_ip_rows

        bad = []
        for name, profile in load_default_selection().items():
            for domain, ip in get_service_domain_ip_rows(name, profile):
                try:
                    address = ipaddress.ip_address(ip)
                except ValueError:
                    bad.append(f"{domain} -> {ip} ({name}): не адрес")
                    continue
                if address.is_loopback or address.is_private or address.is_unspecified:
                    bad.append(f"{domain} -> {ip} ({name})")

        self.assertEqual(bad, [], "домен указывает в никуда")

    def test_ai_group_from_the_screenshot_is_enabled(self) -> None:
        """Ровно те десять строк, что были на скриншоте с просьбой."""
        from hosts.defaults import load_default_selection

        selection = load_default_selection()

        for expected in (
            "ChatGPT & Sora (OpenAI)",
            "Gemini AI",
            "Claude",
            "Microsoft (Copilot, Designer, Xbox)",
            "Grok",
            "Manus",
            "Meta AI",
            "Trae.ai",
            "Windsurf",
            "GitHub Copilot",
        ):
            with self.subTest(service=expected):
                self.assertEqual(selection.get(expected), "xbox_dns")

    def test_direct_hosts_group_is_enabled(self) -> None:
        """Именно эта группа была на скриншоте с просьбой включить всё."""
        from hosts.defaults import load_default_selection

        selection = load_default_selection()
        direct = {name for name, profile in selection.items() if profile == "hosts"}

        for expected in ("Discord", "GitHub", "Instagram", "Rutor", "Supercell", "Render"):
            self.assertIn(expected, direct)
        self.assertTrue(any(name.startswith("Telegram") for name in direct))
        self.assertTrue(any(name.startswith("WhatsApp") for name in direct))


class OneShotTests(unittest.TestCase):
    def test_not_needed_once_current_version_is_applied(self) -> None:
        import hosts.first_run_defaults as module
        from settings import store as settings_store

        original = settings_store.get_hosts_defaults_version
        try:
            settings_store.get_hosts_defaults_version = lambda: module.DEFAULTS_VERSION
            self.assertFalse(module.is_needed())
            settings_store.get_hosts_defaults_version = lambda: 0
            self.assertTrue(module.is_needed())
        finally:
            settings_store.get_hosts_defaults_version = original

    def test_old_broken_defaults_are_rewritten_once(self) -> None:
        """У кого стоит версия 1 — блок hosts надо переписать.

        Первая версия включала подмену DNS всем подряд: сайты
        переставали открываться, хотя приложение рапортовало «обход
        работает». Вторая выключила её целиком — а вместе с ней и
        нейросети. Булев флаг оставил бы обе установки как есть.
        """
        import hosts.first_run_defaults as module
        from settings import store as settings_store

        original = settings_store.get_hosts_defaults_version
        try:
            settings_store.get_hosts_defaults_version = lambda: 1
            self.assertTrue(module.is_needed())
        finally:
            settings_store.get_hosts_defaults_version = original

        self.assertGreater(module.DEFAULTS_VERSION, 2)

    def test_unreadable_settings_do_not_touch_hosts(self) -> None:
        """Не прочитали настройки — системный файл не трогаем."""
        import hosts.first_run_defaults as module
        from settings import store as settings_store

        def _boom():
            raise OSError("settings.json недоступен")

        original = settings_store.get_hosts_defaults_version
        try:
            settings_store.get_hosts_defaults_version = _boom
            self.assertFalse(module.is_needed())
        finally:
            settings_store.get_hosts_defaults_version = original

    def test_background_start_is_skipped_when_not_needed(self) -> None:
        import hosts.first_run_defaults as module

        original = module.is_needed
        try:
            module.is_needed = lambda: False
            self.assertIsNone(module.apply_in_background())
        finally:
            module.is_needed = original


class WizardDoesNotWriteHostsTests(unittest.TestCase):
    def test_wizard_hosts_step_is_a_no_op(self) -> None:
        """Два писателя в один системный файл — гонка.

        Мастер закрывается примерно тогда же, когда отрабатывает поток с
        умолчаниями. Раньше оба писали в hosts, и результат зависел от
        того, кто допишет последним.
        """
        import inspect

        from wizard import apply as wizard_apply

        source = inspect.getsource(wizard_apply._apply_hosts_entries)

        self.assertNotIn("apply_service_profiles", source)
        self.assertNotIn("apply_domain_ip_entries", source)
        self.assertEqual(wizard_apply._apply_hosts_entries({"Discord": "hosts"}), "")


if __name__ == "__main__":
    unittest.main()
