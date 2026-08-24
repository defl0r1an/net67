from __future__ import annotations

import unittest

from dns.custom_providers import CUSTOM_DNS_CATEGORY, build_dns_providers_with_custom
from settings import schema
from settings.normalize import normalize_dns


class CustomDnsSettingsTests(unittest.TestCase):
    def test_default_dns_settings_include_empty_custom_servers_list(self) -> None:
        self.assertEqual(schema.default_dns()["custom_servers"], [])

    def test_custom_dns_settings_are_normalized(self) -> None:
        normalized = normalize_dns(
            {
                "custom_servers": [
                    {
                        "id": "home",
                        "name": " Домашний DNS ",
                        "ipv4": ["8.8.8.8", "8.8.8.8", "bad"],
                        "ipv6": ["2001:4860:4860::8888"],
                    },
                    {
                        "id": "empty",
                        "name": "Пустой",
                        "ipv4": [],
                    },
                ]
            }
        )

        self.assertEqual(
            normalized["custom_servers"],
            [
                {
                    "id": "home",
                    "name": "Домашний DNS",
                    "ipv4": ["8.8.8.8"],
                    "ipv6": ["2001:4860:4860::8888"],
                }
            ],
        )

    def test_custom_dns_settings_become_provider_group(self) -> None:
        providers = build_dns_providers_with_custom(
            {"Основные": {"Cloudflare": {"ipv4": ["1.1.1.1"], "ipv6": []}}},
            [
                {
                    "id": "home",
                    "name": "Домашний DNS",
                    "ipv4": ["8.8.8.8"],
                    "ipv6": [],
                }
            ],
        )

        self.assertIn(CUSTOM_DNS_CATEGORY, providers)
        self.assertEqual(providers[CUSTOM_DNS_CATEGORY]["Домашний DNS"]["ipv4"], ["8.8.8.8"])
        self.assertIn("Cloudflare", providers["Основные"])


if __name__ == "__main__":
    unittest.main()
