"""Вкладки VPN: «Amnezia» и «VPN», а не AmneziaWG и WireGuard.

Раньше вкладок тоже было две, но делили они протоколы: конфиги с
маскировкой и без. Разделение было формально верным — обфускация либо
есть, либо нет, — и бесполезным: поднимает их один и тот же клиент,
порядок действий одинаковый, и человек всё равно вставлял конфиг туда,
где было место. Сведены обратно по прямой просьбе.

Новое деление — по способу подключения. «Amnezia» это всё семейство
WireGuard, «VPN» — подключение по ссылке (vless, vmess, trojan, ss),
которое поднимает другой клиент.

Правила проверяются без Qt: они не про интерфейс.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _Profile:
    """Достаточная замена VpnProfile: вкладку решают два признака.

    Поле с исходной ссылкой зовётся `raw` — так оно называется у
    настоящего LinkProfile. Здесь оно называлось `link`, и подделка
    разошлась с тем, что она изображает: проверка была зелёной, а живые
    двадцать пять серверов из подписки уезжали на вкладку Amnezia,
    потому что поля `link` у них нет вовсе.

    Правило простое: подделка обязана носить те же имена полей, что и
    подделываемое. Иначе она проверяет саму себя.
    """

    def __init__(self, name: str, *, raw: str = "", obfuscated: bool = False):
        self.name = name
        self.raw = raw
        self.awg = type("Awg", (), {"enabled": obfuscated})()


class TabSetTests(unittest.TestCase):
    def test_there_are_exactly_two_tabs(self) -> None:
        from vpn.tabs import TAB_ORDER

        self.assertEqual(len(TAB_ORDER), 2)

    def test_titles_are_the_requested_ones(self) -> None:
        from vpn.tabs import TAB_AMNEZIA, TAB_LINKS, TAB_TITLES

        self.assertEqual(TAB_TITLES[TAB_AMNEZIA], "Amnezia")
        self.assertEqual(TAB_TITLES[TAB_LINKS], "VPN")

    def test_amnezia_comes_first(self) -> None:
        """Ей пользуются, ссылки — про запас."""
        from vpn.tabs import TAB_AMNEZIA, TAB_ORDER

        self.assertEqual(TAB_ORDER[0], TAB_AMNEZIA)

    def test_every_tab_has_a_hint_and_a_placeholder(self) -> None:
        from vpn.tabs import TAB_HINTS, TAB_ORDER, TAB_PLACEHOLDERS

        for key in TAB_ORDER:
            with self.subTest(tab=key):
                self.assertTrue(TAB_HINTS.get(key))
                self.assertTrue(TAB_PLACEHOLDERS.get(key))


class RoutingTests(unittest.TestCase):
    def test_wireguard_and_amnezia_now_share_one_tab(self) -> None:
        """Клиент один, порядок действий один — вкладка одна."""
        from vpn.tabs import TAB_AMNEZIA, tab_for_profile

        plain = _Profile("обычный .conf", obfuscated=False)
        masked = _Profile("с маскировкой", obfuscated=True)

        self.assertEqual(tab_for_profile(plain), TAB_AMNEZIA)
        self.assertEqual(tab_for_profile(masked), TAB_AMNEZIA)

    def test_links_go_to_their_own_tab(self) -> None:
        from vpn.tabs import TAB_LINKS, tab_for_profile

        profile = _Profile("по ссылке", raw="vless://uuid@example.org:443")

        self.assertEqual(tab_for_profile(profile), TAB_LINKS)

    def test_filtering_keeps_order(self) -> None:
        from vpn.tabs import TAB_AMNEZIA, profiles_for_tab

        profiles = [
            _Profile("первый"),
            _Profile("ссылка", raw="vless://a@b:443"),
            _Profile("второй"),
        ]

        names = [item.name for item in profiles_for_tab(profiles, TAB_AMNEZIA)]

        self.assertEqual(names, ["первый", "второй"])

    def test_counts_cover_every_tab(self) -> None:
        from vpn.tabs import TAB_AMNEZIA, TAB_LINKS, tab_counts

        counts = tab_counts([_Profile("a"), _Profile("b"), _Profile("l", raw="ss://x@y:1")])

        self.assertEqual(counts[TAB_AMNEZIA], 2)
        self.assertEqual(counts[TAB_LINKS], 1)


class SavedChoiceTests(unittest.TestCase):
    """Прежний выбор вкладки нельзя сбрасывать молча."""

    def test_old_wireguard_key_lands_on_amnezia(self) -> None:
        from vpn.tabs import TAB_AMNEZIA, TAB_WIREGUARD, normalize_tab

        self.assertEqual(normalize_tab(TAB_WIREGUARD), TAB_AMNEZIA)

    def test_junk_falls_back_instead_of_failing(self) -> None:
        from vpn.tabs import TAB_AMNEZIA, normalize_tab

        for junk in ("", None, 17, "что-то новое"):
            with self.subTest(value=junk):
                self.assertEqual(normalize_tab(junk), TAB_AMNEZIA)

    def test_known_keys_survive(self) -> None:
        from vpn.tabs import TAB_ORDER, normalize_tab

        for key in TAB_ORDER:
            with self.subTest(tab=key):
                self.assertEqual(normalize_tab(key), key)


class EmptyTextTests(unittest.TestCase):
    def test_empty_text_names_the_tab(self) -> None:
        """Общее «Профили не добавлены» врало: они могли быть на соседней."""
        from vpn.tabs import TAB_AMNEZIA, TAB_LINKS, empty_text

        self.assertIn("vpn://", empty_text(TAB_AMNEZIA))
        self.assertIn("vless://", empty_text(TAB_LINKS))

    def test_texts_differ_between_tabs(self) -> None:
        from vpn.tabs import TAB_AMNEZIA, TAB_LINKS, empty_text

        self.assertNotEqual(empty_text(TAB_AMNEZIA), empty_text(TAB_LINKS))


class StorageTests(unittest.TestCase):
    def test_storage_stays_one_file(self) -> None:
        """Вкладки делят показ, а не хранение.

        Разделение хранилища потребовало бы миграции у всех, кто уже
        добавил профили, ради одного лишь внешнего вида.
        """
        import inspect

        from vpn import tabs

        source = inspect.getsource(tabs)

        self.assertNotIn("open(", source)
        self.assertNotIn("json", source)


if __name__ == "__main__":
    unittest.main()
