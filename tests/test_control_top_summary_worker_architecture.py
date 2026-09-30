from __future__ import annotations

import inspect
import unittest

import presets.ui.control.control_page_shared as control_page_shared
from presets.ui.control.zapret2.page import Zapret2ModeControlPage
import ui.page_deps.presets as preset_page_deps


class ControlTopSummaryWorkerArchitectureTests(unittest.TestCase):

    def test_page_deps_wraps_summary_readers_inside_worker_factory(self) -> None:
        source = inspect.getsource(preset_page_deps.build_control_page_kwargs)

        self.assertIn("create_top_summary_worker", source)
        self.assertIn("get_selected_source_preset_display", source)
        self.assertIn("get_enabled_profile_count_snapshot", source)


    def test_page_deps_wraps_additional_settings_setters_inside_worker_factory(self) -> None:
        source = inspect.getsource(preset_page_deps.build_control_page_kwargs)

        self.assertIn("create_additional_settings_save_worker", source)
        self.assertIn("set_discord_restart_setting", source)
        self.assertIn("set_wssize_enabled", source)
        self.assertIn("set_debug_log_enabled", source)


if __name__ == "__main__":
    unittest.main()
