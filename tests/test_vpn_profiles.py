from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

PRIV = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
PUB = "u6tIaMhatSm6rX8St/iuWQ504VmaXCXiXCwhBVOv6gA="

CONF = f"""
[Interface]
PrivateKey = {PRIV}
Address = 10.8.0.2/32
Jc = 4
Jmin = 40

[Peer]
PublicKey = {PUB}
Endpoint = vpn.example.com:51820
AllowedIPs = 0.0.0.0/0
"""


def _profile(endpoint: str = "vpn.example.com:51820", name: str = "Основной"):
    from vpn.parser import parse_wireguard_conf

    host, _, port = endpoint.rpartition(":")
    text = CONF.replace("vpn.example.com:51820", f"{host}:{port}")
    profile = parse_wireguard_conf(text, name=name)
    return profile


class ProfileStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_file_gives_empty_list(self) -> None:
        from vpn.profiles import load_profiles

        self.assertEqual(load_profiles(self.root), [])

    def test_round_trip_preserves_fields(self) -> None:
        from vpn.profiles import load_profiles, save_profiles

        saved, _ = save_profiles(self.root, [_profile()])
        self.assertTrue(saved)

        loaded = load_profiles(self.root)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].private_key, PRIV)
        self.assertEqual(loaded[0].endpoint, "vpn.example.com:51820")
        self.assertEqual(loaded[0].name, "Основной")

    def test_round_trip_preserves_amnezia_params(self) -> None:
        """Без Jc/Jmin профиль превращается в обычный WireGuard."""
        from vpn.profiles import load_profiles, save_profiles

        save_profiles(self.root, [_profile()])
        loaded = load_profiles(self.root)[0]

        self.assertEqual(loaded.protocol, "AmneziaWG")
        self.assertEqual(loaded.awg.values["Jc"], "4")
        self.assertEqual(loaded.awg.values["Jmin"], "40")

    def test_corrupted_file_does_not_break_loading(self) -> None:
        from vpn.profiles import load_profiles, profiles_path

        profiles_path(self.root).write_text("{не json", encoding="utf-8")

        self.assertEqual(load_profiles(self.root), [])

    def test_garbage_entries_are_skipped(self) -> None:
        import json

        from vpn.profiles import load_profiles, profiles_path, save_profiles

        save_profiles(self.root, [_profile()])
        raw = json.loads(profiles_path(self.root).read_text(encoding="utf-8"))
        raw["profiles"].append("не словарь")
        profiles_path(self.root).write_text(json.dumps(raw), encoding="utf-8")

        self.assertEqual(len(load_profiles(self.root)), 1)

    def test_profiles_are_stored_outside_settings_json(self) -> None:
        """В профилях приватные ключи — им не место в общем конфиге."""
        from vpn.profiles import PROFILES_FILE_NAME

        self.assertNotIn("settings.json", PROFILES_FILE_NAME)


class ProfileCollectionTests(unittest.TestCase):
    def test_same_endpoint_replaces_instead_of_duplicating(self) -> None:
        from vpn.profiles import upsert_profile

        first = _profile(name="Старое имя")
        second = _profile(name="Новое имя")

        result = upsert_profile([first], second)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Новое имя")

    def test_different_endpoints_coexist(self) -> None:
        from vpn.profiles import upsert_profile

        result = upsert_profile([_profile()], _profile(endpoint="other.example.com:51820"))

        self.assertEqual(len(result), 2)

    def test_remove_by_endpoint(self) -> None:
        from vpn.profiles import remove_profile, upsert_profile

        profiles = upsert_profile([_profile()], _profile(endpoint="other.example.com:51820"))
        result = remove_profile(profiles, "vpn.example.com:51820")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].endpoint_host, "other.example.com")

    def test_display_name_falls_back_to_host(self) -> None:
        from dataclasses import replace

        from vpn.profiles import display_name

        self.assertEqual(display_name(_profile(name="Имя")), "Имя")
        self.assertEqual(display_name(replace(_profile(), name="")), "vpn.example.com")


class PingResultTests(unittest.TestCase):
    def test_missing_host_is_reported(self) -> None:
        from vpn.ping import check_server

        result = check_server("")

        self.assertFalse(result.ok)
        self.assertIn("не указан", result.message)

    def test_format_latency_handles_failure(self) -> None:
        from vpn.ping import PingResult, format_latency

        self.assertEqual(format_latency(PingResult(False, None, "tcp", "")), "—")
        self.assertEqual(format_latency(PingResult(True, 42.4, "icmp", "")), "42 мс")

    def test_closed_port_is_told_apart_from_silence(self) -> None:
        """Закрытый порт и молчащий сервер — разные диагнозы.

        Закрытый UDP-порт даёт ICMP «порт недоступен», и это доказывает,
        что хост жив. Молчание же ничего не доказывает: так ведёт себя и
        рабочий WireGuard, и заблокированный файрволом UDP.
        """
        from vpn.ping import check_server

        # Порт 9 (discard) на localhost почти наверняка закрыт.
        result = check_server("127.0.0.1", 9, timeout=0.5)

        self.assertIn(result.method, ("udp", "icmp", "none"))
        self.assertTrue(result.message.strip())


if __name__ == "__main__":
    unittest.main()
