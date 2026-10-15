"""HTTP на настоящем сокете; QUIC требует сравнения с контрольным именем."""

from contextlib import contextmanager
import socket
import threading
from unittest.mock import patch

import pytest

from blockcheck.strategy_search import probes, verdict
from diagnostics import quic_probe
from utils.socket_cancel import SocketCancel


@contextmanager
def http_server(reply):
    stopped = threading.Event()
    requests = []
    errors = []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(2)
        port = listener.getsockname()[1]

        def serve():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(2)
                    requests.append(connection.recv(4096))
                    reply(connection, stopped)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            yield port, requests
        finally:
            stopped.set()
            thread.join(3)
            assert not thread.is_alive()
            assert not errors, errors


def test_http_reads_complete_response_without_waiting_for_close():
    def reply(connection, stopped):
        connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        stopped.wait(1)

    with http_server(reply) as (port, requests), patch.object(probes, "HTTPS_READ_TIMEOUT", 0.1):
        outcome = probes.probe_http("пример.рф", "127.0.0.1", port=port)
    assert outcome.ok
    assert b"Host: xn--e1afmkfd.xn--p1ai\r\n" in requests[0]


def test_http_partial_response_is_not_a_success():
    def reply(connection, stopped):
        connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\nx")
        stopped.wait(1)

    with http_server(reply) as (port, _), patch.object(probes, "HTTPS_READ_TIMEOUT", 0.1):
        outcome = probes.probe_http("example.org", "127.0.0.1", port=port)
    assert outcome.state == verdict.PROBE_BLOCKED
    assert outcome.failure == "timeout"


def test_http_total_deadline_limits_slow_drip():
    def reply(connection, stopped):
        connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\n")
        while not stopped.wait(0.02):
            connection.sendall(b"x")

    with http_server(reply) as (port, _), patch.object(probes, "HTTPS_TIMEOUT", 0.2):
        outcome = probes.probe_http("example.org", "127.0.0.1", port=port)
    assert outcome.state == verdict.PROBE_BLOCKED
    assert outcome.failure == "timeout"


def test_http_eof_before_declared_body_is_not_success():
    def reply(connection, stopped):
        connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\nx")

    with http_server(reply) as (port, _):
        outcome = probes.probe_http("example.org", "127.0.0.1", port=port)
    assert outcome.state == verdict.PROBE_BLOCKED
    assert outcome.failure == "closed"


def test_http_cancel_interrupts_waiting_socket():
    token = SocketCancel()

    def reply(connection, stopped):
        token.cancel()
        stopped.wait(1)

    with http_server(reply) as (port, _):
        outcome = probes.probe_http("example.org", "127.0.0.1", cancel=token, port=port)
    assert outcome.state == verdict.PROBE_CANCELLED


@pytest.mark.parametrize("facts,expected", [
    (quic_probe.QuicFacts("example.org"), False),
    (quic_probe.QuicFacts("example.org", real_ms=12), False),
    (quic_probe.QuicFacts("example.org", neutral_ms=12), True),
    (quic_probe.QuicFacts("example.org", nameless_ms=12), True),
    (quic_probe.QuicFacts("example.org", neutral_ms=12, cancelled=True), False),
])
def test_quic_silence_alone_does_not_start_search(facts, expected):
    with patch.object(quic_probe, "collect", return_value=facts):
        assert probes.quic_blocked_by_name("example.org", "127.0.0.1", cancel=SocketCancel()) is expected
