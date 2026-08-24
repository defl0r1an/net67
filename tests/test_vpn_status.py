from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

PUB = "u6tIaMhatSm6rX8St/iuWQ504VmaXCXiXCwhBVOv6gA="
PSK = "KAY8rzkLWL06CF8jKVeBySHuWKmjQykQAdFZ20v/ONU="

#: Строка устройства AmneziaWG: помимо ключей и порта содержит параметры
#: обфускации. Именно поэтому разбор идёт не по позиции строки.
AWG_DEVICE_LINE = "\t".join(
    [
        "privkey", "pubkey", "51820",
        "4", "40", "70", "0", "0", "0", "0",
        "(null)", "(null)", "(null)", "(null)",
        "(null)", "(null)", "(null)", "(null)", "(null)",
        "off",
    ]
)

PEER_LINE = "\t".join(
    [PUB, PSK, "203.0.113.10:51820", "0.0.0.0/0", "1785000000", "1048576", "524288", "25"]
)

DUMP = f"{AWG_DEVICE_LINE}\n{PEER_LINE}\n"


class DumpParsingTests(unittest.TestCase):
    def test_peer_line_is_parsed(self) -> None:
        from vpn.status import parse_dump

        stats = parse_dump(DUMP)

        self.assertIsNotNone(stats)
        self.assertEqual(stats.endpoint, "203.0.113.10:51820")
        self.assertEqual(stats.last_handshake, 1785000000)
        self.assertEqual(stats.rx_bytes, 1048576)
        self.assertEqual(stats.tx_bytes, 524288)

    def test_wide_amnezia_device_line_is_not_mistaken_for_peer(self) -> None:
        """Главная ловушка формата AmneziaWG."""
        from vpn.status import parse_dump

        stats = parse_dump(AWG_DEVICE_LINE + "\n")

        self.assertIsNone(stats)

    def test_empty_output_gives_none(self) -> None:
        from vpn.status import parse_dump

        self.assertIsNone(parse_dump(""))
        self.assertIsNone(parse_dump("   \n\n"))

    def test_missing_endpoint_is_normalised(self) -> None:
        from vpn.status import parse_dump

        line = PEER_LINE.replace("203.0.113.10:51820", "(none)")
        stats = parse_dump(f"{AWG_DEVICE_LINE}\n{line}\n")

        self.assertEqual(stats.endpoint, "")

    def test_no_handshake_yet(self) -> None:
        from vpn.status import parse_dump

        line = PEER_LINE.replace("\t1785000000\t", "\t0\t")
        stats = parse_dump(f"{AWG_DEVICE_LINE}\n{line}\n")

        self.assertFalse(stats.has_handshake)

    def test_garbage_numbers_do_not_raise(self) -> None:
        from vpn.status import parse_dump

        line = PEER_LINE.replace("\t1048576\t", "\tмусор\t")
        stats = parse_dump(f"{AWG_DEVICE_LINE}\n{line}\n")

        self.assertEqual(stats.rx_bytes, 0)


class FormattingTests(unittest.TestCase):
    def test_bytes_scale(self) -> None:
        from vpn.status import format_bytes

        self.assertEqual(format_bytes(512), "512 Б")
        self.assertEqual(format_bytes(1024), "1.0 КБ")
        self.assertEqual(format_bytes(1048576), "1.0 МБ")

    def test_handshake_ages(self) -> None:
        from vpn.status import format_handshake

        now = 1785000000
        self.assertIn("сек", format_handshake(now - 30, now=now))
        self.assertIn("мин", format_handshake(now - 300, now=now))
        self.assertIn("ч", format_handshake(now - 7200, now=now))

    def test_no_handshake_is_explicit(self) -> None:
        from vpn.status import format_handshake

        self.assertIn("не было", format_handshake(0))

    def test_future_handshake_does_not_show_negative(self) -> None:
        """Расхождение часов не должно давать «-5 сек назад»."""
        from vpn.status import format_handshake

        self.assertEqual(format_handshake(1785000100, now=1785000000), "только что")

    def test_describe_includes_handshake_and_traffic(self) -> None:
        from vpn.status import describe, parse_dump

        text = describe(parse_dump(DUMP), now=1785000060)

        self.assertIn("Рукопожатие", text)
        self.assertIn("МБ", text)

    def test_describe_handles_missing_stats(self) -> None:
        from vpn.status import describe

        self.assertIn("Нет данных", describe(None))


if __name__ == "__main__":
    unittest.main()
