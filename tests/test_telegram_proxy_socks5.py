from __future__ import annotations

import asyncio
import socket
import struct
import unittest
from unittest.mock import patch


class TelegramProxySocks5Tests(unittest.TestCase):
    def test_proactor_connection_lost_reset_is_quiet_loop_failure(self) -> None:
        import telegram_proxy

        exc = ConnectionResetError("remote host closed connection")
        exc.winerror = 10054

        self.assertTrue(
            telegram_proxy._is_ignorable_asyncio_loop_exception(
                {
                    "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost()",
                    "exception": exc,
                    "handle": object(),
                }
            )
        )

    def test_handshake_timeout_is_quiet_protocol_failure(self) -> None:
        from telegram_proxy.proxy import socks5

        async def run_check() -> None:
            with (
                patch.object(socks5, "_do_handshake", side_effect=asyncio.TimeoutError),
                patch.object(socks5.log, "debug") as debug_log,
                patch.object(socks5.log, "exception") as exception_log,
            ):
                result = await socks5.handshake(object(), object())

            self.assertIsNone(result)
            debug_log.assert_called_once()
            exception_log.assert_not_called()

        asyncio.run(run_check())

    def test_udp_associate_handshake_returns_udp_request_and_bound_port(self) -> None:
        from telegram_proxy.proxy import socks5

        class _Reader:
            def __init__(self) -> None:
                self._chunks = [
                    b"\x05\x01",
                    b"\x00",
                    b"\x05\x03\x00\x01",
                    b"\x00\x00\x00\x00",
                    struct.pack("!H", 9),
                ]

            async def readexactly(self, _size: int) -> bytes:
                return self._chunks.pop(0)

        class _Writer:
            def __init__(self) -> None:
                self.writes: list[bytes] = []

            def write(self, data: bytes) -> None:
                self.writes.append(bytes(data))

            async def drain(self) -> None:
                return None

        async def run_check() -> None:
            result = await socks5.handshake(
                _Reader(),
                _Writer(),
                allow_udp_associate=True,
                on_udp_associate=lambda: ("127.0.0.1", 45678),
            )

            self.assertIsInstance(result, socks5.UdpAssociateRequest)
            self.assertEqual(result.client_host, "0.0.0.0")
            self.assertEqual(result.client_port, 9)

        asyncio.run(run_check())

    def test_udp_packet_roundtrip_keeps_destination_header(self) -> None:
        from telegram_proxy.proxy import socks5

        packet = socks5.build_udp_packet("149.154.167.220", 443, b"call-bytes")
        parsed = socks5.parse_udp_packet(packet)

        self.assertEqual(parsed.target_host, "149.154.167.220")
        self.assertEqual(parsed.target_port, 443)
        self.assertEqual(parsed.payload, b"call-bytes")

    def test_upstream_udp_associate_sends_socks5_udp_request(self) -> None:
        from telegram_proxy.proxy import socks5

        class _Reader:
            def __init__(self) -> None:
                self._chunks = [
                    b"\x05\x00",
                    b"\x05\x00\x00\x01",
                    socket.inet_aton("127.0.0.1"),
                    struct.pack("!H", 39000),
                ]

            async def readexactly(self, _size: int) -> bytes:
                return self._chunks.pop(0)

        class _Writer:
            def __init__(self) -> None:
                self.writes: list[bytes] = []

            def write(self, data: bytes) -> None:
                self.writes.append(bytes(data))

            async def drain(self) -> None:
                return None

            def close(self) -> None:
                return None

        opened: list[_Writer] = []

        async def fake_open_connection(*_args, **_kwargs):
            writer = _Writer()
            opened.append(writer)
            return _Reader(), writer

        async def run_check() -> None:
            with patch("telegram_proxy.proxy.socks5.asyncio.open_connection", side_effect=fake_open_connection):
                session = await socks5.open_udp_associate_via_socks5("127.0.0.1", 1080)

            self.assertEqual(session.relay_host, "127.0.0.1")
            self.assertEqual(session.relay_port, 39000)
            self.assertEqual(opened[0].writes[1], b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")

        asyncio.run(run_check())


if __name__ == "__main__":
    unittest.main()
