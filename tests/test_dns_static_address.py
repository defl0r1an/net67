"""Адаптер со статическим адресом: автоматического DNS у него нет.

Владелец предупредил 26 октября 2026: «если я выберу автоматически,
интернет у меня отвалится, т.к. у меня статика». «Автоматически» стирает
DNS, прописанный вручную, и Windows берёт тот, что выдаёт DHCP, — а при
статике выдавать некому. Так же ломали интернет сборка и удаление
программы, когда снимали шифрованный DNS сбросом на автоматический.

Отсюда три правила, которые держат тесты:
- плитка «Автоматически» не применяется к адаптеру без DHCP;
- перед 127.0.0.1 программа запоминает прежний DNS адаптера;
- запись о прежнем DNS исчезает, когда шифрованный DNS сняли сами.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from dns import local_proxy  # noqa: E402
from dns.adapters import DnsAdapter  # noqa: E402
from dns.page_plans import adapters_without_automatic_dns  # noqa: E402
from test_dns_local_proxy import FakeSystem  # noqa: E402

STATIC = DnsAdapter(
    "{00000000-0000-0000-0000-0000000000aa}", "OpenWrt", "vEthernet", "ethernet",
    connected=True, internet=True, static_ipv4=("192.168.3.250",), dhcp=False,
)
DHCP = DnsAdapter(
    "{00000000-0000-0000-0000-0000000000bb}", "Wi-Fi", "Intel", "wifi",
    connected=True, internet=False, auto_ipv4=("192.168.1.1",),
)


class AutomaticTileTests(unittest.TestCase):
    def test_static_adapter_is_named_only_when_it_is_selected(self) -> None:
        adapters = (STATIC, DHCP)

        self.assertEqual(adapters_without_automatic_dns(adapters, [STATIC.guid, DHCP.guid]), ("OpenWrt",))
        self.assertEqual(adapters_without_automatic_dns(adapters, [DHCP.guid]), ())

    def test_flag_comes_from_windows_and_defaults_to_dhcp(self) -> None:
        from dns.adapters import build_dns_adapters
        from dns.winapi import IF_TYPE_ETHERNET_CSMACD, InternetRoute, RawInterface, StaticDns

        raw = RawInterface(
            guid=STATIC.guid, index=2, ipv6_index=2, name="OpenWrt", description="vEthernet",
            if_type=IF_TYPE_ETHERNET_CSMACD, connected=True, dhcp=False,
        )
        built = build_dns_adapters([raw], InternetRoute(ipv4_index=2), {STATIC.guid: StaticDns(ipv4=("192.168.3.250",))})
        self.assertFalse(built[0].dhcp)
        self.assertTrue(DnsAdapter("{x}", "n", "d", "ethernet", connected=True, internet=True).dhcp)


class PreviousDnsRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.system = FakeSystem(Path(folder.name))
        self.path = self.system.work_dir() / local_proxy.PREVIOUS_DNS_NAME

    def _record(self) -> dict:
        return {item["guid"]: item for item in json.loads(self.path.read_text(encoding="utf-8"))["adapters"]}

    def test_old_dns_is_remembered_and_a_mode_switch_does_not_overwrite_it(self) -> None:
        local_proxy.remember_previous_dns(
            [{"guid": STATIC.guid, "name": "OpenWrt", "ipv4": ["192.168.3.250"], "ipv6": [], "dhcp": False}],
            system=self.system,
        )
        # Смена режима: адаптер уже на 127.0.0.1 — запись о настоящем прежнем DNS остаётся.
        local_proxy.remember_previous_dns(
            [{"guid": STATIC.guid, "name": "OpenWrt", "ipv4": ["127.0.0.1"], "ipv6": ["::1"], "dhcp": False}],
            system=self.system,
        )

        saved = self._record()[STATIC.guid]
        self.assertEqual(saved["ipv4"], ["192.168.3.250"])
        self.assertFalse(saved["dhcp"])

    def test_automatic_adapter_is_remembered_as_automatic(self) -> None:
        local_proxy.remember_previous_dns(
            [{"guid": DHCP.guid, "name": "Wi-Fi", "ipv4": [], "ipv6": [], "dhcp": True}], system=self.system
        )
        self.assertEqual(self._record()[DHCP.guid]["ipv4"], [])

    def test_stopping_the_engine_forgets_the_record(self) -> None:
        local_proxy.remember_previous_dns(
            [{"guid": STATIC.guid, "name": "OpenWrt", "ipv4": ["192.168.3.250"], "ipv6": [], "dhcp": False}],
            system=self.system,
        )
        local_proxy.stop(system=self.system)
        self.assertFalse(self.path.exists())

    def test_apply_dns_remembers_only_before_pointing_at_the_engine(self) -> None:
        from dns import runtime
        from dns.state import DnsState

        state = DnsState(adapters=(STATIC, DHCP))
        remembered = []
        with patch.object(runtime, "load_state", return_value=state), patch.object(
            runtime, "write_doh_templates", return_value=None
        ), patch.object(runtime, "check_servers", return_value=None), patch.object(
            runtime.winapi, "write_dns"
        ), patch.object(runtime.winapi, "flush_resolver_cache"), patch.object(
            local_proxy, "remember_previous_dns", side_effect=lambda entries: remembered.append(entries)
        ):
            runtime.apply_dns([STATIC.guid], ["127.0.0.1"], ["::1"])
            runtime.apply_dns([STATIC.guid], ["9.9.9.9"], [])

        self.assertEqual(len(remembered), 1)
        self.assertEqual(remembered[0][0]["ipv4"], ["192.168.3.250"])
        self.assertFalse(remembered[0][0]["dhcp"])


class AutomaticTilePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_automatic_is_refused_for_a_static_adapter(self) -> None:
        from dns.state import DnsState
        from dns.ui.page import AUTO_CHOICE, NetworkPage

        state = DnsState(adapters=(STATIC,), ipv6_available=False, doh_supported=True)
        feature = SimpleNamespace(
            consume_warmed_page_data=Mock(return_value=state),
            create_page_load_worker=Mock(),
            create_dns_apply_worker=Mock(),
            create_dns_flush_cache_worker=Mock(),
            create_dns_latency_worker=Mock(),
            create_isp_dns_warning_worker=Mock(),
            create_custom_server_worker=Mock(),
        )
        with patch("dns.ui.page.InfoBar") as info_bar:
            page = NetworkPage(deps=SimpleNamespace(dns_feature=feature, open_custom_server=Mock()))
            self.addCleanup(page.deleteLater)
            for lane in page._lanes():
                lane.request = Mock()
            page.on_page_activated()

            page.grid.activated.emit(AUTO_CHOICE)

            page._apply_lane.request.assert_not_called()
            self.assertEqual(info_bar.warning.call_args.kwargs["title"], "У адаптера статический адрес")
            self.assertIn("«OpenWrt»", info_bar.warning.call_args.kwargs["content"])


class RemovalScriptTests(unittest.TestCase):
    def test_script_restores_the_recorded_dns_before_falling_back(self) -> None:
        script = (ROOT / "installer" / "remove_dnscrypt.ps1").read_text(encoding="ascii")
        self.assertIn(local_proxy.PREVIOUS_DNS_NAME, script)
        restore = script.index("gets its DNS back")
        automatic = script.index("switched back to automatic DNS")
        gateway = script.index("DNS set to its gateway")
        self.assertLess(restore, automatic)
        self.assertLess(automatic, gateway)
        # DHCP проверяется до сброса на автоматический — статику автоматикой не ломаем.
        self.assertLess(script.index('$dhcp.Dhcp -eq "Enabled"'), automatic)


if __name__ == "__main__":
    unittest.main()
