"""Сохранённый профиль исчез из каталога — сервис не выпадает из hosts.

В каталоге 2026.09.28.1 исходный проект убрал play2go.cloud DNS. У того,
кто выбрал его на «Сервисах», после обновления сервис молча пропадал из
блока hosts. Теперь пишутся адреса профиля по умолчанию.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import hosts.hosts as hosts_module  # noqa: E402


class MissingProfileFallbackTests(unittest.TestCase):
    def _manager(self):
        manager = hosts_module.HostsManager.__new__(hosts_module.HostsManager)
        manager.status_callback = None
        manager._last_status = None
        return manager

    def test_removed_profile_falls_back_to_xbox(self) -> None:
        manager = self._manager()
        written: list = []

        def rows(service, profile):
            return [("claude.ai", "87.228.47.201")] if profile == "xbox_dns" else []

        with (
            mock.patch.object(hosts_module, "get_service_domain_ip_rows", side_effect=rows),
            mock.patch(
                "hosts.proxy_domains.get_service_available_dns_profiles",
                return_value=["xbox_dns", "comss_dns"],
            ),
            mock.patch.object(hosts_module.HostsManager, "apply_domain_ip_rows", side_effect=lambda r: written.extend(r) or True),
        ):
            ok = manager.apply_service_dns_selections({"Claude": "play2go_cloud_dns"})

        self.assertTrue(ok)
        self.assertEqual(written, [("claude.ai", "87.228.47.201")])

    def test_existing_profile_is_used_as_is(self) -> None:
        manager = self._manager()
        written: list = []
        with (
            mock.patch.object(
                hosts_module,
                "get_service_domain_ip_rows",
                side_effect=lambda s, p: [("claude.ai", "45.88.174.254")] if p == "comss_dns" else [("claude.ai", "x")],
            ),
            mock.patch.object(hosts_module.HostsManager, "apply_domain_ip_rows", side_effect=lambda r: written.extend(r) or True),
        ):
            manager.apply_service_dns_selections({"Claude": "comss_dns"})

        self.assertEqual(written, [("claude.ai", "45.88.174.254")])


if __name__ == "__main__":
    unittest.main()
