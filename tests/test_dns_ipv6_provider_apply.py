from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch


class DnsIpv6ProviderApplyTests(unittest.TestCase):
    def test_provider_dns_plan_accepts_ipv6_only_when_ipv6_is_available(self) -> None:
        from dns.page_plans import build_provider_dns_plan

        plan = build_provider_dns_plan(
            name="Мой IPv6 DNS",
            data={"ipv4": [], "ipv6": ["2001:4860:4860::8888"]},
            ipv6_available=True,
        )

        self.assertTrue(plan.valid)
        self.assertEqual(plan.ipv4, [])
        self.assertEqual(plan.ipv6, ["2001:4860:4860::8888"])

    def test_provider_dns_plan_rejects_ipv6_only_when_ipv6_is_unavailable(self) -> None:
        from dns.page_plans import build_provider_dns_plan

        plan = build_provider_dns_plan(
            name="Мой IPv6 DNS",
            data={"ipv4": [], "ipv6": ["2001:4860:4860::8888"]},
            ipv6_available=False,
        )

        self.assertFalse(plan.valid)
        self.assertIn("нет DNS", plan.log_message)

    def test_runtime_applies_ipv6_only_provider_without_ipv4_write(self) -> None:
        from dns.runtime import apply_provider_dns

        manager = _DnsManagerStub()

        with patch("dns.runtime._get_dns_manager", return_value=manager):
            affected = apply_provider_dns(
                ["Ethernet"],
                [],
                ["2001:4860:4860::8888", "2001:4860:4860::8844"],
                ipv6_available=True,
            )

        self.assertEqual(affected, 1)
        self.assertEqual(
            manager.calls,
            [
                (
                    "Ethernet",
                    "2001:4860:4860::8888",
                    "2001:4860:4860::8844",
                    "IPv6",
                )
            ],
        )
        self.assertTrue(manager.flushed)


class _DnsManagerStub:
    def __init__(self):
        self.calls: list[tuple[str, str, str | None, str]] = []
        self.flushed = False

    def set_custom_dns(self, adapter: str, primary: str, secondary: str | None, family: str):
        self.calls.append((adapter, primary, secondary, family))
        return True, ""

    def flush_dns_cache(self):
        self.flushed = True
        return SimpleNamespace(success=True)


if __name__ == "__main__":
    unittest.main()
