from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class UiCleanupNonblockingContractTests(unittest.TestCase):
    def test_profile_order_cleanup_stops_workers_without_gui_wait(self) -> None:
        from profile.ui.profile_order_page import ProfileOrderPageBase

        cleanup_source = inspect.getsource(ProfileOrderPageBase.cleanup)

        self.assertIn(
            '_order_load_runtime.stop(\n            blocking=False,',
            cleanup_source,
        )
        self.assertIn(
            '_order_move_runtime.stop(\n            blocking=False,',
            cleanup_source,
        )

    def test_control_page_cleanup_stops_refresh_workers_without_gui_wait(self) -> None:
        from presets.ui.control.control_page_shared import cleanup_control_page_subscriptions

        cleanup_source = inspect.getsource(cleanup_control_page_subscriptions)

        self.assertIn(
            'top_summary_runtime.stop(\n            blocking=False,',
            cleanup_source,
        )
        self.assertIn(
            'program_settings_load_runtime.stop(\n            blocking=False,',
            cleanup_source,
        )
        self.assertIn(
            'program_settings_save_runtime.stop(\n            blocking=False,',
            cleanup_source,
        )


if __name__ == "__main__":
    unittest.main()
