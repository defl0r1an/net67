from __future__ import annotations

import inspect
import threading
import time
import unittest


class WinwsRuntimeUiThreadContractTests(unittest.TestCase):


    def test_gui_runtime_callbacks_only_read_published_state(self) -> None:
        from winws_runtime.runtime import lifecycle_feedback, restart_flow, status_flow

        callback_source = "\n".join(
            (
                inspect.getsource(status_flow),
                inspect.getsource(lifecycle_feedback),
                inspect.getsource(restart_flow.process_pending_presets_switch),
                inspect.getsource(restart_flow.process_pending_restart_request),
            )
        )

        for forbidden in (
            "runner_factory",
            "get_runner_state_snapshot",
            "has_residual_processes(",
            "refresh_now(",
            "process_probe",
            "get_launch_snapshot(",
        ):
            self.assertNotIn(forbidden, callback_source)
        self.assertIn("_runtime_service().snapshot()", callback_source)

    def test_start_request_is_prepared_inside_worker(self) -> None:
        from winws_runtime.runtime import start_flow
        from winws_runtime.runtime.start_workers import PresetLaunchStartWorker

        gui_source = inspect.getsource(start_flow)
        worker_source = inspect.getsource(PresetLaunchStartWorker.run)

        self.assertNotIn("prepare_start_request(", gui_source)
        self.assertNotIn("get_launch_snapshot(", gui_source)
        self.assertIn("prepare_start_request(", worker_source)
        self.assertIn("self._prepare_request", worker_source)

    def test_startup_and_ui_dependencies_do_not_probe_processes_or_read_launch_settings(self) -> None:
        from main import (
            post_startup_profile_warmup,
            post_startup_user_presets_warmup,
            window_startup,
        )
        from ui.page_deps import system
        from winws_runtime.runtime import autostart, startup

        source = "\n".join(
            inspect.getsource(module)
            for module in (
                autostart,
                startup,
                window_startup,
                post_startup_profile_warmup,
                post_startup_user_presets_warmup,
                system,
            )
        )

        for forbidden in (
            "get_strategy_launch_method(",
            "is_any_running(",
            "has_residual_processes(",
            "get_launch_snapshot(",
            "get_canonical_winws_process_pids(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("runtime_feature.is_running()", source)


if __name__ == "__main__":
    unittest.main()
