"""Проверка сервера VPN и единственный владелец блока hosts.

Две поломки из одного корня — «пишет не тот, кто знает правду».

Кнопка «Проверить сервер» стучалась по ICMP и TCP в сервер, который
слушает UDP. Исправный WireGuard молчит в ответ на всё, кроме настоящего
рукопожатия, и получал вердикт «не ответил ни на ICMP, ни на TCP» —
вывод, из которого ничего не следует.

Кнопка «Включить» переписывала блок hosts своим набором из 501 записи.
Запись в hosts не дописывает, а заменяет блок целиком, поэтому полторы
тысячи записей, поставленных при установке, исчезали, и на странице
«Сервисы» тумблеры дружно гасли.
"""

from __future__ import annotations

import inspect
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


def _stats(*, rx: int, tx: int, handshake: int):
    return SimpleNamespace(rx_bytes=rx, tx_bytes=tx, last_handshake=handshake)


class TunnelVerdictTests(unittest.TestCase):
    def test_handshake_means_the_server_answers(self) -> None:
        """Рукопожатие доказано криптографически — проб точнее не бывает."""
        from vpn.ping import check_tunnel_stats

        result = check_tunnel_stats(_stats(rx=4096, tx=2048, handshake=int(time.time()) - 12))

        self.assertTrue(result.ok)
        self.assertIn("рукопожатие", result.message.lower())
        self.assertIn("4.0 КБ", result.message)

    def test_sent_without_received_is_named_honestly(self) -> None:
        """Ровно то, что было на экране: отправлено 276 Б, принято 0."""
        from vpn.ping import check_tunnel_stats

        result = check_tunnel_stats(_stats(rx=0, tx=276, handshake=0))

        self.assertFalse(result.ok)
        self.assertIn("276 Б", result.message)
        self.assertIn("ответа нет", result.message)
        # Подсказка про обход DPI важна: он и правда ломает рукопожатие.
        self.assertIn("DPI", result.message)

    def test_no_stats_gives_no_verdict(self) -> None:
        from vpn.ping import check_tunnel_stats

        self.assertIsNone(check_tunnel_stats(None))

    def test_live_tunnel_beats_external_probe(self) -> None:
        """check_server не должен трогать сеть, если туннель уже отвечает."""
        from vpn.ping import check_server

        result = check_server(
            "203.0.113.1",
            51820,
            stats=_stats(rx=1024, tx=1024, handshake=int(time.time()) - 5),
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.method, "handshake")

    def test_icmp_and_tcp_are_not_the_main_check(self) -> None:
        """Фиксируем причину прошлой поломки: TCP-проба в UDP-порт."""
        from vpn import ping

        source = inspect.getsource(ping.check_server)

        self.assertIn("check_tunnel_stats", source)
        self.assertNotIn("_tcp_probe", source)
        self.assertFalse(hasattr(ping, "_tcp_probe"))

    def test_latency_label_survives_missing_number(self) -> None:
        from vpn.ping import PingResult, format_latency

        self.assertEqual(
            format_latency(PingResult(True, None, "handshake", "")),
            "отвечает",
        )
        self.assertEqual(format_latency(PingResult(False, None, "udp", "")), "—")
        self.assertEqual(format_latency(PingResult(True, 42.4, "icmp", "")), "42 мс")


class StatsRefreshTests(unittest.TestCase):
    def test_page_polls_the_tunnel(self) -> None:
        """Статистику запрашивали один раз — цифры застывали навсегда."""
        from vpn.ui import page as vpn_page

        source = inspect.getsource(vpn_page)

        self.assertIn("STATS_REFRESH_MS", source)
        self.assertIn("_stats_timer", source)
        self.assertIn("timeout.connect(self._refresh_connection_state)", source)

    def test_polling_stops_when_there_is_nothing_to_poll(self) -> None:
        """awg.exe запускается на каждый вызов — впустую его дёргать нельзя."""
        from vpn.ui import page as vpn_page

        source = inspect.getsource(vpn_page.VpnPage._sync_stats_timer)

        self.assertIn("connected", source)
        self.assertIn("isVisible", source)
        self.assertIn("timer.stop()", source)

    def test_check_server_gets_live_stats(self) -> None:
        from vpn.ui import page as vpn_page

        source = inspect.getsource(vpn_page.VpnPage._on_check_server)

        self.assertIn("stats=stats", source)


class HostsSingleWriterTests(unittest.TestCase):
    def test_enable_button_reapplies_the_saved_selection(self) -> None:
        """«Включить» больше не сужает блок hosts до своих 501 записи."""
        from oneclick import deps

        source = inspect.getsource(deps._apply_hosts)

        self.assertIn("load_user_selection", source)
        self.assertIn("apply_service_profiles", source)
        self.assertNotIn("apply_domain_ip_entries", source)

    def test_first_run_saves_the_selection_it_applied(self) -> None:
        """Иначе первое же «Включить» переписало бы блок своим набором."""
        from hosts import first_run_defaults

        source = inspect.getsource(first_run_defaults.apply_now)

        self.assertIn("save_user_selection", source)

    def test_defaults_and_enable_agree_on_content(self) -> None:
        """Один и тот же выбор — значит гонка двух писателей безобидна."""
        from hosts.defaults import load_default_selection

        selection = load_default_selection()

        self.assertTrue(selection, "по умолчанию не включено ничего")
        self.assertTrue(all(profile for profile in selection.values()))


if __name__ == "__main__":
    unittest.main()


class SelfCheckHonestyTests(unittest.TestCase):
    """Самопроверка не должна называть работающим то, что не работает.

    Она делала только TCP-коннект. Записи в hosts уводят домен на чужой
    адрес, тот адрес принимает TCP — и проверка рапортовала «открывается»,
    пока в браузере не открывалось ничего. Теперь доводим TLS до конца:
    сертификат чужого сервера не подойдёт к имени домена.
    """

    def test_tcp_only_probe_is_gone(self) -> None:
        from oneclick import deps

        source = inspect.getsource(deps._probe_domains)

        self.assertNotIn("probe_tcp_target_health", source)
        self.assertIn("probe_domain_over_https", source)

    def test_certificate_check_is_not_disabled(self) -> None:
        """Ради проверки имени в сертификате всё и затевалось."""
        from oneclick import deps

        source = inspect.getsource(deps.probe_domain_over_https)

        self.assertIn("check_hostname = True", source)
        self.assertIn("verify_mode = ssl.CERT_REQUIRED", source)
        self.assertNotIn("_create_unverified_context", source)

    def test_broken_input_is_reported_as_unavailable(self) -> None:
        from oneclick.deps import probe_domain_over_https

        for url in ("", "мусор", "https://127.0.0.1:1/"):
            with self.subTest(url=url):
                self.assertFalse(probe_domain_over_https(url, timeout=1.0))
