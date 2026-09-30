# tests/test_hosts_catalog_refresh.py
"""Разбор DNS-ответа в инструменте пересчёта каталога hosts.

Разбор бинарного пакета — то место, где ошибка не заметна. Скрипт не
упадёт: он просто запишет в каталог не тот адрес, и обход перестанет
работать у одного сервиса из шестидесяти. Поэтому проверяется отдельно и
на собранных вручную пакетах, без обращения к сети.
"""

from __future__ import annotations

import socket
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from refresh_hosts_catalog import (  # noqa: E402
    TYPE_A,
    TYPE_AAAA,
    DnsError,
    build_query,
    encode_name,
    parse_addresses,
    skip_name,
)


def answer_packet(txid: int, name: str, records, *, rcode: int = 0, compress: bool = True) -> bytes:
    """Собирает ответ резолвера так, как его собрал бы настоящий."""
    flags = 0x8180 | (rcode & 0x0F)
    header = struct.pack(">HHHHHH", txid, flags, 1, len(records), 0, 0)
    question = encode_name(name) + struct.pack(">HH", TYPE_A, 1)

    body = b""
    for rtype, address in records:
        if compress:
            # Ссылка на имя в вопросе — так делают все резолверы.
            owner = b"\xc0\x0c"
        else:
            owner = encode_name(name)
        if rtype == TYPE_A:
            rdata = socket.inet_pton(socket.AF_INET, address)
        elif rtype == TYPE_AAAA:
            rdata = socket.inet_pton(socket.AF_INET6, address)
        else:
            rdata = address
        body += owner + struct.pack(">HHIH", rtype, 1, 300, len(rdata)) + rdata

    return header + question + body


class NameTests(unittest.TestCase):
    def test_encodes_labels_with_lengths(self) -> None:
        self.assertEqual(encode_name("api.anthropic.com"), b"\x03api\x09anthropic\x03com\x00")

    def test_trailing_dot_is_ignored(self) -> None:
        self.assertEqual(encode_name("example.com."), encode_name("example.com"))

    def test_unicode_name_becomes_punycode(self) -> None:
        self.assertIn(b"xn--", encode_name("пример.рф"))

    def test_empty_name_is_refused(self) -> None:
        with self.assertRaises(DnsError):
            encode_name("   ")

    def test_too_long_label_is_refused(self) -> None:
        with self.assertRaises(DnsError):
            encode_name("a" * 64 + ".com")


class SkipNameTests(unittest.TestCase):
    def test_plain_name(self) -> None:
        data = encode_name("example.com") + b"XX"
        self.assertEqual(skip_name(data, 0), len(data) - 2)

    def test_compression_pointer_is_two_bytes(self) -> None:
        self.assertEqual(skip_name(b"\xc0\x0c\xff", 0), 2)

    def test_truncated_name_is_refused(self) -> None:
        with self.assertRaises(DnsError):
            skip_name(b"\x03ex", 0)


class ParseTests(unittest.TestCase):
    def test_reads_ipv4(self) -> None:
        packet = answer_packet(0x1234, "example.com", [(TYPE_A, "93.184.216.34")])
        self.assertEqual(parse_addresses(packet, txid=0x1234), ["93.184.216.34"])

    def test_reads_ipv6(self) -> None:
        packet = answer_packet(0x1234, "example.com", [(TYPE_AAAA, "2606:2800:220:1:248:1893:25c8:1946")])
        self.assertEqual(
            parse_addresses(packet, txid=0x1234), ["2606:2800:220:1:248:1893:25c8:1946"]
        )

    def test_reads_several_answers_in_order(self) -> None:
        packet = answer_packet(
            0x1234,
            "example.com",
            [(TYPE_A, "1.2.3.4"), (TYPE_A, "5.6.7.8")],
        )
        self.assertEqual(parse_addresses(packet, txid=0x1234), ["1.2.3.4", "5.6.7.8"])

    def test_uncompressed_names_are_handled_too(self) -> None:
        packet = answer_packet(0x1234, "example.com", [(TYPE_A, "1.2.3.4")], compress=False)
        self.assertEqual(parse_addresses(packet, txid=0x1234), ["1.2.3.4"])

    def test_cname_before_address_is_skipped(self) -> None:
        """Резолверы часто отдают CNAME первой записью — она не адрес."""
        cname = encode_name("cdn.example.net")
        header = struct.pack(">HHHHHH", 0x1234, 0x8180, 1, 2, 0, 0)
        question = encode_name("example.com") + struct.pack(">HH", TYPE_A, 1)
        body = b"\xc0\x0c" + struct.pack(">HHIH", 5, 1, 300, len(cname)) + cname
        body += b"\xc0\x0c" + struct.pack(">HHIH", TYPE_A, 1, 300, 4) + socket.inet_pton(
            socket.AF_INET, "9.9.9.9"
        )
        self.assertEqual(parse_addresses(header + question + body, txid=0x1234), ["9.9.9.9"])

    def test_no_such_name_is_an_answer_not_a_failure(self) -> None:
        # NXDOMAIN означает «такого домена нет», и это законный ответ.
        # Считать его сбоем — значит переспрашивать впустую.
        packet = answer_packet(0x1234, "nope.example", [], rcode=3)
        self.assertEqual(parse_addresses(packet, txid=0x1234), [])

    def test_server_failure_is_reported(self) -> None:
        packet = answer_packet(0x1234, "example.com", [], rcode=2)
        with self.assertRaises(DnsError):
            parse_addresses(packet, txid=0x1234)

    def test_foreign_answer_is_refused(self) -> None:
        """Чужой номер — это подложенный ответ, а не наш.

        Принять его значило бы записать в каталог адрес, который прислал
        кто угодно с любого адреса в сети.
        """
        packet = answer_packet(0x1111, "example.com", [(TYPE_A, "6.6.6.6")])
        with self.assertRaises(DnsError):
            parse_addresses(packet, txid=0x2222)

    def test_truncated_packet_is_refused(self) -> None:
        with self.assertRaises(DnsError):
            parse_addresses(b"\x12\x34")


class QueryTests(unittest.TestCase):
    def test_query_asks_for_recursion(self) -> None:
        _txid, packet = build_query("example.com", TYPE_A, txid=0x2020)
        txid, flags, questions, answers, _a, _b = struct.unpack(">HHHHHH", packet[:12])
        self.assertEqual(txid, 0x2020)
        self.assertEqual(flags & 0x0100, 0x0100, "не запрошена рекурсия")
        self.assertEqual((questions, answers), (1, 0))

    def test_query_round_trips_through_the_parser(self) -> None:
        txid, packet = build_query("api.anthropic.com", TYPE_A)
        reply = answer_packet(txid, "api.anthropic.com", [(TYPE_A, "72.56.93.144")])
        self.assertEqual(parse_addresses(reply, txid=txid), ["72.56.93.144"])
        self.assertGreater(len(packet), 12)

    def test_random_ids_differ(self) -> None:
        ids = {build_query("example.com", TYPE_A)[0] for _ in range(50)}
        self.assertGreater(len(ids), 1, "номер запроса не случаен")


class ResolverConfigTests(unittest.TestCase):
    """Настройка резолверов должна читаться и быть внятной."""

    def test_config_loads_and_covers_every_source(self) -> None:
        import json

        from refresh_hosts_catalog import CATALOG_ROOT, load_resolvers

        config = load_resolvers()
        sources = config["sources"]

        listed = json.loads((CATALOG_ROOT / "dns_sources.json").read_text(encoding="utf-8"))
        expected = {item["id"] for item in listed["dns_sources"]}

        # Источник из каталога без записи здесь просто молча не
        # обновится — и никто не поймёт почему.
        self.assertEqual(set(sources) & expected, expected, "источник каталога не описан")

    def test_dns_ai_is_asked_over_tls_only(self) -> None:
        """У DNS-AI закрыт 53-й порт: UDP не пробуем, чтобы не ждать таймаутов."""
        from unittest.mock import patch

        import refresh_hosts_catalog as tool

        source = tool.load_resolvers()["sources"]["dns_ai"]
        self.assertTrue(tool._has_transport(source))
        with (
            patch.object(tool, "resolve_over_tls", return_value=["20.0.0.1"]) as tls,
            patch.object(tool, "resolve_over_udp") as udp,
        ):
            self.assertEqual(tool.resolve("chatgpt.com", TYPE_A, source), ["20.0.0.1"])
        tls.assert_called_once()
        self.assertEqual(tls.call_args.args[2], "dns.dns-ai.ru")
        udp.assert_not_called()

        with (
            patch.object(tool, "resolve_over_tls", side_effect=DnsError("reset")),
            patch.object(tool, "resolve_over_udp") as udp,
        ):
            with self.assertRaises(DnsError):
                tool.resolve("chatgpt.com", TYPE_A, source)
        udp.assert_not_called()

    def test_known_sources_have_servers(self) -> None:
        from refresh_hosts_catalog import load_resolvers

        sources = load_resolvers()["sources"]
        for key in ("xbox_dns", "xbox_dns_old", "comss_dns", "malw_dns"):
            self.assertTrue(sources[key]["servers"], f"{key} остался без резолвера")


if __name__ == "__main__":
    unittest.main()
