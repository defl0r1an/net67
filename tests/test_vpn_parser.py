from __future__ import annotations

import base64
import json
import struct
import sys
import unittest
import zlib
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


# Ключи WireGuard — ровно 32 байта в base64, то есть 44 символа.
PRIV = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
PUB = "u6tIaMhatSm6rX8St/iuWQ504VmaXCXiXCwhBVOv6gA="
PSK = "KAY8rzkLWL06CF8jKVeBySHuWKmjQykQAdFZ20v/ONU="

PLAIN_CONF = f"""
[Interface]
PrivateKey = {PRIV}
Address = 10.8.0.2/32
DNS = 1.1.1.1
MTU = 1420

[Peer]
PublicKey = {PUB}
PresharedKey = {PSK}
AllowedIPs = 0.0.0.0/0
Endpoint = vpn.example.com:51820
PersistentKeepalive = 25
"""

AWG_CONF = f"""
[Interface]
PrivateKey = {PRIV}
Address = 10.8.0.2/32
Jc = 4
Jmin = 40
Jmax = 70
S1 = 0
S2 = 0
H1 = 1
H2 = 2
H3 = 3
H4 = 4

[Peer]
PublicKey = {PUB}
Endpoint = 203.0.113.10:51820
AllowedIPs = 0.0.0.0/0
"""


def _make_vpn_key(config_text: str, *, qt_style: bool = True) -> str:
    payload = json.dumps({"description": "Тест", "containers": [{"awg": {"last_config": config_text}}]})
    compressed = zlib.compress(payload.encode("utf-8"))
    blob = struct.pack(">I", len(payload)) + compressed if qt_style else compressed
    return "vpn://" + base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")


class WireguardConfTests(unittest.TestCase):
    def test_plain_config_is_parsed(self) -> None:
        from vpn.parser import parse_wireguard_conf

        profile = parse_wireguard_conf(PLAIN_CONF)

        self.assertEqual(profile.private_key, PRIV)
        self.assertEqual(profile.public_key, PUB)
        self.assertEqual(profile.endpoint_host, "vpn.example.com")
        self.assertEqual(profile.endpoint_port, 51820)
        self.assertEqual(profile.dns, "1.1.1.1")
        self.assertEqual(profile.mtu, 1420)
        self.assertEqual(profile.keepalive, 25)

    def test_plain_config_is_wireguard_not_amnezia(self) -> None:
        from vpn.parser import parse_wireguard_conf

        self.assertEqual(parse_wireguard_conf(PLAIN_CONF).protocol, "WireGuard")

    def test_amnezia_fields_are_recognised(self) -> None:
        from vpn.parser import parse_wireguard_conf

        profile = parse_wireguard_conf(AWG_CONF)

        self.assertEqual(profile.protocol, "AmneziaWG")
        self.assertEqual(profile.awg.values["Jc"], "4")
        self.assertEqual(profile.awg.values["H4"], "4")

    def test_comments_are_ignored(self) -> None:
        from vpn.parser import parse_wireguard_conf

        text = PLAIN_CONF.replace("DNS = 1.1.1.1", "# DNS = 9.9.9.9\nDNS = 1.1.1.1  # комментарий")

        self.assertEqual(parse_wireguard_conf(text).dns, "1.1.1.1")

    def test_ipv6_endpoint_in_brackets(self) -> None:
        from vpn.parser import parse_wireguard_conf

        text = PLAIN_CONF.replace("vpn.example.com:51820", "[2001:db8::1]:51820")
        profile = parse_wireguard_conf(text)

        self.assertEqual(profile.endpoint_host, "2001:db8::1")
        self.assertEqual(profile.endpoint_port, 51820)


class WireguardConfErrorTests(unittest.TestCase):
    def test_empty_config_is_rejected(self) -> None:
        from vpn.parser import VpnConfigError, parse_wireguard_conf

        with self.assertRaises(VpnConfigError):
            parse_wireguard_conf("   ")

    def test_missing_private_key_is_reported(self) -> None:
        from vpn.parser import VpnConfigError, parse_wireguard_conf

        text = PLAIN_CONF.replace(f"PrivateKey = {PRIV}\n", "")
        with self.assertRaises(VpnConfigError) as ctx:
            parse_wireguard_conf(text)

        self.assertIn("PrivateKey", str(ctx.exception))

    def test_missing_endpoint_is_reported(self) -> None:
        from vpn.parser import VpnConfigError, parse_wireguard_conf

        text = PLAIN_CONF.replace("Endpoint = vpn.example.com:51820\n", "")
        with self.assertRaises(VpnConfigError) as ctx:
            parse_wireguard_conf(text)

        self.assertIn("Endpoint", str(ctx.exception))

    def test_malformed_key_is_reported(self) -> None:
        from vpn.parser import VpnConfigError, parse_wireguard_conf

        text = PLAIN_CONF.replace(PRIV, "не-ключ")
        with self.assertRaises(VpnConfigError) as ctx:
            parse_wireguard_conf(text)

        self.assertIn("PrivateKey", str(ctx.exception))

    def test_bad_port_is_reported(self) -> None:
        from vpn.parser import VpnConfigError, parse_wireguard_conf

        text = PLAIN_CONF.replace(":51820", ":ноль")
        with self.assertRaises(VpnConfigError):
            parse_wireguard_conf(text)

    def test_non_numeric_amnezia_field_is_reported(self) -> None:
        from vpn.parser import VpnConfigError, parse_wireguard_conf

        text = AWG_CONF.replace("Jc = 4", "Jc = много")
        with self.assertRaises(VpnConfigError) as ctx:
            parse_wireguard_conf(text)

        self.assertIn("Jc", str(ctx.exception))


class VpnKeyTests(unittest.TestCase):
    def test_qt_style_key_is_parsed(self) -> None:
        from vpn.parser import parse_vpn_key

        profile = parse_vpn_key(_make_vpn_key(AWG_CONF))

        self.assertEqual(profile.endpoint_host, "203.0.113.10")
        self.assertEqual(profile.protocol, "AmneziaWG")
        self.assertEqual(profile.source, "key")

    def test_raw_zlib_key_is_parsed(self) -> None:
        """Формат ключа между версиями Amnezia менялся."""
        from vpn.parser import parse_vpn_key

        profile = parse_vpn_key(_make_vpn_key(PLAIN_CONF, qt_style=False))

        self.assertEqual(profile.endpoint_host, "vpn.example.com")

    def test_key_name_falls_back_to_description(self) -> None:
        from vpn.parser import parse_vpn_key

        self.assertEqual(parse_vpn_key(_make_vpn_key(PLAIN_CONF)).name, "Тест")

    def test_broken_base64_is_reported(self) -> None:
        from vpn.parser import VpnConfigError, parse_vpn_key

        with self.assertRaises(VpnConfigError):
            parse_vpn_key("vpn://!!!не-base64!!!")

    def test_key_without_wireguard_config_is_reported(self) -> None:
        from vpn.parser import VpnConfigError, parse_vpn_key

        payload = json.dumps({"containers": [{"openvpn": {"last_config": "client\ndev tun\n"}}]})
        key = "vpn://" + base64.urlsafe_b64encode(zlib.compress(payload.encode())).decode().rstrip("=")

        with self.assertRaises(VpnConfigError) as ctx:
            parse_vpn_key(key)

        self.assertIn("другого протокола", str(ctx.exception))


class ParseAnyTests(unittest.TestCase):
    def test_detects_conf_text(self) -> None:
        from vpn.parser import parse_any

        self.assertEqual(parse_any(PLAIN_CONF).source, "conf")

    def test_detects_vpn_key(self) -> None:
        from vpn.parser import parse_any

        self.assertEqual(parse_any(_make_vpn_key(PLAIN_CONF)).source, "key")

    def test_empty_input_gives_actionable_message(self) -> None:
        from vpn.parser import VpnConfigError, parse_any

        with self.assertRaises(VpnConfigError) as ctx:
            parse_any("")

        self.assertIn("Введите ключ", str(ctx.exception))

    def test_foreign_scheme_is_rejected_clearly(self) -> None:
        from vpn.parser import VpnConfigError, parse_any

        with self.assertRaises(VpnConfigError) as ctx:
            parse_any("ss://something")

        self.assertIn("vpn://", str(ctx.exception))


class ConfRoundTripTests(unittest.TestCase):
    def test_export_reparses_identically(self) -> None:
        from vpn.parser import parse_wireguard_conf, to_conf_text

        original = parse_wireguard_conf(AWG_CONF)
        again = parse_wireguard_conf(to_conf_text(original))

        self.assertEqual(again.private_key, original.private_key)
        self.assertEqual(again.endpoint, original.endpoint)
        self.assertEqual(again.awg.values, original.awg.values)

    def test_export_keeps_amnezia_fields(self) -> None:
        from vpn.parser import parse_wireguard_conf, to_conf_text

        text = to_conf_text(parse_wireguard_conf(AWG_CONF))

        for name in ("Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"):
            self.assertIn(name, text)




# Форматы, на которых разбор падал у пользователя с рабочим конфигом.
REAL_AWG_CONF = f"""
[Interface]
Address = 10.8.1.17/32
DNS = 172.16.1.10, 172.19.102.10
PrivateKey = {PRIV}
MTU = 1280
Jc = 3
Jmin = 17
Jmax = 40
S1 = 31
S2 = 45
S3 = 21
S4 = 47
H1 = 1429615376-1775318475
H2 = 2465132267-2556724678
H3 = 3269493681-3308362703
H4 = 4198807155-4289964061

[Peer]
PublicKey = {PUB}
PresharedKey = {PSK}
AllowedIPs = 1.0.0.0/8, 2.0.0.0/7, 4.0.0.0/6
Endpoint = 203.0.113.10:51820
"""


class RealWorldAmneziaTests(unittest.TestCase):
    """Конфигурации AmneziaWG 1.5, которые разбор раньше отвергал."""

    def test_header_ranges_are_accepted(self) -> None:
        """H1..H4 бывают диапазонами, а не одним числом."""
        from vpn.parser import parse_wireguard_conf

        profile = parse_wireguard_conf(REAL_AWG_CONF)

        self.assertEqual(profile.protocol, "AmneziaWG")
        self.assertEqual(profile.awg.values["H1"], "1429615376-1775318475")
        self.assertEqual(profile.awg.values["H4"], "4198807155-4289964061")

    def test_s3_and_s4_are_recognised(self) -> None:
        from vpn.parser import parse_wireguard_conf

        profile = parse_wireguard_conf(REAL_AWG_CONF)

        self.assertEqual(profile.awg.values["S3"], "21")
        self.assertEqual(profile.awg.values["S4"], "47")

    def test_ranges_survive_export(self) -> None:
        """Клиент AmneziaWG должен получить исходную запись диапазона."""
        from vpn.parser import parse_wireguard_conf, to_conf_text

        text = to_conf_text(parse_wireguard_conf(REAL_AWG_CONF))

        self.assertIn("H1 = 1429615376-1775318475", text)
        self.assertIn("S4 = 47", text)

    def test_broken_header_is_still_rejected(self) -> None:
        from vpn.parser import VpnConfigError, parse_wireguard_conf

        broken = REAL_AWG_CONF.replace("H1 = 1429615376-1775318475", "H1 = abc")

        with self.assertRaises(VpnConfigError) as caught:
            parse_wireguard_conf(broken)

        self.assertIn("H1", str(caught.exception))

    def test_plain_base64_conf_key_is_parsed(self) -> None:
        """vpn:// бывает просто base64 от текста .conf, без JSON."""
        from vpn.parser import parse_vpn_key

        encoded = base64.urlsafe_b64encode(REAL_AWG_CONF.encode("utf-8"))
        key = "vpn://" + encoded.decode("ascii").rstrip("=")

        profile = parse_vpn_key(key)

        self.assertEqual(profile.endpoint_host, "203.0.113.10")
        self.assertEqual(profile.protocol, "AmneziaWG")
        self.assertEqual(profile.source, "key")
        self.assertEqual(profile.awg.values["H1"], "1429615376-1775318475")

    def test_json_key_still_wins_over_raw_text(self) -> None:
        """JSON тоже содержит [Interface] — но внутри строки."""
        from vpn.parser import parse_vpn_key

        profile = parse_vpn_key(_make_vpn_key(REAL_AWG_CONF))

        self.assertEqual(profile.source, "key")
        self.assertEqual(profile.awg.values["S3"], "21")


if __name__ == "__main__":
    unittest.main()
