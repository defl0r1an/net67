"""Запасной прямой DNS подбора стратегии.

На машине владельца DNS-клиент Windows отвечал 12 с на каждое новое имя:
первыми в списке стояли серверы Radmin VPN, запрос шёл в мёртвый туннель.
Подбор ждал 4 с и объявлял «Нет интернета», хотя роутер отвечал за 7 мс.
"""

from __future__ import annotations

import socket
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from utils import dns_direct  # noqa: E402


def _answer(txid: int, name: str, ips: list[str], *, rcode: int = 0, cname: str = "") -> bytes:
    """Ответ сервера с A-записями (и CNAME впереди), имена через сжатие."""
    question = dns_direct.build_a_query(name, txid)[12:]
    records = b""
    count = 0
    if cname:
        target = b"".join(bytes([len(p)]) + p.encode() for p in cname.split(".")) + b"\0"
        records += b"\xc0\x0c" + struct.pack(">HHIH", 5, 1, 60, len(target)) + target
        count += 1
    for ip in ips:
        records += b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4) + socket.inet_aton(ip)
        count += 1
    header = struct.pack(">HHHHHH", txid, 0x8180 | rcode, 1, count, 0, 0)
    return header + question + records


class ParseTests(unittest.TestCase):
    def test_reads_a_records_after_cname(self) -> None:
        data = _answer(0x1234, "www.microsoft.com", ["23.32.25.194", "23.32.25.195"], cname="e13678.dscb.akamaiedge.net")
        self.assertEqual(dns_direct.parse_a_answers(data, 0x1234), ("23.32.25.194", "23.32.25.195"))

    def test_foreign_or_failed_answer_is_empty(self) -> None:
        data = _answer(0x1234, "ya.ru", ["77.88.44.242"])
        self.assertEqual(dns_direct.parse_a_answers(data, 0x4321), ())
        self.assertEqual(dns_direct.parse_a_answers(_answer(7, "ya.ru", [], rcode=3), 7), ())
        self.assertEqual(dns_direct.parse_a_answers(data[:20], 0x1234), ())


class QueryTests(unittest.TestCase):
    def test_first_server_with_addresses_wins(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        self.addCleanup(server.close)

        import threading

        def serve() -> None:
            data, peer = server.recvfrom(512)
            txid = struct.unpack(">H", data[:2])[0]
            server.sendto(_answer(txid, "ya.ru", ["77.88.44.242"]), peer)

        threading.Thread(target=serve, daemon=True).start()
        answer = dns_direct.query_a("ya.ru", ["127.0.0.1"], timeout=2.0, port=port)

        self.assertEqual(answer.ips, ("77.88.44.242",))
        self.assertEqual(answer.server, "127.0.0.1")

    def test_no_servers_means_no_answer(self) -> None:
        self.assertEqual(dns_direct.query_a("ya.ru", [], timeout=0.1).ips, ())


class ScanFallbackTests(unittest.TestCase):
    def test_system_dns_timeout_falls_back_to_direct_query(self) -> None:
        from blockcheck.strategy_search import probes
        from utils.net_resolve import DNSTimeoutError

        with (
            patch("utils.net_resolve.resolve_addrinfo", side_effect=DNSTimeoutError("DNS не ответил за 4с: ya.ru")),
            patch("utils.windows_dns_query.system_dns_servers", return_value=("1.1.1.1", "192.168.0.1")),
            patch.object(dns_direct, "query_a", return_value=dns_direct.DirectAnswer(("77.88.44.242",), "192.168.0.1", 7.0)),
        ):
            addresses, error = probes.resolve_target_addresses("ya.ru", 443)

        self.assertEqual(addresses, ["77.88.44.242"])
        self.assertEqual(error, "")

    def test_missing_domain_does_not_use_fallback(self) -> None:
        """«Домена нет» — ответ DNS, а не молчание: второй раз не спрашиваем."""
        from blockcheck.strategy_search import probes

        with (
            patch("utils.net_resolve.resolve_addrinfo", side_effect=socket.gaierror(11001, "getaddrinfo failed")),
            patch.object(dns_direct, "query_a") as direct,
        ):
            addresses, error = probes.resolve_target_addresses("nonexistent.invalid", 443)

        direct.assert_not_called()
        self.assertEqual(addresses, [])
        self.assertIn("не найден", error)


if __name__ == "__main__":
    unittest.main()
