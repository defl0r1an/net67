"""Проверка сайта после «Применить» — уже через пресет пользователя."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from blockcheck import strategy_apply_check as check
from blockcheck.strategy_search import verdict as rules
from blockcheck.strategy_search.verdict import ProbeOutcome
from utils.socket_cancel import SocketCancel

OK = ProbeOutcome(rules.PROBE_OK, "HTTP 200", 50.0, body_size=60_000)
RESET = ProbeOutcome(rules.PROBE_BLOCKED, "соединение сброшено", 30.0, "reset")


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> bool:
        self.now += seconds
        return True


class WaitTests(unittest.TestCase):
    def test_waits_for_zapret_then_settles(self) -> None:
        clock = _Clock()
        states = iter([False, False, True])
        self.assertTrue(
            check.wait_until_running(lambda: next(states), restarting=False, sleep=clock.sleep, cancelled=lambda: False, clock=clock)
        )
        self.assertAlmostEqual(clock.now, 2 * check.POLL_SECONDS + check.READY_SETTLE_SECONDS)

    def test_zapret_that_never_starts_gives_up(self) -> None:
        clock = _Clock()
        self.assertFalse(
            check.wait_until_running(lambda: False, restarting=False, sleep=clock.sleep, cancelled=lambda: False, clock=clock)
        )

    def test_restart_waits_for_the_preset_to_be_reread(self) -> None:
        clock = _Clock()
        check.wait_until_running(lambda: True, restarting=True, sleep=clock.sleep, cancelled=lambda: False, clock=clock)
        self.assertGreaterEqual(clock.now, check.RESTART_SETTLE_SECONDS)


class CheckSiteTests(unittest.TestCase):
    def _run(self, outcomes_by_call, *, running=True):
        calls = iter(outcomes_by_call)
        with (
            patch("blockcheck.strategy_search.probes.resolve_target_addresses", return_value=(["1.1.1.1", "1.1.2.1"], "")),
            patch("blockcheck.strategy_search.probes.probe_https_addresses", side_effect=lambda host, addresses, cancel: next(calls)),
            patch.object(check, "wait_until_running", return_value=running),
        ):
            cancel = SocketCancel()
            cancel.sleep = lambda seconds: True
            return check.run_apply_check("discord.com", is_running=lambda: True, restarting=False, cancel=cancel)

    def test_site_open_through_preset_is_ok(self) -> None:
        self.assertEqual(self._run([[OK, OK]]).code, check.CHECK_OK)

    def test_failure_is_rechecked_once_before_reporting(self) -> None:
        self.assertEqual(self._run([[RESET, OK], [OK, OK]]).code, check.CHECK_OK)
        failed = self._run([[RESET, OK], [RESET, RESET]])
        self.assertEqual(failed.code, check.CHECK_FAILED)
        self.assertIn("сброшено", failed.text)

    def test_zapret_not_started_is_skipped(self) -> None:
        self.assertEqual(self._run([], running=False).code, check.CHECK_SKIPPED)

    def test_short_answer_is_topped_up_with_volume(self) -> None:
        short = ProbeOutcome(rules.PROBE_OK, "HTTP 200", 50.0, body_size=500)
        cut = ProbeOutcome(rules.PROBE_BLOCKED, "соединение замирает после ~16 КБ", 50.0, "reset", 500, rules.VOLUME_CUT)
        with patch("blockcheck.strategy_search.probes.probe_volume", return_value=cut):
            result = self._run([[short], [short]])
        self.assertEqual(result.code, check.CHECK_FAILED)
        self.assertIn("16 КБ", result.text)


class MessageTests(unittest.TestCase):
    def test_messages(self) -> None:
        kind, _title, body = check.apply_check_message("discord.com", check.CHECK_OK, "")
        self.assertEqual(kind, "success")
        self.assertIn("discord.com", body)
        kind, _title, body = check.apply_check_message("discord.com", check.CHECK_FAILED, "соединение сброшено")
        self.assertEqual(kind, "warning")
        self.assertIn("профиль", body)
        skipped = check.apply_check_message("discord.com", check.CHECK_SKIPPED, "обход не запустился")
        self.assertEqual(skipped[0], "warning")
        self.assertIn("завершить не удалось", skipped[2])


class ProtocolCheckTests(unittest.TestCase):
    def test_checks_measured_protocol_without_https_volume(self):
        for protocol, method, port, udp in (
            ("tcp_http", "probe_http_addresses", 80, False),
            ("udp_quic", "probe_quic_addresses", 443, True),
        ):
            with (
                self.subTest(protocol=protocol),
                patch("blockcheck.strategy_search.probes.resolve_target_addresses", return_value=(["1.1.1.1"], "")) as resolve,
                patch(f"blockcheck.strategy_search.probes.{method}", return_value=[OK]) as probe,
                patch("blockcheck.strategy_search.probes.probe_https_addresses") as https,
                patch("blockcheck.strategy_search.probes.probe_volume") as volume,
            ):
                token = SocketCancel()
                result = check.check_site("example.org", cancel=token, scan_protocol=protocol)
                self.assertEqual(result.code, check.CHECK_OK)
                resolve.assert_called_once_with("example.org", port, udp=udp)
                probe.assert_called_once_with("example.org", ["1.1.1.1"], cancel=token)
                https.assert_not_called()
                volume.assert_not_called()

    def test_redirect_does_not_claim_final_https_site_works(self):
        redirect = ProbeOutcome(rules.PROBE_OK, "HTTP 301", redirect_https=True)
        with (
            patch("blockcheck.strategy_search.probes.resolve_target_addresses", return_value=(["1.1.1.1"], "")),
            patch("blockcheck.strategy_search.probes.probe_http_addresses", return_value=[redirect]),
        ):
            result = check.check_site("example.org", cancel=SocketCancel(), scan_protocol="tcp_http")
        self.assertEqual(result.code, check.CHECK_SKIPPED)
        self.assertIn("конечного адреса", result.text)

    def test_retry_preserves_protocol(self):
        token = SocketCancel()
        token.sleep = lambda seconds: True
        with (
            patch.object(check, "wait_until_running", return_value=True),
            patch.object(check, "check_site", side_effect=[check.ApplyCheck(check.CHECK_FAILED), check.ApplyCheck(check.CHECK_OK)]) as probe,
        ):
            result = check.run_apply_check("example.org", is_running=lambda: True, restarting=False,
                                           cancel=token, scan_protocol="udp_quic")
        self.assertEqual(result.code, check.CHECK_OK)
        self.assertEqual(len(probe.call_args_list), 2)
        self.assertTrue(all(call.kwargs["scan_protocol"] == "udp_quic" for call in probe.call_args_list))
