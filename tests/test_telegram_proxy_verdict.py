"""Вердикт отчёта о Telegram: следует из проб, а не из привычки.

Итог отчёта писал «Тип: блокировка TLS к IP Telegram (DPI)» одной
захардкоженной строкой — при любом числе заблокированных адресов и не
глядя на собственные пробы. В отчёте, где TCP не открывался ни к одному
из шестнадцати адресов, порт 80 тоже, а чужой SNI тоже, это была прямая
неправда: SYN без ответа — не DPI, инспектировать там нечего.

Неправда с последствием. Вывод «DPI» тянул совет «winws2 запущен — могут
работать через zapret», человек проверял обход и искал поломку там, где
её нет: обход меняет пакеты установленного соединения, а к
несуществующему ему прикладывать нечего.

Второе умолчание — внешний прокси. В режиме MTProxy он включён всегда,
и когда прямые пути закрыты, прокси уходит именно туда. Адреса у
человека не было, встроенных в сборку тоже, — а отчёт о нём не говорил
ни слова, и SOCKS5 timeout читался как «прокси сломался».

Первый набор проверок — ровно на том отчёте, который человек прислал.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


def _dead(ip: str, dc: str) -> dict:
    return {"ip": ip, "dc": dc, "tcp": False, "tls": None,
            "line": f"{ip:<20} {dc:<12} {'FAIL':>8}  {'—':>8}  TCP не подключается"}


def _fine(ip: str, dc: str) -> dict:
    return {"ip": ip, "dc": dc, "tcp": True, "tls": "ok",
            "line": f"{ip:<20} {dc:<12}    103ms      81ms  OK"}


def _broken(ip: str, dc: str) -> dict:
    return {"ip": ip, "dc": dc, "tcp": True, "tls": "blocked",
            "line": f"{ip:<20} {dc:<12}     90ms      12ms  BLOCKED (reset)"}


#: Все шестнадцать адресов из присланного отчёта: TCP не открылся нигде.
REPORTED_ALL_DEAD = [
    _dead("91.105.192.100", "DC203 CDN"),
    _dead("149.154.175.102", "DC3 media"),
    _dead("91.108.56.102", "DC5 media"),
    _dead("149.154.167.50", "DC2"),
    _dead("149.154.175.53", "DC1"),
    _dead("91.108.56.149", "DC5"),
    _dead("149.154.167.41", "DC2"),
    _dead("149.154.164.250", "DC4 media"),
    _dead("149.154.167.222", "DC2 media"),
    _dead("149.154.175.100", "DC3 (→DC1)"),
    _dead("91.108.56.134", "DC5"),
    _dead("149.154.167.91", "DC4"),
    _dead("149.154.167.151", "DC2 media"),
    _dead("149.154.175.52", "DC1 media"),
    _dead("149.154.175.55", "DC1"),
    _dead("149.154.167.220", "WSS relay"),
]

FOREIGN_SNI_TCP_DEAD = {"tcp": False, "tls": None, "line": "…"}
HTTP80_DEAD = {"tcp": False, "ok": False, "line": "…"}

WSS_ALL_TCP_FAIL = [{"dc": dc, "status": "TCP_FAIL"} for dc in (1, 2, 2, 3, 4, 4, 5)]


class ReportedCaseTests(unittest.TestCase):
    """Отчёт, присланный человеком, — дословно по сути."""

    def _verdict(self):
        from telegram_proxy.diagnostics.runner import classify_blocking

        return classify_blocking(
            REPORTED_ALL_DEAD, foreign_sni=FOREIGN_SNI_TCP_DEAD, http80=HTTP80_DEAD
        )

    def test_it_is_an_ip_block(self) -> None:
        from telegram_proxy.diagnostics.runner import BLOCK_IP

        self.assertEqual(self._verdict()["kind"], BLOCK_IP)

    def test_verdict_does_not_say_dpi(self) -> None:
        """SYN без ответа — не DPI. Слово «DPI» тут и было неправдой."""
        self.assertNotIn("DPI", self._verdict()["title"])

    def test_bypass_is_not_offered_as_a_cure(self) -> None:
        self.assertFalse(self._verdict()["dpi_can_help"])

    def test_evidence_is_named(self) -> None:
        """Вердикт без доказательства — снова вера на слово."""
        detail = self._verdict()["detail"]

        self.assertIn("16", detail)
        self.assertIn("порт 80", detail)

    def _summary(self, upstream: str) -> str:
        from telegram_proxy.diagnostics.runner import _build_summary

        return _build_summary(
            [p["line"] for p in REPORTED_ALL_DEAD],
            WSS_ALL_TCP_FAIL,
            {"status": "TIMEOUT", "error": "SOCKS5 timeout"},
            True,
            dc_probes=REPORTED_ALL_DEAD,
            foreign_sni=FOREIGN_SNI_TCP_DEAD,
            http80=HTTP80_DEAD,
            upstream=upstream,
        )

    def test_summary_no_longer_promises_zapret_help(self) -> None:
        summary = self._summary("empty")

        self.assertNotIn("могут работать через zapret", summary)
        self.assertIn("бессилен", summary)

    def test_empty_upstream_is_named_in_summary(self) -> None:
        summary = self._summary("empty")

        self.assertIn("Внешний прокси: включён, но не задан", summary)
        self.assertIn("укажите SOCKS5", summary)

    def test_timeout_is_explained(self) -> None:
        """Таймаут вместо «порт закрыт» — значит, прокси жив, но идти ему некуда."""
        summary = self._summary("empty")

        self.assertIn("идти ему некуда", summary)
        self.assertIn("внешний прокси не задан", summary)

    def test_ready_upstream_points_at_its_section(self) -> None:
        summary = self._summary("ready")

        self.assertNotIn("включён, но не задан", summary)
        self.assertIn("через внешний прокси", summary)


class VerdictKindsTests(unittest.TestCase):
    """Остальные виды — чтобы исправление не превратилось в новую захардкоженную строку."""

    def _classify(self, probes, **kwargs):
        from telegram_proxy.diagnostics.runner import classify_blocking

        return classify_blocking(probes, **kwargs)

    def test_all_fine_is_no_block(self) -> None:
        from telegram_proxy.diagnostics.runner import BLOCK_NONE

        verdict = self._classify([_fine("1.1.1.1", "DC1"), _fine("1.1.1.2", "DC2")])

        self.assertEqual(verdict["kind"], BLOCK_NONE)

    def test_relay_alive_among_dead_is_partial(self) -> None:
        """Картина 1 сентября: пятнадцать мёртвых, relay жив."""
        from telegram_proxy.diagnostics.runner import BLOCK_PARTIAL_IP

        probes = REPORTED_ALL_DEAD[:-1] + [_fine("149.154.167.220", "WSS relay")]

        verdict = self._classify(probes)

        self.assertEqual(verdict["kind"], BLOCK_PARTIAL_IP)
        self.assertEqual(verdict["dead"], 15)

    def test_foreign_name_passing_means_sni(self) -> None:
        from telegram_proxy.diagnostics.runner import BLOCK_SNI

        verdict = self._classify(
            [_broken("1.1.1.1", "DC2")],
            foreign_sni={"tcp": True, "tls": "ok"},
        )

        self.assertEqual(verdict["kind"], BLOCK_SNI)
        self.assertTrue(verdict["dpi_can_help"])

    def test_foreign_name_failing_means_tls_by_address(self) -> None:
        from telegram_proxy.diagnostics.runner import BLOCK_TLS

        verdict = self._classify(
            [_broken("1.1.1.1", "DC2")],
            foreign_sni={"tcp": True, "tls": "blocked"},
        )

        self.assertEqual(verdict["kind"], BLOCK_TLS)
        self.assertIn("DPI", verdict["title"])
        self.assertTrue(verdict["dpi_can_help"])

    def test_dpi_case_still_suggests_zapret(self) -> None:
        """Совет запустить обход уместен там, где соединение есть и его рвут."""
        from telegram_proxy.diagnostics.runner import _build_summary

        probes = [_broken("149.154.167.50", "DC2")]
        summary = _build_summary(
            [p["line"] for p in probes],
            [{"dc": 2, "status": "TLS_FAIL"}],
            {"status": "OK"},
            True,
            dc_probes=probes,
            foreign_sni={"tcp": True, "tls": "blocked"},
        )

        self.assertIn("могут работать через zapret", summary)
        self.assertNotIn("бессилен", summary)

    def test_no_probes_is_unknown_not_a_guess(self) -> None:
        from telegram_proxy.diagnostics.runner import BLOCK_UNKNOWN

        self.assertEqual(self._classify([])["kind"], BLOCK_UNKNOWN)


class UpstreamStateTests(unittest.TestCase):
    def _classify(self, **kwargs):
        from telegram_proxy.diagnostics.runner import classify_upstream

        base = {"effective": True, "host": "", "preset_id": "", "has_bundled": False}
        base.update(kwargs)
        return classify_upstream(**base)

    def test_nothing_to_route_to_is_empty(self) -> None:
        """Ровно конфигурация человека: MTProxy, адрес пустой, встроенных нет."""
        from telegram_proxy.diagnostics.runner import UPSTREAM_EMPTY

        self.assertEqual(self._classify(), UPSTREAM_EMPTY)

    def test_bundled_address_is_enough(self) -> None:
        """Без своего адреса берётся первый встроенный — это не «некуда»."""
        from telegram_proxy.diagnostics.runner import UPSTREAM_READY

        self.assertEqual(self._classify(has_bundled=True), UPSTREAM_READY)

    def test_own_host_is_ready(self) -> None:
        from telegram_proxy.diagnostics.runner import UPSTREAM_READY

        self.assertEqual(self._classify(host="10.0.0.5"), UPSTREAM_READY)

    def test_not_effective_is_off(self) -> None:
        from telegram_proxy.diagnostics.runner import UPSTREAM_OFF

        self.assertEqual(self._classify(effective=False), UPSTREAM_OFF)


class LegacyCallTests(unittest.TestCase):
    def test_lines_only_call_gets_the_right_verdict_too(self) -> None:
        """Старые вызовы передают одни строки — и тоже не должны слышать про DPI."""
        from telegram_proxy.diagnostics.runner import _build_summary

        summary = _build_summary(
            dc_lines=[p["line"] for p in REPORTED_ALL_DEAD],
            wss_results=WSS_ALL_TCP_FAIL,
            proxy_result={"status": "OK"},
            winws2_running=True,
        )

        self.assertIn("блокировка по IP", summary)
        self.assertNotIn("могут работать через zapret", summary)


class SourceGuardTests(unittest.TestCase):
    def test_the_hardcoded_verdict_is_gone(self) -> None:
        """Строка, которую печатали при любом раскладе, возвращаться не должна."""
        source = (
            PROJECT_SRC / "telegram_proxy" / "diagnostics" / "runner.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn('"  Тип: блокировка TLS к IP Telegram (DPI)"', source)


if __name__ == "__main__":
    unittest.main()
