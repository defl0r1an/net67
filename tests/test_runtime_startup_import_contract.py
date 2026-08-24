from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class RuntimeStartupImportContractTests(unittest.TestCase):
    def test_runtime_startup_module_does_not_import_heavy_runtime_helpers_at_module_load(self) -> None:
        from winws_runtime.runtime import startup

        module_prefix = inspect.getsource(startup).split("def init_launch_runtime_api", 1)[0]

        self.assertNotIn("from log.log import log", module_prefix)
        self.assertNotIn("from settings.mode import", module_prefix)
        self.assertNotIn("from winws_runtime.runtime.status_feedback import", module_prefix)


if __name__ == "__main__":
    unittest.main()
