from __future__ import annotations

import unittest


class TelegramProxyRouteCatalogTests(unittest.TestCase):
    def test_stable_wss_routes_are_only_dc2_and_dc4(self) -> None:
        from telegram_proxy.proxy.route_catalog import (
            RouteStatus,
            stable_wss_domains_for_dc,
            wss_enabled_dcs,
        )

        self.assertEqual(wss_enabled_dcs(), (2, 4))
        self.assertEqual(
            stable_wss_domains_for_dc(2, is_media=False),
            ("kws2.web.telegram.org", "kws2-1.web.telegram.org"),
        )
        self.assertEqual(
            stable_wss_domains_for_dc(2, is_media=True),
            ("kws2-1.web.telegram.org", "kws2.web.telegram.org"),
        )
        self.assertEqual(
            stable_wss_domains_for_dc(4, is_media=False),
            ("kws4.web.telegram.org", "kws4-1.web.telegram.org"),
        )
        self.assertEqual(stable_wss_domains_for_dc(1, is_media=False), ())
        self.assertEqual(stable_wss_domains_for_dc(203, is_media=False), ())
        self.assertEqual(RouteStatus.STABLE.value, "stable")

    def test_candidate_zws_routes_are_recorded_but_not_used_as_stable(self) -> None:
        from telegram_proxy.proxy.route_catalog import (
            candidate_wss_domains_for_dc,
            stable_wss_domains_for_dc,
        )

        self.assertEqual(
            candidate_wss_domains_for_dc(2, is_media=False),
            ("zws2.web.telegram.org", "zws2-1.web.telegram.org"),
        )
        self.assertEqual(
            candidate_wss_domains_for_dc(4, is_media=True),
            ("zws4-1.web.telegram.org", "zws4.web.telegram.org"),
        )
        self.assertNotIn("zws2.web.telegram.org", stable_wss_domains_for_dc(2, is_media=False))
        self.assertNotIn("zws4.web.telegram.org", stable_wss_domains_for_dc(4, is_media=False))

    def test_fallback_only_routes_document_non_wss_dcs(self) -> None:
        from telegram_proxy.proxy.route_catalog import (
            fallback_only_reason,
            route_status_for_dc,
        )

        for dc in (1, 3, 5, 203):
            with self.subTest(dc=dc):
                self.assertEqual(route_status_for_dc(dc), "fallback_only")
                self.assertIn("101", fallback_only_reason(dc))

        self.assertEqual(route_status_for_dc(2), "stable")
        self.assertEqual(route_status_for_dc(4), "stable")

    def test_dc_map_uses_route_catalog_stable_domains(self) -> None:
        from telegram_proxy.proxy import dc_map

        self.assertEqual(
            dc_map.WSS_DOMAINS,
            {
                2: ["kws2.web.telegram.org", "kws2-1.web.telegram.org"],
                4: ["kws4.web.telegram.org", "kws4-1.web.telegram.org"],
            },
        )
        self.assertEqual(dc_map.ws_domains_for_dc(2, False), ["kws2.web.telegram.org", "kws2-1.web.telegram.org"])
        self.assertEqual(dc_map.ws_domains_for_dc(2, True), ["kws2-1.web.telegram.org", "kws2.web.telegram.org"])
        self.assertEqual(
            dc_map.ws_domains_for_dc(203, False),
            ["kws2.web.telegram.org", "kws2-1.web.telegram.org", "kws4.web.telegram.org", "kws4-1.web.telegram.org"],
        )


if __name__ == "__main__":
    unittest.main()
