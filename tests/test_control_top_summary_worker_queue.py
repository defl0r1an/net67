from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from presets.ui.control.additional_settings_runtime import ModeControlRefreshRuntime, create_refresh_runtime
from presets.ui.control.zapret2.page import Zapret2ModeControlPage


class ControlTopSummaryWorkerQueueTests(unittest.TestCase):
    def test_top_summary_queue_uses_shared_latest_worker_state(self) -> None:
        runtime_source = inspect.getsource(ModeControlRefreshRuntime)
        init_source = inspect.getsource(ModeControlRefreshRuntime.__init__)

        self.assertIn("LatestValueWorkerState", runtime_source)
        self.assertIn("top_summary_state", runtime_source)
        self.assertNotIn("self.top_summary_pending = False", init_source)
        self.assertNotIn("self.top_summary_start_scheduled = False", init_source)


if __name__ == "__main__":
    unittest.main()
