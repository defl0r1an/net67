from __future__ import annotations

import unittest
from unittest.mock import patch

from hosts import relay_check


class HostsRelayCheckTests(unittest.TestCase):
    ROWS = [
        ("chatgpt.com", "144.31.82.230"),
        ("api.openai.com", "144.31.82.230"),
        ("auth.openai.com", "144.31.82.230"),
        ("cdn.openai.com", "104.18.33.45"),
    ]

    RELAYS = {"144.31.82.230"}

    def test_relay_is_what_the_catalog_calls_a_relay(self) -> None:
        self.assertEqual(relay_check.relay_addresses(self.ROWS, self.RELAYS), ["144.31.82.230"])
        self.assertEqual(relay_check.relay_addresses(self.ROWS, set()), [])

    def test_shared_site_address_is_not_a_relay(self) -> None:
        # Настоящий адрес сайта бывает общим для десятка имён и из России не отвечает
        # (CloudFront у Comss, 35.228.34.253 у GeoHide). В 21.1.7.116–119 его считали посредником.
        rows = [("a%d.example" % i, "65.9.46.4") for i in range(12)] + self.ROWS
        with patch.object(relay_check, "_connects", return_value=False) as connects:
            self.assertEqual(relay_check.unreachable_relays(rows, self.RELAYS), ["144.31.82.230"])
        self.assertEqual([call.args[0] for call in connects.call_args_list], ["144.31.82.230"])

    def test_blocked_relay_is_reported(self) -> None:
        with patch.object(relay_check, "_connects", return_value=False):
            self.assertEqual(relay_check.unreachable_relays(self.ROWS, self.RELAYS), ["144.31.82.230"])
        with patch.object(relay_check, "_connects", return_value=True):
            self.assertEqual(relay_check.unreachable_relays(self.ROWS, self.RELAYS), [])

    def test_rows_without_a_relay_are_not_probed(self) -> None:
        with patch.object(relay_check, "_connects") as connects:
            self.assertEqual(relay_check.unreachable_relays([("a.example", "1.2.3.4")], self.RELAYS), [])
            connects.assert_not_called()




    def test_one_lost_attempt_is_not_a_blocked_relay(self) -> None:
        attempts = iter([False, True])
        with patch.object(relay_check, "_connect_once", side_effect=lambda _address: next(attempts)), patch.object(
            relay_check.time, "sleep"
        ):
            self.assertTrue(relay_check._connects("144.31.82.230"))


    # Настоящий адрес Instagram стоит сразу у нескольких имён и из России без обхода
    # не отвечает. В выпуске 21.1.7.116 он считался посредником и запрещал любую правку hosts.




    # Как у GeoHide для Gemini: четыре посредника на имя, один из них провайдер закрыл.


class HostsFastWriteTests(unittest.TestCase):
    def test_switch_does_not_wait_for_relays_or_require_internet(self):
        from hosts import hosts as hosts_module

        manager = hosts_module.HostsManager.__new__(hosts_module.HostsManager)
        rows = [("chatgpt.com", "138.124.29.69"), ("api.openai.com", "138.124.29.69")]
        with (
            patch.object(hosts_module, "_build_service_selection_rows", return_value=(rows, True)),
            patch.object(relay_check, "_connects", side_effect=AssertionError("Сеть в быстрой записи")),
            patch.object(hosts_module.HostsManager, "apply_domain_ip_rows", return_value=True) as write,
        ):
            self.assertTrue(manager.apply_service_dns_selections({"ChatGPT": "net67_dns"}))
        write.assert_called_once_with(rows)

    def test_missing_catalog_rows_do_not_erase_the_current_hosts(self):
        from hosts import hosts as hosts_module

        manager = hosts_module.HostsManager.__new__(hosts_module.HostsManager)
        statuses = []
        manager.set_status = statuses.append
        with (
            patch.object(hosts_module, "_build_service_selection_rows", return_value=([], True)),
            patch.object(hosts_module.HostsManager, "apply_domain_ip_rows") as write,
        ):
            self.assertFalse(manager.apply_service_dns_selections({"ChatGPT": "net67_dns"}))
        write.assert_not_called()
        self.assertTrue(statuses)

    def test_catalog_uses_the_own_net67_relay(self):
        from hosts.proxy_domains import get_relay_addresses

        self.assertIn("138.124.29.69", get_relay_addresses())
