"""Настоящие HTTP-ответы: части, обрывы и молчание вместо моков чтения."""

from __future__ import annotations

import hashlib
import re
import socket
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from updater import download_transfer as transfer
from updater.update_pipeline import UpdateArtifact, UpdatePipeline


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def do_HEAD(self):
        state = self.server.state
        if state.head_rejected:
            self.send_response(405)
            self.send_header("Content-Length", "0")
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(state.payload)))
            if state.ranges:
                self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        state = self.server.state
        requested = self.headers.get("Range")
        with state.lock:
            state.requests.append(requested)
            fault = state.faults > 0
            state.faults -= int(fault)
        payload = state.payload
        match = re.fullmatch(r"bytes=(\d+)-(\d+)", requested or "")
        ranged = bool(match and not state.ignore_range)
        start, end = map(int, match.groups()) if ranged else (0, len(payload) - 1)
        if ranged and state.reject_range:
            self.send_response(416)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(206 if ranged else 200)
        if state.chunked:
            self.send_header("Transfer-Encoding", "chunked")
        else:
            self.send_header("Content-Length", str(end - start + 1))
        if ranged:
            bad = state.bad_range
            range_start = start + int(bad is True or bad == "start")
            range_end = end + int(bad == "end")
            range_total = len(payload) + int(bad == "total")
            if bad != "missing":
                self.send_header("Content-Range", f"bytes {range_start}-{range_end}/{range_total}")
        self.end_headers()
        body = payload[start:end + 1]
        try:
            if fault:
                self.wfile.write(body[:8192])
                self.wfile.flush()
                state.prefix_sent.set()
                if state.stall:
                    state.stopping.wait(state.stall)
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            if state.chunked:
                for offset in range(0, len(body), 1024):
                    chunk = body[offset:offset + 1024]
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            elif state.slow:
                for offset in range(0, len(body), 1024):
                    self.wfile.write(body[offset:offset + 1024])
                    self.wfile.flush()
                    state.stopping.wait(state.slow)
            else:
                self.wfile.write(body)
                self.wfile.flush()
        except (OSError, ValueError):
            pass


@contextmanager
def _server(payload, **options):
    state = SimpleNamespace(
        payload=payload, ranges=True, head_rejected=False, ignore_range=False,
        bad_range=False, reject_range=False, faults=0, stall=0, slow=0, chunked=False,
        requests=[], lock=threading.Lock(), prefix_sent=threading.Event(), stopping=threading.Event(),
    )
    for key, value in options.items():
        setattr(state, key, value)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.state = state
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    try:
        yield transfer.DownloadSource(f"http://127.0.0.1:{server.server_port}/setup.exe", True), state
    finally:
        state.stopping.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


class UpdaterHttpDownloadTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.destination = self.root / "installer.part"
        self.events = []
        self.progress = transfer.ThrottledProgress(lambda *args: self.events.append(args), interval_seconds=0)
        self.token = transfer.CancellationToken()
        for name, value in (("READ_TIMEOUT_SECONDS", 0.15), ("CONNECT_TIMEOUT_SECONDS", 1), ("RETRY_DELAY_SECONDS", 0)):
            patcher = patch.object(transfer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _download(self, source, size, **options):
        transfer.download_source(source, str(self.destination), expected_size=size,
                                 token=self.token, progress=self.progress, **options)

    def _artifact(self, source, payload, *, version="99.1.67"):
        return UpdateArtifact(version, "setup.exe", len(payload), hashlib.sha256(payload).hexdigest(), (source,))

    def _pipeline(self, artifact):
        layout = SimpleNamespace(update_cache_dir=self.root, root=self.root)
        with patch("updater.update_pipeline.APPLICATION_PATHS", layout):
            return UpdatePipeline(token=self.token).download_and_prepare(artifact)

    def test_small_file_resumes_received_prefix_after_disconnect(self):
        payload = bytes(range(256)) * 512
        statuses = []
        with _server(payload, faults=1) as (source, state):
            self._download(source, len(payload), on_status=statuses.append)
        self.assertEqual(self.destination.read_bytes(), payload)
        self.assertEqual(state.requests, [None, f"bytes=8192-{len(payload) - 1}"])
        self.assertTrue(any("2 из 3" in status for status in statuses))

    def test_large_file_resumes_each_segment_without_redownloading_completed_parts(self):
        payload = bytes(range(256)) * (24 * 1024)
        with _server(payload, faults=1) as (source, state):
            self._download(source, len(payload))
        self.assertEqual(self.destination.read_bytes(), payload)
        starts = [int(re.match(r"bytes=(\d+)-", value).group(1)) for value in state.requests]
        self.assertTrue(any(start % (len(payload) // 4) == 8192 for start in starts))
        self.assertEqual(self.events[-1], (100, len(payload), len(payload)))
        self.assertLessEqual(len(state.requests), 8)

    def test_silent_response_times_out_and_retries_with_saved_bytes(self):
        payload = b"x" * 100_000
        with _server(payload, faults=1, stall=0.7) as (source, state):
            began = time.monotonic()
            self._download(source, len(payload))
            elapsed = time.monotonic() - began
        self.assertLess(elapsed, 0.7)
        self.assertEqual(state.requests, [None, "bytes=8192-99999"])
        self.assertEqual(self.destination.read_bytes(), payload)

    def test_slow_continuous_bytes_are_reported_and_not_treated_as_silence(self):
        payload = b"x" * 16_384
        with _server(payload, slow=0.025) as (source, state):
            self._download(source, len(payload))
        self.assertEqual(state.requests, [None])
        self.assertTrue(any(0 < done < len(payload) for _, done, _ in self.events))
        self.assertEqual(self.destination.read_bytes(), payload)

    def test_ignored_range_restarts_same_response_without_appending(self):
        payload = b"new installer" * 10_000
        self.destination.write_bytes(payload[:8192])
        with _server(payload, ignore_range=True) as (source, state):
            self._download(source, len(payload))
        self.assertEqual(len(state.requests), 1)
        self.assertEqual(self.destination.read_bytes(), payload)
        self.assertTrue(any(done == 0 for _, done, _ in self.events))

    def test_segmented_download_falls_back_if_head_advertises_unsupported_ranges(self):
        payload = b"z" * (5 * 1024 * 1024)
        with _server(payload, ignore_range=True) as (source, state):
            self._download(source, len(payload))
        self.assertIn(None, state.requests)
        self.assertEqual(self.destination.read_bytes(), payload)

    def test_invalid_content_range_is_rejected_before_appending(self):
        payload = b"a" * 100_000
        for field in ("start", "end", "total", "missing"):
            with self.subTest(field=field):
                self.destination.write_bytes(payload[:8192])
                with _server(payload, bad_range=field) as (source, _state):
                    with self.assertRaisesRegex(transfer.UpdatePipelineError, "неверный диапазон"):
                        self._download(source, len(payload), max_retries=1)
                self.assertFalse(self.destination.exists())

    def test_rejected_range_can_retry_from_start(self):
        payload = b"a" * 100_000
        self.destination.write_bytes(payload[:8192])
        with _server(payload, reject_range=True) as (source, state):
            self._download(source, len(payload))
        self.assertEqual(state.requests, ["bytes=8192-99999", None])
        self.assertEqual(self.destination.read_bytes(), payload)

    def test_get_works_when_head_is_not_supported(self):
        payload = b"installer" * 1000
        with _server(payload, head_rejected=True) as (source, _state):
            self._download(source, len(payload))
        self.assertEqual(self.destination.read_bytes(), payload)

    def test_chunked_response_is_saved_without_http_framing(self):
        payload = b"installer" * 1000
        with _server(payload, chunked=True, head_rejected=True) as (source, _state):
            self._download(source, len(payload))
        self.assertEqual(self.destination.read_bytes(), payload)

    def test_server_size_change_is_rejected_without_handoff(self):
        with _server(b"short file") as (source, state):
            with self.assertRaisesRegex(transfer.UpdateIntegrityError, "Размер файла"):
                self._download(source, 100_000)
        self.assertEqual(state.requests, [])
        self.assertFalse(self.destination.exists())

    def test_cancel_interrupts_silent_socket_without_retry(self):
        payload = b"x" * 100_000
        with _server(payload, faults=1, stall=2) as (source, state):
            failures = []

            def run():
                try:
                    self._download(source, len(payload))
                except Exception as exc:
                    failures.append(exc)

            with patch.object(transfer, "READ_TIMEOUT_SECONDS", 10):
                thread = threading.Thread(target=run, daemon=True)
                thread.start()
                self.assertTrue(state.prefix_sent.wait(2))
                self.token.cancel()
                thread.join(1)
                self.assertFalse(thread.is_alive())
            self.assertEqual(state.requests, [None])
            self.assertIsInstance(failures[0], transfer.UpdateCancelled)

    def test_cancel_interrupts_retry_pause(self):
        payload = b"x" * 100_000
        statuses = []

        def status(message):
            statuses.append(message)
            self.token.cancel()

        with _server(payload, faults=1) as (source, state):
            with patch.object(transfer, "RETRY_DELAY_SECONDS", 4):
                began = time.monotonic()
                with self.assertRaises(transfer.UpdateCancelled):
                    self._download(source, len(payload), on_status=status)
                self.assertLess(time.monotonic() - began, 1)
        self.assertEqual(len(state.requests), 1)
        self.assertTrue(statuses)

    def test_failed_run_keeps_prefix_and_manual_retry_uses_it_then_verifies_installer(self):
        payload = b"x" * 100_000
        with _server(payload, faults=100) as (source, state):
            artifact = self._artifact(source, payload)
            with self.assertRaisesRegex(transfer.UpdatePipelineError, "Повторить"):
                self._pipeline(artifact)
            self.assertEqual(len(state.requests), 3)
            prefix = next(self.root.glob("downloads/partial-*/installer.part")).stat().st_size
            self.assertEqual(prefix, 3 * 8192)
            state.faults = 0
            handoff = self._pipeline(artifact)
            self.assertEqual(state.requests[3], f"bytes={prefix}-{len(payload) - 1}")
        self.assertEqual(Path(handoff.installer_path).read_bytes(), payload)
        self.assertEqual(list(self.root.glob("downloads/partial-*")), [])

    def test_changed_digest_for_same_version_does_not_reuse_old_prefix(self):
        before = b"x" * 100_000
        after = b"y" * len(before)
        with _server(before, faults=100) as (source, state):
            with self.assertRaises(transfer.UpdatePipelineError):
                self._pipeline(self._artifact(source, before))
            state.faults = 0
            state.payload = after
            state.requests.clear()
            handoff = self._pipeline(self._artifact(source, after))
        self.assertEqual(state.requests, [None])
        self.assertEqual(Path(handoff.installer_path).read_bytes(), after)

    def test_saved_segments_resume_even_when_head_stops_working(self):
        payload = b"x" * (5 * 1024 * 1024)
        with _server(payload, faults=100) as (source, state):
            artifact = self._artifact(source, payload)
            with self.assertRaises(transfer.UpdatePipelineError):
                self._pipeline(artifact)
            self.assertTrue(list(self.root.glob("downloads/partial-*/installer.part_segments/segment_*")))
            state.faults = 0
            state.head_rejected = True
            state.requests.clear()
            handoff = self._pipeline(artifact)
        self.assertTrue(all(request is not None for request in state.requests))
        self.assertEqual(Path(handoff.installer_path).read_bytes(), payload)

    def test_wrong_sha_never_reaches_handoff_and_discards_bad_parts(self):
        wanted = b"x" * 100_000
        with _server(b"y" * len(wanted)) as (source, _state):
            with patch("updater.update_pipeline.prepare_handoff") as handoff:
                with self.assertRaises(transfer.UpdateIntegrityError):
                    self._pipeline(self._artifact(source, wanted))
            handoff.assert_not_called()
        self.assertEqual(list(self.root.glob("downloads/partial-*")), [])


if __name__ == "__main__":
    unittest.main()
