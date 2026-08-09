from __future__ import annotations

import sys
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

[Peer]
PublicKey = {PUB}
Endpoint = vpn.example.com:51820
AllowedIPs = 0.0.0.0/0
"""


def _profile(**overrides):
    from dataclasses import replace

    from vpn.parser import parse_wireguard_conf

    return replace(parse_wireguard_conf(CONF, name="Основной"), **overrides)


class TunnelNamingTests(unittest.TestCase):
    def test_unsafe_characters_are_stripped(self) -> None:
        from vpn.tunnel import normalize_tunnel_name

        self.assertEqual(normalize_tunnel_name("Мой сервер / VPN!"), "VPN")

    def test_fully_cyrillic_name_falls_back_to_default(self) -> None:
        """Имя службы — только латиница, а профили пользователь называет по-русски."""
        from vpn.tunnel import DEFAULT_TUNNEL_NAME, normalize_tunnel_name

        self.assertEqual(normalize_tunnel_name("Основной сервер"), DEFAULT_TUNNEL_NAME)

    def test_empty_name_falls_back_to_default(self) -> None:
        from vpn.tunnel import DEFAULT_TUNNEL_NAME, normalize_tunnel_name

        self.assertEqual(normalize_tunnel_name(""), DEFAULT_TUNNEL_NAME)
        self.assertEqual(normalize_tunnel_name("!!!"), DEFAULT_TUNNEL_NAME)

    def test_name_is_truncated(self) -> None:
        from vpn.tunnel import normalize_tunnel_name

        self.assertLessEqual(len(normalize_tunnel_name("a" * 100)), 32)

    def test_conf_file_name_matches_tunnel(self) -> None:
        from vpn.tunnel import conf_file_name

        self.assertEqual(conf_file_name("net67"), "net67.conf")

    def test_service_candidates_cover_known_forks(self) -> None:
        """Точное имя службы зависит от версии клиента — проверяем все."""
        from vpn.tunnel import service_name_candidates

        candidates = service_name_candidates("net67")

        self.assertGreaterEqual(len(candidates), 2)
        self.assertTrue(all(c.endswith("$net67") for c in candidates))


class TunnelCommandTests(unittest.TestCase):
    def test_install_command_shape(self) -> None:
        from vpn.tunnel import build_install_command

        self.assertEqual(
            build_install_command("C:/exe/amneziawg.exe", "C:/cfg/net67.conf"),
            ["C:/exe/amneziawg.exe", "/installtunnelservice", "C:/cfg/net67.conf"],
        )

    def test_uninstall_command_uses_normalized_name(self) -> None:
        from vpn.tunnel import build_uninstall_command

        command = build_uninstall_command("awg.exe", "Мой / сервер")

        self.assertEqual(command[1], "/uninstalltunnelservice")
        self.assertNotIn("/", command[2])


class TunnelStateTests(unittest.TestCase):
    def test_service_codes_map_to_states(self) -> None:
        from vpn.tunnel import (
            SERVICE_RUNNING,
            SERVICE_START_PENDING,
            SERVICE_STOPPED,
            TunnelState,
            map_service_state,
        )

        self.assertIs(map_service_state(SERVICE_RUNNING), TunnelState.CONNECTED)
        self.assertIs(map_service_state(SERVICE_STOPPED), TunnelState.DISCONNECTED)
        self.assertIs(map_service_state(SERVICE_START_PENDING), TunnelState.CONNECTING)

    def test_missing_service_is_disconnected_not_error(self) -> None:
        from vpn.tunnel import TunnelState, map_service_state

        self.assertIs(map_service_state(None), TunnelState.DISCONNECTED)

    def test_unknown_code_is_error(self) -> None:
        from vpn.tunnel import TunnelState, map_service_state

        self.assertIs(map_service_state(999), TunnelState.ERROR)

    def test_every_state_has_russian_label(self) -> None:
        from vpn.tunnel import TunnelState, describe_state

        for state in TunnelState:
            self.assertTrue(describe_state(state))


class TunnelValidationTests(unittest.TestCase):
    def test_complete_profile_passes(self) -> None:
        from vpn.tunnel import validate_profile_for_tunnel

        ok, _ = validate_profile_for_tunnel(_profile())

        self.assertTrue(ok)

    def test_missing_address_is_rejected(self) -> None:
        """Без Address адаптер создать нечем — ловим до запуска клиента."""
        from vpn.tunnel import validate_profile_for_tunnel

        ok, message = validate_profile_for_tunnel(_profile(address=""))

        self.assertFalse(ok)
        self.assertIn("Address", message)

    def test_missing_endpoint_is_rejected(self) -> None:
        from vpn.tunnel import validate_profile_for_tunnel

        ok, message = validate_profile_for_tunnel(_profile(endpoint_host=""))

        self.assertFalse(ok)
        self.assertIn("сервера", message)

    def test_none_profile_is_rejected(self) -> None:
        from vpn.tunnel import validate_profile_for_tunnel

        self.assertFalse(validate_profile_for_tunnel(None)[0])


class ClientContractTests(unittest.TestCase):
    """Факты, сверенные с исходниками amneziawg-windows-client 2.0.2.

    Makefile собирает amneziawg.exe и кладёт рядом wintun.dll, а main.go
    объявляет ключи /installtunnelservice CONFIG_PATH и
    /uninstalltunnelservice TUNNEL_NAME. Тест сторожит, чтобы правки не
    разошлись с этим контрактом.
    """

    def test_client_file_names(self) -> None:
        from vpn.tunnel_runtime import CLIENT_EXE_NAME, WINTUN_DLL_NAME

        self.assertEqual(CLIENT_EXE_NAME, "amneziawg.exe")
        self.assertEqual(WINTUN_DLL_NAME, "wintun.dll")

    def test_install_flag_matches_client_cli(self) -> None:
        from vpn.tunnel import build_install_command

        self.assertEqual(build_install_command("a.exe", "c.conf")[1], "/installtunnelservice")

    def test_uninstall_takes_name_not_path(self) -> None:
        """Клиент ждёт имя туннеля, а не путь к файлу."""
        from vpn.tunnel import build_uninstall_command

        command = build_uninstall_command("a.exe", "net67")

        self.assertEqual(command[2], "net67")
        self.assertNotIn(".conf", command[2])

    def test_tunnel_name_comes_from_conf_file_name(self) -> None:
        """conf.NameFromPath берёт имя туннеля из имени файла."""
        from vpn.tunnel import conf_file_name, normalize_tunnel_name

        name = normalize_tunnel_name("net67")

        self.assertEqual(conf_file_name(name), f"{name}.conf")

    def test_amnezia_prefix_is_among_candidates(self) -> None:
        """В исходниках ключ реестра Software\\AmneziaWG."""
        from vpn.tunnel import service_name_candidates

        candidates = service_name_candidates("net67")

        self.assertTrue(any("AmneziaWG" in c for c in candidates))


class TunnelHintTests(unittest.TestCase):
    def test_hint_mentions_dpi_when_winws_runs(self) -> None:
        from vpn.tunnel import build_failure_hint

        self.assertIn("обход DPI", build_failure_hint(winws_running=True))

    def test_hint_without_winws_suggests_checking_server(self) -> None:
        from vpn.tunnel import build_failure_hint

        hint = build_failure_hint(winws_running=False)

        self.assertNotIn("обход DPI", hint)
        self.assertIn("сервера", hint)


if __name__ == "__main__":
    unittest.main()
