from __future__ import annotations

import inspect
import unittest

import hosts.commands as hosts_commands
import hosts.services_catalog_worker as services_catalog_worker
from hosts.ui.page import HostsPage


class HostsServicesCatalogWorkerArchitectureTests(unittest.TestCase):
    def test_services_catalog_worker_receives_feature_actions_not_page_controller(self) -> None:
        self.assertTrue(hasattr(hosts_commands, "build_services_catalog_plan"))

        page_source = inspect.getsource(HostsPage._start_services_catalog_worker)
        worker_source = inspect.getsource(services_catalog_worker.HostsServicesCatalogWorker)
        command_source = inspect.getsource(hosts_commands.build_services_catalog_plan)

        self.assertNotIn("controller=self", page_source)
        self.assertNotIn("self._controller", worker_source)
        self.assertIn("self._hosts.create_services_catalog_worker", page_source)
        self.assertIn("_build_services_catalog_plan", worker_source)
        self.assertIn("_get_catalog_signature", worker_source)
        self.assertNotIn("hosts.commands", worker_source)
        self.assertIn("read_active_domain_ip_map", command_source)


if __name__ == "__main__":
    unittest.main()
