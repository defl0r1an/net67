from __future__ import annotations

import inspect
import sys
import tempfile
import types
import unittest
import weakref
from ctypes import addressof
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class StartupRuntimeSetupTests(unittest.TestCase):
    def test_post_interactive_startup_steps_have_no_fixed_gap(self) -> None:
        from main import startup_coordinator

        self.assertEqual(startup_coordinator.STARTUP_STEP_GAP_MS, 0)

    def test_phase_two_completion_dispatches_deferred_autostart(self) -> None:
        from main import startup_coordinator
        from main.startup_coordinator import StartupCoordinator

        class Runtime:
            def __init__(self) -> None:
                self.autostart_calls: list[str | None] = []
                self.calls: list[str] = []

            def init_launch_runtime_api(self) -> None:
                self.calls.append("runtime_api")

            def init_launch_runtime(self) -> None:
                self.calls.append("runtime")

            def init_process_monitor(self) -> None:
                self.calls.append("process_monitor")

            def init_core_startup(self) -> None:
                self.calls.append("core_startup")

            def snapshot(self):
                return SimpleNamespace(launch_method="zapret2_mode")

            def start_autostart(self, launch_method: str | None = None) -> None:
                self.calls.append("autostart")
                self.autostart_calls.append(launch_method)

        runtime = Runtime()
        window_shell = SimpleNamespace(
            start_in_tray=False,
            set_status=Mock(),
            mark_startup_interactive=Mock(),
            mark_startup_core_ready=Mock(),
            mark_startup_post_init_done=Mock(),
            init_theme_manager=Mock(side_effect=lambda: runtime.calls.append("theme")),
        )
        tray = SimpleNamespace(
            init=Mock(),
            is_initialized=Mock(return_value=False),
        )
        coordinator = StartupCoordinator(
            runtime_feature=runtime,
            tray_feature=tray,
            window_shell=window_shell,
            log_startup_metric=Mock(),
            migrate_gui_autostart=Mock(return_value=False),
        )
        scheduled: list[tuple[int, object]] = []
        timer_delays: list[int] = []
        background_targets: list[object] = []

        with (
            patch.object(startup_coordinator, "run_queued", side_effect=lambda callback: scheduled.append((0, callback))),
            patch.object(
                startup_coordinator.QTimer,
                "singleShot",
                side_effect=lambda delay_ms, callback: (
                    timer_delays.append(int(delay_ms)),
                    scheduled.append((int(delay_ms), callback)),
                ),
            ),
            patch.object(
                startup_coordinator,
                "start_daemon_thread",
                side_effect=lambda name, target: background_targets.append((name, target)),
            ),
        ):
            coordinator.run_async_init()
            self.assertEqual(runtime.calls, [])
            while scheduled:
                _delay_ms, callback = scheduled.pop(0)
                callback()
            step_targets = [t for name, t in background_targets if name.startswith("StartupStep-")]
            self.assertEqual(len(step_targets), 1)
            self.assertIn("GuiAutostartMigration", [name for name, _t in background_targets])
            step_targets[0]()
            while scheduled:
                _delay_ms, callback = scheduled.pop(0)
                callback()

        self.assertTrue(coordinator._post_init_scheduled)
        self.assertEqual(runtime.autostart_calls, ["zapret2_mode"])
        metric_names = [call.args[0] for call in coordinator.log_startup_metric.call_args_list]
        for metric_name in (
            "StartupStepLaunchRuntimeApi",
            "StartupStepLaunchRuntime",
            "StartupStepProcessMonitor",
            "StartupStepCoreStartup",
            "StartupStepStartupCoreReady",
        ):
            self.assertIn(metric_name, metric_names)
        window_shell.mark_startup_interactive.assert_not_called()
        window_shell.mark_startup_post_init_done.assert_called_once()
        self.assertIn(startup_coordinator.STARTUP_STEP_GAP_MS, timer_delays)
        self.assertIn(startup_coordinator.STARTUP_DPI_AUTOSTART_DELAY_MS, timer_delays)
        self.assertEqual(
            runtime.calls,
            [
                "runtime_api",
                "runtime",
                "autostart",
                "theme",
                "process_monitor",
                "core_startup",
            ],
        )

    def test_visual_and_background_startup_steps_run_after_deferred_autostart(self) -> None:
        from main import startup_coordinator
        from main.startup_coordinator import StartupCoordinator

        class Runtime:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def init_launch_runtime_api(self) -> None:
                self.calls.append("runtime_api")

            def init_launch_runtime(self) -> None:
                self.calls.append("runtime")

            def init_process_monitor(self) -> None:
                self.calls.append("process_monitor")

            def init_core_startup(self) -> None:
                self.calls.append("core_startup")

            def snapshot(self):
                return SimpleNamespace(launch_method="zapret2_mode")

            def start_autostart(self, launch_method: str | None = None) -> None:
                self.calls.append(f"autostart:{launch_method}")

        runtime = Runtime()
        window_shell = SimpleNamespace(
            start_in_tray=False,
            set_status=Mock(),
            mark_startup_interactive=Mock(),
            mark_startup_core_ready=Mock(),
            mark_startup_post_init_done=Mock(),
            init_theme_manager=Mock(side_effect=lambda: runtime.calls.append("theme")),
        )
        tray = SimpleNamespace(
            init=Mock(),
            is_initialized=Mock(return_value=False),
        )
        coordinator = StartupCoordinator(
            runtime_feature=runtime,
            tray_feature=tray,
            window_shell=window_shell,
            log_startup_metric=Mock(),
            migrate_gui_autostart=Mock(return_value=False),
        )
        scheduled: list[tuple[int, object]] = []
        background_targets: list[object] = []

        with (
            patch.object(startup_coordinator, "run_queued", side_effect=lambda callback: scheduled.append((0, callback))),
            patch.object(
                startup_coordinator.QTimer,
                "singleShot",
                side_effect=lambda delay_ms, callback: scheduled.append((int(delay_ms), callback)),
            ),
            patch.object(
                startup_coordinator,
                "start_daemon_thread",
                side_effect=lambda name, target: background_targets.append((name, target)),
                create=True,
            ),
        ):
            coordinator.run_async_init()
            while scheduled:
                _delay_ms, callback = scheduled.pop(0)
                callback()

            self.assertEqual(
                runtime.calls,
                ["runtime_api", "runtime", "autostart:zapret2_mode", "theme", "process_monitor"],
            )
            step_targets = [t for name, t in background_targets if name.startswith("StartupStep-")]
            self.assertEqual(len(step_targets), 1)
            window_shell.mark_startup_post_init_done.assert_called_once()

            step_targets[0]()
            while scheduled:
                _delay_ms, callback = scheduled.pop(0)
                callback()

        self.assertEqual(
            runtime.calls,
            [
                "runtime_api",
                "runtime",
                "autostart:zapret2_mode",
                "theme",
                "process_monitor",
                "core_startup",
            ],
        )
        window_shell.mark_startup_post_init_done.assert_called_once()

    def test_deferred_autostart_does_not_wait_for_core_startup_file_check(self) -> None:
        from main import startup_coordinator
        from main.startup_coordinator import StartupCoordinator

        class Runtime:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def init_launch_runtime_api(self) -> None:
                self.calls.append("runtime_api")

            def init_launch_runtime(self) -> None:
                self.calls.append("runtime")

            def init_process_monitor(self) -> None:
                self.calls.append("process_monitor")

            def init_core_startup(self) -> None:
                self.calls.append("core_startup")

            def snapshot(self):
                return SimpleNamespace(launch_method="zapret2_mode")

            def start_autostart(self, launch_method: str | None = None) -> None:
                self.calls.append(f"autostart:{launch_method}")

        runtime = Runtime()
        window_shell = SimpleNamespace(
            start_in_tray=False,
            set_status=Mock(),
            mark_startup_interactive=Mock(),
            mark_startup_core_ready=Mock(),
            mark_startup_post_init_done=Mock(),
            init_theme_manager=Mock(side_effect=lambda: runtime.calls.append("theme")),
        )
        tray = SimpleNamespace(init=Mock(), is_initialized=Mock(return_value=False))
        coordinator = StartupCoordinator(
            runtime_feature=runtime,
            tray_feature=tray,
            window_shell=window_shell,
            log_startup_metric=Mock(),
            migrate_gui_autostart=Mock(return_value=False),
        )
        scheduled: list[tuple[int, object]] = []
        background_targets: list[object] = []

        with (
            patch.object(startup_coordinator, "run_queued", side_effect=lambda callback: scheduled.append((0, callback))),
            patch.object(
                startup_coordinator.QTimer,
                "singleShot",
                side_effect=lambda delay_ms, callback: scheduled.append((int(delay_ms), callback)),
            ),
            patch.object(
                startup_coordinator,
                "start_daemon_thread",
                side_effect=lambda name, target: background_targets.append((name, target)),
                create=True,
            ),
        ):
            coordinator.run_async_init()
            while scheduled:
                _delay_ms, callback = scheduled.pop(0)
                callback()

        self.assertEqual(
            runtime.calls,
            [
                "runtime_api",
                "runtime",
                "autostart:zapret2_mode",
                "theme",
                "process_monitor",
            ],
        )
        step_targets = [t for name, t in background_targets if name.startswith("StartupStep-")]
        self.assertEqual(len(step_targets), 1)
        window_shell.mark_startup_post_init_done.assert_called_once()

        step_targets[0]()

        self.assertEqual(runtime.calls[-1], "core_startup")


    def test_main_defers_late_bootstrap_until_qt_event_loop_runs(self) -> None:
        from main import entry
        import main.application_controller as application_controller_module
        import main.window as window_module
        import main.windows_session_shutdown as shutdown_module

        calls: list[str] = []
        scheduled: list[tuple[int, object]] = []
        timer_delays: list[int] = []
        app_runtime = object()

        class Signal:
            def __init__(self) -> None:
                self._callbacks: list[object] = []

            def connect(self, callback) -> None:
                self._callbacks.append(callback)

            def emit(self, value: str = "") -> None:
                for callback in list(self._callbacks):
                    callback(value)

        startup_signal = Signal()
        window = SimpleNamespace(
            startup_state=SimpleNamespace(interactive_logged=False),
            startup_interactive_ready=startup_signal,
        )

        class App:
            def exec(self) -> int:
                calls.append("app.exec")
                while scheduled:
                    _delay, callback = scheduled.pop(0)
                    callback()
                calls.append("startup_interactive.emit")
                window.startup_state.interactive_logged = True
                startup_signal.emit("ui_ready")
                while scheduled:
                    _delay, callback = scheduled.pop(0)
                    callback()
                return 0

        class Controller:
            def __init__(self, *, window_cls, start_in_tray) -> None:
                calls.append("controller.init")
                self.app_runtime = app_runtime
                self.window_state_actions = object()

            def create_window(self):
                calls.append("create_window")
                return window

        class Bridge:
            def __init__(self, target_window) -> None:
                pass

            def start(self) -> bool:
                calls.append("bridge.start")
                return True

        with (
            patch.object(entry, "require_packaged_application"),
            patch.object(entry, "shell_bootstrap", return_value=False),
            patch.object(entry, "application_bootstrap", return_value=App()),
            patch.object(entry, "is_qt_event_diagnostic_enabled", return_value=False),
            patch.object(application_controller_module, "ApplicationController", Controller),
            patch.object(window_module, "LupiDPIApp", object()),
            patch.object(shutdown_module, "connect_windows_session_shutdown", side_effect=lambda *_: calls.append("shutdown.hook")),
            patch.object(entry, "_configure_window_appearance", side_effect=lambda *_: calls.append("appearance")),
            patch("startup.show_window_bridge.ShowWindowBridge", Bridge),
            patch.object(
                entry.QTimer,
                "singleShot",
                side_effect=lambda delay, callback: (
                    timer_delays.append(int(delay)),
                    calls.append("schedule.late_bootstrap"),
                    scheduled.append((delay, callback)),
                ),
            ),
            patch.object(entry, "_build_application_post_startup_deps", side_effect=lambda **_: calls.append("build_post_startup_deps") or object()),
            patch.object(entry, "_install_post_startup_tasks", side_effect=lambda *_: calls.append("install_post_startup")),
        ):
            with self.assertRaises(SystemExit):
                entry.main()

        self.assertEqual(timer_delays[0], 0)
        self.assertLess(calls.index("schedule.late_bootstrap"), calls.index("app.exec"))
        self.assertLess(calls.index("app.exec"), calls.index("install_post_startup"))
        self.assertLess(calls.index("startup_interactive.emit"), calls.index("install_post_startup"))
        self.assertLess(calls.index("appearance"), calls.index("install_post_startup"))
        self.assertLess(calls.index("bridge.start"), calls.index("install_post_startup"))

    def test_post_startup_install_is_bound_to_interactive_ready(self) -> None:
        from main import entry

        class Signal:
            def __init__(self) -> None:
                self._callbacks: list[object] = []

            def connect(self, callback) -> None:
                self._callbacks.append(callback)

            def emit(self, value: str = "") -> None:
                for callback in list(self._callbacks):
                    callback(value)

        signal = Signal()
        window = SimpleNamespace(
            startup_state=SimpleNamespace(interactive_logged=False),
            startup_interactive_ready=signal,
        )
        deps = object()
        scheduled: list[tuple[int, object]] = []
        installed: list[object] = []

        with (
            patch.object(
                entry.QTimer,
                "singleShot",
                side_effect=lambda delay, callback: scheduled.append((int(delay), callback)),
            ),
            patch.object(entry, "_install_post_startup_tasks", side_effect=lambda value: installed.append(value)),
        ):
            entry._install_post_startup_tasks_after_interactive(window, deps)
            self.assertEqual(installed, [])
            self.assertEqual(scheduled, [])

            window.startup_state.interactive_logged = True
            signal.emit("ui_ready")
            self.assertEqual(installed, [])
            self.assertEqual(scheduled[0][0], 0)
            scheduled.pop(0)[1]()

        self.assertEqual(installed, [deps])

    def test_post_startup_deps_are_built_after_interactive_ready(self) -> None:
        from main import entry

        class Signal:
            def __init__(self) -> None:
                self._callbacks: list[object] = []

            def connect(self, callback) -> None:
                self._callbacks.append(callback)

            def emit(self, value: str = "") -> None:
                for callback in list(self._callbacks):
                    callback(value)

        signal = Signal()
        window = SimpleNamespace(
            startup_state=SimpleNamespace(interactive_logged=False),
            startup_interactive_ready=signal,
        )
        built: list[str] = []
        installed: list[object] = []
        scheduled: list[tuple[int, object]] = []

        def build_deps():
            built.append("deps")
            return "deps"

        with (
            patch.object(
                entry.QTimer,
                "singleShot",
                side_effect=lambda delay, callback: scheduled.append((int(delay), callback)),
            ),
            patch.object(entry, "_install_post_startup_tasks", side_effect=lambda deps: installed.append(deps)),
        ):
            entry._install_post_startup_tasks_after_interactive(window, build_deps)
            self.assertEqual(built, [])
            self.assertEqual(installed, [])

            window.startup_state.interactive_logged = True
            signal.emit("ui_ready")
            self.assertEqual(built, ["deps"])
            self.assertEqual(installed, [])

            scheduled.pop(0)[1]()

        self.assertEqual(installed, ["deps"])

    def test_qt_scroll_style_is_installed_after_interactive_ready(self) -> None:
        from main import entry

        class Signal:
            def __init__(self) -> None:
                self._callbacks: list[object] = []

            def connect(self, callback) -> None:
                self._callbacks.append(callback)

            def emit(self, value: str = "") -> None:
                for callback in list(self._callbacks):
                    callback(value)

        signal = Signal()
        window = SimpleNamespace(
            startup_state=SimpleNamespace(interactive_logged=False),
            startup_interactive_ready=signal,
        )
        app = object()
        installed: list[object] = []
        scheduled: list[tuple[int, object]] = []

        with (
            patch.object(
                entry.QTimer,
                "singleShot",
                side_effect=lambda delay, callback: scheduled.append((int(delay), callback)),
            ),
            patch.object(entry, "_install_qt_scroll_style", side_effect=lambda value: installed.append(value)),
        ):
            entry._install_qt_scroll_style_after_interactive(window, app)
            self.assertEqual(installed, [])
            self.assertEqual(scheduled, [])

            window.startup_state.interactive_logged = True
            signal.emit("ui_ready")
            self.assertEqual(installed, [])
            self.assertGreaterEqual(scheduled[0][0], 1500)

            scheduled.pop(0)[1]()

        self.assertEqual(installed, [app])

    def test_entry_keeps_post_startup_imports_out_of_top_level(self) -> None:
        import inspect
        from main import entry

        source = inspect.getsource(entry)
        top_level = source.split("def _build_application_post_startup_deps", 1)[0]

        self.assertNotIn("from startup.show_window_bridge import ShowWindowBridge", top_level)
        self.assertNotIn("from main.application_post_startup import build_application_post_startup_deps", top_level)
        self.assertNotIn("from main.post_startup import install_post_startup_tasks", top_level)

    def test_post_startup_module_keeps_task_imports_lazy(self) -> None:
        import inspect
        from main import post_startup

        source = inspect.getsource(post_startup)
        top_level = source.split("def install_startup_checks", 1)[0]

        self.assertNotIn("from main.post_startup_checks import", top_level)
        self.assertNotIn("from main.post_startup_dns_warmup import", top_level)
        self.assertNotIn("from main.post_startup_page_warmup import", top_level)
        self.assertNotIn("from main.post_startup_user_presets_warmup import", top_level)
        self.assertNotIn("from main.post_startup_update import", top_level)

    def test_startup_audit_is_disabled_by_default_after_temporary_diagnostics(self) -> None:
        from main import startup_audit

        with patch.dict("os.environ", {}, clear=True), patch.object(sys, "argv", ["Zapret.exe"]):
            self.assertFalse(startup_audit.is_startup_audit_enabled())

        with patch.dict("os.environ", {"ZAPRET_STARTUP_AUDIT": "0"}, clear=True):
            self.assertFalse(startup_audit.is_startup_audit_enabled())

        with patch.dict("os.environ", {}, clear=True), patch.object(sys, "argv", ["Zapret.exe", "--startup-audit"]):
            self.assertTrue(startup_audit.is_startup_audit_enabled())

    def test_startup_metric_includes_memory_when_audit_is_enabled(self) -> None:
        from main import runtime_state

        with (
            patch("log.log.log") as log_fn,
            patch("main.startup_audit.is_startup_audit_enabled", return_value=True),
            patch("main.startup_audit.process_memory_details", return_value="rss=123.4MB"),
        ):
            runtime_state.log_startup_metric("DemoMetric", "details")

        logged_text = str(log_fn.call_args.args[0])
        self.assertIn("DemoMetric", logged_text)
        self.assertIn("details", logged_text)
        self.assertIn("rss=123.4MB", logged_text)

    def test_startup_threading_reports_audit_boundaries(self) -> None:
        from main import post_startup_threading

        calls: list[str] = []

        with (
            patch.object(post_startup_threading.startup_audit, "is_startup_audit_enabled", return_value=True),
            patch.object(post_startup_threading.startup_audit, "audit_task_begin", side_effect=lambda name, kind: calls.append(f"begin:{kind}:{name}") or 11),
            patch.object(post_startup_threading.startup_audit, "audit_task_end", side_effect=lambda task_id, name, kind: calls.append(f"end:{kind}:{name}:{task_id}")),
        ):
            post_startup_threading._run_audited_target("DemoWorker", lambda: calls.append("target"))

        self.assertEqual(calls, ["begin:thread:DemoWorker", "target", "end:thread:DemoWorker:11"])

    def test_startup_threading_uses_separate_serial_queues_per_subsystem(self) -> None:
        import threading
        import time
        from main import post_startup_threading

        queue_suffix = str(time.monotonic_ns())
        calls: list[str] = []
        first_started = threading.Event()
        release_first = threading.Event()
        second_done = threading.Event()
        other_done = threading.Event()

        def first_hosts_task() -> None:
            calls.append("hosts:first:start")
            first_started.set()
            release_first.wait(2)
            calls.append("hosts:first:end")

        def second_hosts_task() -> None:
            calls.append("hosts:second")
            second_done.set()

        def profile_task() -> None:
            calls.append("profile:first")
            other_done.set()

        post_startup_threading.enqueue_subsystem_task(
            f"hosts-{queue_suffix}",
            "HostsWarmup-1",
            first_hosts_task,
        )
        post_startup_threading.enqueue_subsystem_task(
            f"hosts-{queue_suffix}",
            "HostsWarmup-2",
            second_hosts_task,
        )
        post_startup_threading.enqueue_subsystem_task(
            f"profile-{queue_suffix}",
            "ProfileWarmup-1",
            profile_task,
        )

        self.assertTrue(first_started.wait(1.0))
        self.assertTrue(other_done.wait(1.0))
        self.assertFalse(second_done.wait(0.05))
        self.assertIn("profile:first", calls)

        release_first.set()
        self.assertTrue(second_done.wait(1.0))
        self.assertLess(calls.index("hosts:first:start"), calls.index("hosts:first:end"))
        self.assertLess(calls.index("hosts:first:end"), calls.index("hosts:second"))
        self.assertLess(calls.index("profile:first"), calls.index("hosts:first:end"))

    def test_startup_audit_summary_installed_by_post_startup_tasks(self) -> None:
        from main import post_startup

        deps = SimpleNamespace(
            startup_host=object(),
            hosts_feature=object(),
            profile_feature=object(),
            dns_feature=object(),
            notify=Mock(),
            notify_many=Mock(),
            set_status=Mock(),
            log_startup_metric=Mock(),
            start_proxy_if_enabled_async=Mock(),
            startup_lists_check=Mock(),
            install_tray_post_startup=Mock(),
            updater_feature=object(),
            premium_feature=None,
            logs_feature=None,
            presets_feature=None,
        )

        with (
            patch.object(post_startup, "install_startup_checks"),
            patch.object(post_startup, "install_after_interactive_import_warmup"),
            patch.object(post_startup, "install_secondary_page_warmup"),
            patch.object(post_startup, "install_user_preset_contract_migration"),
            patch.object(post_startup, "install_remote_presets_sync"),
            patch.object(post_startup, "install_deferred_maintenance"),
            patch.object(post_startup, "install_telegram_proxy_startup"),
            patch.object(post_startup, "install_telegram_proxy_page_warmup"),
            patch.object(post_startup, "install_lists_check"),
            patch.object(post_startup, "install_dns_address_migration"),
            patch.object(post_startup, "install_hosts_applied_selection_refresh"),
            patch.object(post_startup, "install_onboarding_tour"),
            patch.object(post_startup, "install_dns_page_data_warmup"),
            patch.object(post_startup, "install_hosts_page_warmup"),
            patch.object(post_startup, "install_profile_warmup"),
            patch.object(post_startup, "install_update_check"),
            patch.object(post_startup, "install_cpu_diagnostic"),
            patch.object(post_startup, "install_qt_event_diagnostic_probe"),
            patch.object(post_startup, "install_global_exception_handler"),
            patch.object(post_startup, "install_startup_audit") as install_audit,
        ):
            post_startup.install_post_startup_tasks(deps)

        install_audit.assert_called_once()

    def test_startup_log_contract_accepts_ui_before_runtime_order(self) -> None:
        from main.startup_log_contract import validate_startup_log_contract

        result = validate_startup_log_contract(
            "\n".join(
                (
                    "[12:00:00] [⏱ STARTUP] ⏱ Startup StartupTTFF: 1000ms | first showEvent",
                    "[12:00:01] [⏱ STARTUP] ⏱ Startup StartupInteractive: 1200ms | ui_ready",
                    "[12:00:01] [⏱ STARTUP] ⏱ Startup StartupRuntimeInitQueued: 1450ms | 25ms gaps",
                    "[12:00:02] [⏱ STARTUP] ⏱ Startup StartupCoreReady: 1800ms | startup_coordinator",
                    "[12:00:02] [⏱ STARTUP] ⏱ Startup StartupPostInit: 1900ms | post_init_scheduled",
                    "[12:00:02] [⏱ STARTUP] ⏱ Startup StartupPostInitDeferredStart: 2300ms | zapret2_mode",
                    "[12:00:02] [⏱ STARTUP] ⏱ Startup StartupNetworkDataWarmupQueued: 2400ms | 1200ms after interactive",
                    "[12:00:02] [⏱ STARTUP] ⏱ Startup StartupSidebarSearchQueued: 2500ms | 1000ms after interactive",
                    "[12:00:02] [⏱ STARTUP] ⏱ Startup StartupHiddenModeNavQueued: 2800ms | 1600ms after interactive",
                )
            )
        )

        self.assertTrue(result.ok, result.errors)

    def test_startup_log_contract_accepts_hidden_tray_start_before_first_show(self) -> None:
        from main.startup_log_contract import validate_startup_log_contract

        result = validate_startup_log_contract(
            "\n".join(
                (
                    "[12:00:01] [⏱ STARTUP] ⏱ Startup StartupInteractive: 5400ms | ui_ready",
                    "[12:00:01] [TRAY] Запуск приложения скрыто в трее",
                    "[12:00:02] [⏱ STARTUP] ⏱ Startup StartupRuntimeInitQueued: 5500ms | 0ms gaps",
                    "[12:00:03] [⏱ STARTUP] ⏱ Startup StartupCoreReady: 6400ms | startup_coordinator",
                    "[12:00:03] [⏱ STARTUP] ⏱ Startup StartupPostInit: 6500ms | post_init_scheduled",
                    "[12:05:49] [⏱ STARTUP] ⏱ Startup StartupTTFF: 352855ms | first showEvent",
                )
            )
        )

        self.assertTrue(result.ok, result.errors)

    def test_startup_log_contract_rejects_runtime_before_interactive(self) -> None:
        from main.startup_log_contract import validate_startup_log_contract

        result = validate_startup_log_contract(
            "\n".join(
                (
                    "[12:00:00] [⏱ STARTUP] ⏱ Startup StartupTTFF: 1000ms | first showEvent",
                    "[12:00:01] [⏱ STARTUP] ⏱ Startup StartupRuntimeInitQueued: 1100ms | 25ms gaps",
                    "[12:00:01] [⏱ STARTUP] ⏱ Startup StartupInteractive: 1300ms | ui_ready",
                )
            )
        )

        self.assertFalse(result.ok)
        self.assertTrue(any("StartupRuntimeInitQueued" in error for error in result.errors))

    def test_startup_log_contract_rejects_gui_page_warmup_during_startup(self) -> None:
        from main.startup_log_contract import validate_startup_log_contract

        result = validate_startup_log_contract(
            "\n".join(
                (
                    "[12:00:00] [⏱ STARTUP] ⏱ Startup StartupTTFF: 1000ms | first showEvent",
                    "[12:00:01] [⏱ STARTUP] ⏱ Startup StartupInteractive: 1300ms | ui_ready",
                    "[12:00:10] [⏱ UI] ⏱ UiMetric: scope=page name=NETWORK stage=warmup elapsed=237ms",
                )
            )
        )

        self.assertFalse(result.ok)
        self.assertTrue(any("GUI-прогрев страницы" in error for error in result.errors))

    def test_startup_log_contract_rejects_startup_page_warmup_queue(self) -> None:
        from main.startup_log_contract import validate_startup_log_contract

        result = validate_startup_log_contract(
            "\n".join(
                (
                    "[12:00:00] [⏱ STARTUP] ⏱ Startup StartupTTFF: 1000ms | first showEvent",
                    "[12:00:01] [⏱ STARTUP] ⏱ Startup StartupInteractive: 1300ms | ui_ready",
                    "[12:00:10] [⏱ STARTUP] ⏱ Startup StartupPageNetworkWarmupQueued: 9000ms | NETWORK",
                )
            )
        )

        self.assertFalse(result.ok)
        self.assertTrue(any("Во время запуска можно греть только данные" in error for error in result.errors))

    def test_startup_runtime_step_gap_stays_short_after_interactive(self) -> None:
        from main import startup_coordinator

        self.assertLessEqual(startup_coordinator.STARTUP_STEP_GAP_MS, 8)

    def test_dns_feature_has_warmup_but_no_startup_dns_apply(self) -> None:
        from app.feature_facades.dns import build_dns_feature

        dns_feature = build_dns_feature()

        self.assertFalse(hasattr(dns_feature, "apply_dns_on_startup_async"))
        self.assertTrue(callable(dns_feature.warm_page_data_cache))
        self.assertTrue(callable(dns_feature.consume_warmed_page_data))

    def test_window_startup_metrics_are_imported_for_interactive_ready(self) -> None:
        import main.window_startup as window_startup

        class Signal:
            def __init__(self) -> None:
                self.emitted: list[str] = []

            def emit(self, value: str) -> None:
                self.emitted.append(value)

        window = object.__new__(window_startup.WindowStartupMixin)
        window.startup_state = SimpleNamespace(
            interactive_logged=False,
            interactive_ms=None,
            ttff_ms=None,
        )
        window.startup_interactive_ready = Signal()

        with patch.object(window_startup, "emit_startup_metric") as metric:
            window.mark_startup_interactive("test_ready")

        metric.assert_called_once_with("StartupInteractive", "test_ready")
        self.assertEqual(window.startup_interactive_ready.emitted, ["test_ready"])

    def test_initial_manual_launch_state_keeps_runtime_buttons_preparing(self) -> None:
        from app.feature_facades.runtime_parts import RuntimeObjects
        from winws_runtime.state import LaunchRuntimeService

        _ = RuntimeObjects
        state = LaunchRuntimeService.build_initial_ui_state(
            launch_method="zapret2_mode",
            dpi_autostart_enabled=False,
            launch_supported=True,
        )

        self.assertEqual(state.launch_phase, "stopped")
        self.assertTrue(state.launch_busy)
        self.assertIn("Подготов", state.launch_busy_text)

    def test_initial_autostart_state_uses_autostart_pending_without_extra_busy_flag(self) -> None:
        from app.feature_facades.runtime_parts import RuntimeObjects
        from winws_runtime.state import LaunchRuntimeService

        _ = RuntimeObjects
        state = LaunchRuntimeService.build_initial_ui_state(
            launch_method="zapret2_mode",
            dpi_autostart_enabled=True,
            launch_supported=True,
        )

        self.assertEqual(state.launch_phase, "autostart_pending")
        self.assertFalse(state.launch_busy)
        self.assertEqual(state.launch_busy_text, "")

    def test_runtime_init_clears_startup_button_preparation(self) -> None:
        from app.feature_facades.runtime_parts import RuntimeCommandPort

        runtime_object = object()
        runtime_service = SimpleNamespace(set_busy=Mock())
        owner = SimpleNamespace(
            objects=SimpleNamespace(
                launch_runtime_api=object(),
                launch_runtime=None,
                runtime_service=runtime_service,
            ),
            events=SimpleNamespace(ensure_dispatcher=Mock()),
            ui_port=SimpleNamespace(require_notifications=Mock(return_value=object())),
        )
        commands = RuntimeCommandPort(owner)
        runtime_commands = SimpleNamespace(init_launch_runtime=Mock(return_value=runtime_object))

        with patch.object(RuntimeCommandPort, "_runtime_commands", staticmethod(lambda: runtime_commands)):
            commands.init_launch_runtime()

        self.assertIs(owner.objects.launch_runtime, runtime_object)
        owner.events.ensure_dispatcher.assert_called_once_with()
        runtime_service.set_busy.assert_called_once_with(False)

    def test_runtime_api_init_failure_clears_startup_button_preparation(self) -> None:
        from app.feature_facades.runtime_parts import RuntimeCommandPort

        runtime_service = SimpleNamespace(set_busy=Mock(), mark_start_failed=Mock())
        owner = SimpleNamespace(
            objects=SimpleNamespace(
                launch_runtime_api=None,
                runtime_service=runtime_service,
            ),
        )
        commands = RuntimeCommandPort(owner)
        runtime_commands = SimpleNamespace(init_launch_runtime_api=Mock(side_effect=RuntimeError("boom")))

        with patch.object(RuntimeCommandPort, "_runtime_commands", staticmethod(lambda: runtime_commands)):
            with self.assertRaises(RuntimeError):
                commands.init_launch_runtime_api()

        runtime_service.set_busy.assert_called_once_with(False)
        runtime_service.mark_start_failed.assert_called_once_with("boom")

    def test_runtime_init_failure_clears_startup_button_preparation(self) -> None:
        from app.feature_facades.runtime_parts import RuntimeCommandPort

        runtime_service = SimpleNamespace(set_busy=Mock(), mark_start_failed=Mock())
        owner = SimpleNamespace(
            objects=SimpleNamespace(
                launch_runtime_api=object(),
                launch_runtime=None,
                runtime_service=runtime_service,
            ),
            events=SimpleNamespace(ensure_dispatcher=Mock()),
            ui_port=SimpleNamespace(require_notifications=Mock(return_value=object())),
        )
        commands = RuntimeCommandPort(owner)
        runtime_commands = SimpleNamespace(init_launch_runtime=Mock(side_effect=RuntimeError("boom")))

        with patch.object(RuntimeCommandPort, "_runtime_commands", staticmethod(lambda: runtime_commands)):
            with self.assertRaises(RuntimeError):
                commands.init_launch_runtime()

        runtime_service.set_busy.assert_called_once_with(False)
        runtime_service.mark_start_failed.assert_called_once_with("boom")

    def test_runtime_feature_assembly_uses_light_state_import_before_ui(self) -> None:
        import inspect
        from app.feature_facades import runtime as runtime_feature_module
        from app.feature_facades import runtime_parts

        runtime_source = inspect.getsource(runtime_feature_module)
        runtime_parts_source = inspect.getsource(runtime_parts)

        self.assertIn("from winws_runtime.state import LaunchRuntimeService", runtime_source)
        self.assertNotIn("from winws_runtime.public import LaunchRuntimeService", runtime_source)
        self.assertNotIn("import winws_runtime.public as runtime_commands", runtime_parts_source)


    def test_tray_window_port_defers_heavy_ui_helpers(self) -> None:
        import inspect
        import main.tray_window_port as tray_window_port

        source = inspect.getsource(tray_window_port)
        top_level = source.split("@dataclass", 1)[0]

        self.assertNotIn("from ui.window_adapter import", top_level)
        self.assertNotIn("from ui.popup_menu import", top_level)
        self.assertNotIn("from qfluentwidgets import", top_level)
        self.assertNotIn("from log.log import", top_level)
        self.assertIn("from ui.window_adapter import show_window", inspect.getsource(tray_window_port.TrayWindowPort.show))
        self.assertIn("from ui.popup_menu import exec_popup_menu", inspect.getsource(tray_window_port.TrayWindowPort.exec_popup_menu))

    def test_window_page_actions_defers_heavy_ui_helpers(self) -> None:
        import inspect
        import main.window_page_actions as window_page_actions

        source = inspect.getsource(window_page_actions)
        top_level = source.split("@dataclass", 1)[0]

        self.assertNotIn("from ui.window_adapter import", top_level)
        self.assertNotIn("from ui.workflows.mode import", top_level)
        self.assertNotIn("from ui.window_appearance_state import", top_level)
        self.assertNotIn("from ui.navigation.text_sync import", top_level)
        self.assertNotIn("from main.window_page_presenters import", top_level)
        self.assertIn("from ui.window_adapter import show_page", inspect.getsource(window_page_actions.show_page))
        self.assertIn(
            "from ui.window_appearance_state import on_mica_changed",
            inspect.getsource(window_page_actions.on_mica_changed),
        )


    def test_application_lifecycle_defers_close_cleanup_helpers(self) -> None:
        import inspect
        import main.application_lifecycle as application_lifecycle

        source = inspect.getsource(application_lifecycle)
        top_level = source.split("class ApplicationLifecycle", 1)[0]

        self.assertNotIn("from main.window_lifecycle_cleanup import", top_level)
        self.assertIn(
            "from main.window_lifecycle_cleanup import detach_global_error_notifier",
            inspect.getsource(application_lifecycle.ApplicationLifecycle.run_final_close_cleanup),
        )
        self.assertIn(
            "from main.window_lifecycle_cleanup import",
            inspect.getsource(application_lifecycle.ApplicationLifecycle._cleanup_before_close),
        )

    def test_application_lifecycle_port_defers_close_cleanup_helpers(self) -> None:
        import inspect
        import main.application_lifecycle_port as application_lifecycle_port

        source = inspect.getsource(application_lifecycle_port)
        top_level = source.split("@dataclass", 1)[0]

        self.assertNotIn("from main.window_lifecycle_cleanup import", top_level)
        self.assertIn(
            "from main.window_lifecycle_cleanup import persist_window_geometry",
            inspect.getsource(application_lifecycle_port.ApplicationLifecycleWindowPort.persist_geometry),
        )
        self.assertIn(
            "cleanup_threaded_pages_for_close",
            inspect.getsource(application_lifecycle_port.ApplicationLifecycleWindowPort.cleanup_threaded_pages),
        )

    def test_window_notifications_defers_page_adapter(self) -> None:
        import inspect
        import main.window_notifications_setup as window_notifications_setup

        source = inspect.getsource(window_notifications_setup)
        top_level = source.split("def show_page", 1)[0]

        self.assertNotIn("from ui.window_adapter import", top_level)
        self.assertIn(
            "from ui.window_adapter import show_page",
            inspect.getsource(window_notifications_setup.show_page),
        )


    def test_window_runtime_setup_binds_open_folder_worker_factory(self) -> None:
        import inspect
        import main.window_runtime_setup as window_runtime_setup

        attach_source = inspect.getsource(window_runtime_setup.attach_app_runtime_to_window)
        factory_source = inspect.getsource(window_runtime_setup.create_open_folder_worker)

        self.assertIn("bind_open_folder_worker_factory", attach_source)
        self.assertIn("create_open_folder_worker", attach_source)
        self.assertIn("WindowOpenFolderWorker", factory_source)
        self.assertIn("open_program_folder", factory_source)


    def test_feature_assembly_defers_feature_facades_import(self) -> None:
        import inspect
        import app.feature_assembly as feature_assembly

        source = inspect.getsource(feature_assembly)
        top_level = source.split("@dataclass", 1)[0]

        self.assertNotIn("from app.feature_facades import", top_level)
        self.assertIn(
            "from app.feature_facades.presets import PresetsFeature",
            inspect.getsource(feature_assembly.build_preset_profile_features),
        )
        self.assertIn(
            "from app.feature_facades.profile import ProfileFeature",
            inspect.getsource(feature_assembly.build_preset_profile_features),
        )
        # Фасады импортируются лениво внутри build_app_features через
        # _timed_facade_import, чтобы замерять стоимость каждого импорта.
        build_source = inspect.getsource(feature_assembly.build_app_features)
        self.assertIn("_timed_facade_import", build_source)
        self.assertIn('"blockcheck"', build_source)
        self.assertNotIn(
            "from app.feature_facades import (",
            build_source,
        )
        timed_import_source = inspect.getsource(feature_assembly._timed_facade_import)
        self.assertIn('import_module(f"app.feature_facades.{facade_name}")', timed_import_source)

    def test_page_deps_presets_defers_preset_page_imports(self) -> None:
        import inspect
        import ui.page_deps.presets as page_deps_presets

        source = inspect.getsource(page_deps_presets)
        top_level = source.split("def build_control_page_kwargs", 1)[0]

        # preset_subpage_base тянет ui.fluent_widgets/qtawesome (~200 мс),
        # а этот модуль импортируется до первого показа окна.
        self.assertNotIn("from presets.ui.", top_level)
        self.assertIn(
            "from presets.ui.common.preset_subpage_base import RawPresetRuntimeActions",
            inspect.getsource(page_deps_presets.build_preset_raw_editor_page_kwargs),
        )
        self.assertIn(
            "from presets.ui.common.user_presets_page_runtime import UserPresetsRuntimeActions",
            inspect.getsource(page_deps_presets.build_user_presets_page_kwargs),
        )

    def test_app_features_defers_feature_facades_imports_to_type_checking(self) -> None:
        import inspect
        import app.features as app_features

        source = inspect.getsource(app_features)
        before_type_checking = source.split("if TYPE_CHECKING:", 1)[0]

        self.assertNotIn("from app.feature_facades import", before_type_checking)
        self.assertIn("if TYPE_CHECKING:", source)
        self.assertIn("from app.feature_facades import", source)

    def test_window_state_actions_defers_appearance_state_helpers(self) -> None:
        import inspect
        import main.window_state_actions as window_state_actions

        source = inspect.getsource(window_state_actions)
        top_level = source.split("@dataclass", 1)[0]

        self.assertNotIn("from ui.window_appearance_state import", top_level)
        self.assertNotIn("from log.log import", top_level)
        self.assertIn(
            "from ui.window_appearance_state import apply_window_opacity_value",
            inspect.getsource(window_state_actions.WindowStateActions.set_window_opacity),
        )

    def test_window_page_deps_setup_defers_ui_root_imports(self) -> None:
        import inspect
        import main.window_page_deps_setup as window_page_deps_setup

        source = inspect.getsource(window_page_deps_setup)
        top_level = source.split("def build_window_page_deps_sources", 1)[0]

        self.assertNotIn("from ui.page_deps.common import", top_level)
        self.assertNotIn("from ui.ui_root import", top_level)
        self.assertNotIn("from ui.window_bootstrap_runtime import", top_level)
        self.assertIn(
            "from ui.page_deps.common import PageDepsSources",
            inspect.getsource(window_page_deps_setup.build_window_page_deps_sources),
        )
        self.assertIn(
            "from ui.ui_root import WindowUiRoot",
            inspect.getsource(window_page_deps_setup.attach_window_ui_root),
        )

    def test_post_startup_host_defers_window_adapter(self) -> None:
        import inspect
        import main.post_startup_host as post_startup_host

        source = inspect.getsource(post_startup_host)
        top_level = source.split("@dataclass", 1)[0]

        self.assertNotIn("from ui.window_adapter import", top_level)
        self.assertIn(
            "from ui.window_adapter import show_page",
            inspect.getsource(post_startup_host.PostStartupHost.show_page),
        )
        self.assertIn(
            "from ui.window_adapter import get_loaded_page",
            inspect.getsource(post_startup_host.PostStartupHost.get_loaded_page),
        )


    def test_external_actions_feature_supports_qt_signal_weakrefs(self) -> None:
        from app.feature_facades.external import ExternalActionsFeature

        feature = ExternalActionsFeature()

        self.assertIs(weakref.ref(feature)(), feature)


    def test_program_settings_runtime_service_is_created_lazily(self) -> None:
        from app.feature_facades.program_settings import ProgramSettingsFeature, build_program_settings_feature

        created_services: list[object] = []
        runtime_service = object()
        commands = SimpleNamespace(
            refresh_program_settings_snapshot=Mock(return_value="snapshot"),
        )

        def create_runtime_service():
            created_services.append(runtime_service)
            return runtime_service

        with (
            patch.object(ProgramSettingsFeature, "_create_runtime_service", staticmethod(create_runtime_service)),
            patch.object(ProgramSettingsFeature, "_commands", staticmethod(lambda: commands)),
        ):
            feature = build_program_settings_feature()
            self.assertEqual(created_services, [])

            self.assertEqual(feature.refresh_program_settings_snapshot(), "snapshot")

        self.assertEqual(created_services, [runtime_service])
        commands.refresh_program_settings_snapshot.assert_called_once_with(runtime_service)

    def test_program_settings_runtime_service_peeks_warmed_tray_close_mode_without_settings_read(self) -> None:
        from core.runtime.program_settings_runtime_service import (
            TRAY_CLOSE_MODE_MINIMIZE_AND_CLOSE,
            ProgramSettingsRuntimeService,
            store_warmed_tray_close_mode,
        )

        store_warmed_tray_close_mode(TRAY_CLOSE_MODE_MINIMIZE_AND_CLOSE)
        service = ProgramSettingsRuntimeService()
        store_warmed_tray_close_mode(None)

        with patch(
            "settings.store.get_tray_close_mode",
            side_effect=AssertionError("settings read must not happen in click path"),
            create=True,
        ):
            self.assertEqual(service.peek_tray_close_mode(), TRAY_CLOSE_MODE_MINIMIZE_AND_CLOSE)

    def test_startup_checks_are_delayed_after_ui_ready(self) -> None:
        from main import post_startup_checks
        from main.post_startup_checks import install_startup_checks

        class Signal:
            def __init__(self) -> None:
                self._callback = None

            def connect(self, callback) -> None:
                self._callback = callback

            def emit(self, value: str = "") -> None:
                self._callback(value)

        signal = Signal()
        startup_host = SimpleNamespace(
            startup_interactive_ready=signal,
            startup_state=SimpleNamespace(interactive_logged=False),
            is_alive=Mock(return_value=True),
        )
        scheduled: list[tuple[int, object]] = []
        queued_tasks: list[tuple[str, str]] = []

        with (
            patch.object(
                post_startup_checks,
                "schedule_after",
                create=True,
                side_effect=lambda delay_ms, callback: scheduled.append((delay_ms, callback)),
            ),
            patch.object(
                post_startup_checks,
                "enqueue_subsystem_task",
                side_effect=lambda queue, name, target: queued_tasks.append((queue, name)),
            ),
        ):
            install_startup_checks(
                startup_host,
                notify_many=Mock(),
                set_status=Mock(),
                log_startup_metric=Mock(),
            )
            signal.emit("ui_ready")

            self.assertEqual(queued_tasks, [])
            self.assertEqual(len(scheduled), 1)
            self.assertGreaterEqual(scheduled[0][0], 6000)

            scheduled[0][1]()
            self.assertEqual(queued_tasks, [("checks", "StartupChecksWorker")])

    def test_post_init_lists_and_telegram_are_delayed_past_dpi_start(self) -> None:
        from main import post_startup_lists, post_startup_proxy
        from main.post_startup_lists import install_lists_check
        from main.post_startup_proxy import install_telegram_proxy_startup

        class Signal:
            def __init__(self) -> None:
                self._callbacks: list[object] = []

            def connect(self, callback) -> None:
                self._callbacks.append(callback)

            def emit(self, value: str = "") -> None:
                for callback in list(self._callbacks):
                    callback(value)

        signal = Signal()
        startup_host = SimpleNamespace(
            startup_post_init_ready=signal,
            startup_state=SimpleNamespace(post_init_ready=False),
            is_alive=Mock(return_value=True),
        )
        scheduled: list[tuple[str, int, object]] = []

        def schedule_lists(delay_ms, callback):
            scheduled.append(("lists", delay_ms, callback))

        def schedule_proxy(delay_ms, callback):
            scheduled.append(("proxy", delay_ms, callback))

        with (
            patch.object(post_startup_lists, "schedule_after", side_effect=schedule_lists),
            patch.object(post_startup_proxy, "schedule_after", side_effect=schedule_proxy),
            patch.object(post_startup_lists, "enqueue_subsystem_task"),
            patch.object(post_startup_proxy, "enqueue_subsystem_task"),
        ):
            install_lists_check(
                startup_host,
                startup_lists_check=Mock(),
                log_startup_metric=Mock(),
            )
            install_telegram_proxy_startup(
                startup_host,
                start_proxy_if_enabled_async=Mock(),
                log_startup_metric=Mock(),
            )
            signal.emit("post_init")

        delays = {name: delay for name, delay, _callback in scheduled}
        self.assertGreaterEqual(delays["proxy"], 6000)
        self.assertGreaterEqual(delays["lists"], 7000)

    def test_deferred_init_marks_ui_interactive_before_delayed_runtime_continue(self) -> None:
        from PyQt6.QtCore import QTimer
        import main.window_startup as window_startup

        calls: list[str] = []
        scheduled: list[tuple[int, object]] = []

        class Signal:
            def emit(self) -> None:
                calls.append("continue_startup")

        window = object.__new__(window_startup.WindowStartupMixin)
        window.startup_state = SimpleNamespace(deferred_init_started=False)
        window.continue_startup_requested = Signal()
        window.build_ui = Mock(side_effect=lambda *_args: calls.append("build_ui"))
        window.mark_startup_interactive = Mock(side_effect=lambda source: calls.append(f"interactive:{source}"))

        with (
            patch.object(
                QTimer,
                "singleShot",
                side_effect=lambda delay_ms, callback: scheduled.append((delay_ms, callback)),
            ),
            patch.object(window_startup, "emit_startup_metric") as metric,
        ):
            window_startup.WindowStartupMixin._deferred_init(window)

        self.assertEqual(
            calls,
            [
                "build_ui",
                "interactive:ui_ready",
            ],
        )
        self.assertEqual(len(scheduled), 1)
        self.assertLessEqual(scheduled[0][0], 16)
        metric.assert_called_once_with("StartupContinueAfterUiReadyQueued", f"{scheduled[0][0]}ms")

        with patch.object(window_startup, "emit_startup_metric") as metric:
            scheduled[0][1]()
        self.assertEqual(calls[-1], "continue_startup")
        metric.assert_called_once_with("StartupContinueAfterUiReadyDispatch", "continue_startup_requested")
        window.mark_startup_interactive.assert_called_once_with("ui_ready")

    def test_eager_page_creation_does_not_pump_qt_events_before_interactive(self) -> None:
        import inspect
        from app.page_names import PageName
        from ui.page_host import WindowPageHost
        import ui.page_host as page_host_module

        calls: list[str] = []

        class Page:
            def objectName(self) -> str:
                return "Page"

            def setObjectName(self, _name: str) -> None:
                pass

        class Factory:
            page_class_specs = {}

            def create_page(self, page_name):
                calls.append(f"create:{page_name.name}")
                return SimpleNamespace(page=Page(), elapsed_ms=1)

        host = WindowPageHost(SimpleNamespace(get_launch_method=lambda: "zapret2_mode"), Factory())

        with (
            patch.object(page_host_module, "apply_ui_language_to_page", side_effect=lambda *_args: None),
            patch.object(page_host_module, "record_startup_page_init_metric", side_effect=lambda *_args: None),
            patch.object(page_host_module, "log_page_timing", side_effect=lambda *_args, **_kwargs: None),
        ):
            host.create_eager_pages((PageName.ZAPRET2_MODE_CONTROL,))

        self.assertEqual(calls, ["create:ZAPRET2_MODE_CONTROL"])
        source = inspect.getsource(WindowPageHost.create_eager_pages)
        self.assertNotIn("pump_startup_ui", source)

    def test_window_geometry_settings_are_read_once_for_startup_restore(self) -> None:
        from settings import store as settings_store

        data = {
            "window": {
                "x": 10,
                "y": 20,
                "width": 1200,
                "height": 800,
                "maximized": True,
            }
        }

        with patch.object(settings_store, "read_settings", return_value=data) as read_settings:
            geometry = settings_store.get_window_geometry()

        self.assertEqual(
            geometry,
            {
                "x": 10,
                "y": 20,
                "width": 1200,
                "height": 800,
                "maximized": True,
            },
        )
        read_settings.assert_called_once_with()

    def test_window_geometry_runtime_loads_saved_geometry_with_single_settings_read(self) -> None:
        from settings import store as settings_store
        from ui.window_geometry_runtime import SettingsWindowGeometryStore

        data = {
            "x": 10,
            "y": 20,
            "width": 1200,
            "height": 800,
            "maximized": True,
        }

        with patch.object(settings_store, "get_window_geometry", return_value=data) as get_geometry:
            geometry = SettingsWindowGeometryStore().load()

        self.assertEqual(geometry.position, (10, 20))
        self.assertEqual(geometry.size, (1200, 800))
        self.assertTrue(geometry.maximized)
        get_geometry.assert_called_once_with()

    def test_window_lifecycle_uses_canonical_minimum_size_for_restore_guard(self) -> None:
        """Нижняя граница окна берётся из одного места, а не задаётся числами.

        Минимум зависит от режима интерфейса: простой вид показывает одну
        страницу без боковой панели и живёт в окне поменьше. А проверка
        сохранённой геометрии обязана брать самую мягкую границу из двух,
        иначе размер, выставленный в простом виде, при следующем запуске
        сочли бы слишком маленьким и молча отбросили.
        """
        from config.window_metrics import (
            MIN_HEIGHT,
            MIN_WIDTH,
            SIMPLE_MIN_HEIGHT,
            SIMPLE_MIN_WIDTH,
            get_min_size_for_mode,
        )
        from main import window_lifecycle_setup
        from ui.navigation.schema import is_advanced_mode_enabled

        window = SimpleNamespace(
            close_state=object(),
            close_to_tray=Mock(),
            exit_stop_dpi=Mock(),
            exit_keep_dpi=Mock(),
        )
        window.setMinimumSize = Mock()
        features = SimpleNamespace(
            runtime=SimpleNamespace(snapshot=Mock()),
            premium=object(),
            telegram_proxy=object(),
            tray=object(),
            program_settings=SimpleNamespace(
                tray_close_mode=Mock(return_value="normal"),
            ),
            window_geometry=SimpleNamespace(create_geometry_save_worker=Mock()),
        )

        with (
            patch.object(window_lifecycle_setup, "ApplicationLifecycle"),
            patch.object(window_lifecycle_setup, "WindowCloseFlow"),
            patch.object(window_lifecycle_setup, "build_application_lifecycle_window_port", return_value=object()),
            patch.object(window_lifecycle_setup, "WindowGeometryRuntime") as geometry_runtime,
        ):
            window_lifecycle_setup.attach_window_lifecycle(window, features)

        expected_min = get_min_size_for_mode(bool(is_advanced_mode_enabled()))
        window.setMinimumSize.assert_called_once_with(*expected_min)
        geometry_runtime.assert_called_once()
        self.assertEqual(
            geometry_runtime.call_args.kwargs["min_width"],
            min(MIN_WIDTH, SIMPLE_MIN_WIDTH),
        )
        self.assertEqual(
            geometry_runtime.call_args.kwargs["min_height"],
            min(MIN_HEIGHT, SIMPLE_MIN_HEIGHT),
        )


    def test_zapret2_control_initial_state_is_not_delayed_by_startup_gate(self) -> None:
        from presets.ui.control.zapret2.page import Zapret2ModeControlPage

        bind_source = inspect.getsource(Zapret2ModeControlPage.bind_ui_state_store)

        self.assertNotIn("defer_initial_state", bind_source)
        self.assertNotIn("_wait_for_startup_interactive_before_initial_ui_state", bind_source)
        self.assertIn("bind_control_ui_state_store", bind_source)

    def test_zapret2_control_loads_top_summary_through_worker_without_startup_delay(self) -> None:
        from app.state_store import AppUiState
        from presets.ui.control.additional_settings_runtime import create_refresh_runtime
        from presets.ui.control.zapret2.page import Zapret2ModeControlPage

        class WorkerSignal:
            def __init__(self) -> None:
                self._callbacks: list[object] = []

            def connect(self, callback) -> None:
                self._callbacks.append(callback)

            def emit(self, *args) -> None:
                for callback in list(self._callbacks):
                    callback(*args)

        class FakeTopSummaryWorker:
            def __init__(
                self,
                request_id: int,
                get_selected_source_preset_display,
                get_enabled_profile_count_snapshot,
            ) -> None:
                self._request_id = int(request_id)
                self._get_selected_source_preset_display = get_selected_source_preset_display
                self._get_enabled_profile_count_snapshot = get_enabled_profile_count_snapshot
                self.loaded = WorkerSignal()
                self.failed = WorkerSignal()
                self.finished = WorkerSignal()

            def isRunning(self) -> bool:
                return False

            def start(self) -> None:
                preset_text, preset_tooltip = self._get_selected_source_preset_display("zapret2_mode")
                profile_count = self._get_enabled_profile_count_snapshot("zapret2_mode")
                self.loaded.emit(
                    self._request_id,
                    SimpleNamespace(
                        preset_text=preset_text,
                        preset_tooltip=preset_tooltip,
                        profile_count=profile_count,
                    ),
                )
                self.finished.emit()

            def deleteLater(self) -> None:
                pass

        control_page = Zapret2ModeControlPage.__new__(Zapret2ModeControlPage)
        control_page._cleanup_in_progress = False
        control_page._refresh_runtime = create_refresh_runtime()
        control_page._refresh_runtime.additional_settings_dirty = False
        control_page._ui_language = "ru"
        control_page._ui_state_store = None
        control_page._top_summary_profile_retry_count = 0
        control_page._top_summary_profile_retry_pending = False
        control_page.top_summary = SimpleNamespace(
            set_preset=Mock(),
            set_profile_count=Mock(),
            set_premium=Mock(),
        )
        control_page._get_selected_source_preset_display = Mock(return_value=("Preset", "Preset"))
        control_page._get_enabled_profile_count_snapshot = Mock(return_value=2)
        control_page._create_top_summary_worker = (
            lambda request_id, **_kwargs: FakeTopSummaryWorker(
                request_id,
                control_page._get_selected_source_preset_display,
                control_page._get_enabled_profile_count_snapshot,
            )
        )
        control_page.window = Mock(return_value=SimpleNamespace(startup_state=SimpleNamespace(interactive_logged=False)))
        control_page.set_loading = Mock()
        control_page.update_status = Mock()
        control_page.update_strategy = Mock()
        control_page._refresh_last_status_message = Mock()

        Zapret2ModeControlPage._on_ui_state_changed(control_page, AppUiState(), frozenset())

        control_page._get_selected_source_preset_display.assert_called_once()
        control_page._get_enabled_profile_count_snapshot.assert_called_once()
        control_page.top_summary.set_preset.assert_called_with("Preset")
        control_page.top_summary.set_profile_count.assert_called_with(2)

    def test_zapret2_control_retries_top_summary_profile_count_after_warmup(self) -> None:
        from app.state_store import AppUiState
        from presets.ui.control.additional_settings_runtime import create_refresh_runtime
        from presets.ui.control.zapret2 import page as zapret2_page
        from presets.ui.control.zapret2.page import Zapret2ModeControlPage

        scheduled: list[tuple[int, object]] = []
        profile_count = Mock(side_effect=[None, 4])

        class WorkerSignal:
            def __init__(self) -> None:
                self._callbacks: list[object] = []

            def connect(self, callback) -> None:
                self._callbacks.append(callback)

            def emit(self, *args) -> None:
                for callback in list(self._callbacks):
                    callback(*args)

        class FakeTopSummaryWorker:
            def __init__(
                self,
                request_id: int,
                get_selected_source_preset_display,
                get_enabled_profile_count_snapshot,
            ) -> None:
                self._request_id = int(request_id)
                self._get_selected_source_preset_display = get_selected_source_preset_display
                self._get_enabled_profile_count_snapshot = get_enabled_profile_count_snapshot
                self.loaded = WorkerSignal()
                self.failed = WorkerSignal()
                self.finished = WorkerSignal()

            def isRunning(self) -> bool:
                return False

            def start(self) -> None:
                preset_text, preset_tooltip = self._get_selected_source_preset_display("zapret2_mode")
                current_profile_count = self._get_enabled_profile_count_snapshot("zapret2_mode")
                self.loaded.emit(
                    self._request_id,
                    SimpleNamespace(
                        preset_text=preset_text,
                        preset_tooltip=preset_tooltip,
                        profile_count=current_profile_count,
                    ),
                )
                self.finished.emit()

            def deleteLater(self) -> None:
                pass

        control_page = Zapret2ModeControlPage.__new__(Zapret2ModeControlPage)
        control_page._cleanup_in_progress = False
        control_page._ui_language = "ru"
        control_page._ui_state_store = None
        control_page._refresh_runtime = create_refresh_runtime()
        control_page._top_summary_profile_retry_count = 0
        control_page._top_summary_profile_retry_pending = False
        control_page.top_summary = SimpleNamespace(
            set_preset=Mock(),
            set_profile_count=Mock(),
            set_premium=Mock(),
        )
        control_page._get_selected_source_preset_display = Mock(return_value=("Preset", "Preset"))
        control_page._get_enabled_profile_count_snapshot = profile_count
        control_page._create_top_summary_worker = (
            lambda request_id, **_kwargs: FakeTopSummaryWorker(
                request_id,
                control_page._get_selected_source_preset_display,
                control_page._get_enabled_profile_count_snapshot,
            )
        )

        with patch.object(
            zapret2_page.QTimer,
            "singleShot",
            side_effect=lambda delay_ms, callback: scheduled.append((delay_ms, callback)),
        ):
            Zapret2ModeControlPage._refresh_top_summary(control_page, AppUiState())

        control_page.top_summary.set_profile_count.assert_called_with(None)
        self.assertEqual(len(scheduled), 1)
        self.assertGreaterEqual(scheduled[0][0], zapret2_page.TOP_SUMMARY_PROFILE_RETRY_MS)

        scheduled[0][1]()

        control_page.top_summary.set_profile_count.assert_called_with(4)
        self.assertEqual(control_page._top_summary_profile_retry_count, 0)
        self.assertFalse(control_page._top_summary_profile_retry_pending)


    def test_window_page_actions_route_pages_through_adapter(self) -> None:
        from app.page_names import PageName
        from main import window_page_actions
        from main.window_page_actions import build_window_page_actions

        window = SimpleNamespace(
            set_status=Mock(),
            window_notification_center=SimpleNamespace(notify=Mock()),
            request_exit=Mock(),
            open_connection_test=Mock(),
            open_folder=Mock(),
        )
        appearance_actions = SimpleNamespace(
            set_garland_enabled=Mock(),
            set_snowflakes_enabled=Mock(),
            set_window_opacity=Mock(),
        )

        with patch.object(window_page_actions, "show_page", return_value=True) as routed_show_page:
            actions = build_window_page_actions(
                window=window,
                appearance_actions=appearance_actions,
            )
            self.assertTrue(actions.show_page(PageName.ABOUT, allow_internal=True))

        routed_show_page.assert_called_once_with(window, PageName.ABOUT, allow_internal=True)

    def test_profile_setup_change_invalidates_loaded_order_page_without_ensuring_it(self) -> None:
        from app.page_names import PageName
        from main import window_page_presenters

        calls: list[tuple[PageName, str, dict, bool]] = []

        def send_page_command(_window, page_name, command, payload, *, ensure=True):
            calls.append((page_name, command, payload, ensure))
            return True

        with patch.object(window_page_presenters, "send_page_command", side_effect=send_page_command):
            self.assertTrue(
                window_page_presenters.apply_profile_setup_change_for_method(
                    object(),
                    "zapret2_mode",
                    "profile:1",
                    "strategy",
                )
            )

        self.assertEqual(calls[0][0], PageName.ZAPRET2_PRESET_SETUP)
        self.assertEqual(calls[0][1], "profile_setup_changed")
        self.assertFalse(calls[0][3])
        self.assertEqual(calls[1][0], PageName.ZAPRET2_PROFILE_ORDER)
        self.assertEqual(calls[1][1], "profile_order_changed")
        self.assertFalse(calls[1][3])

    def test_window_notifications_route_pages_through_adapter(self) -> None:
        from app.page_names import PageName
        from main import window_notifications_setup
        from main.window_notifications_setup import attach_window_notifications

        captured: dict[str, object] = {}

        class NotificationCenter:
            def __init__(self, *_args, show_page, **_kwargs) -> None:
                captured["show_page"] = show_page
                self.notify = Mock()

            def register_global_error_notifier(self) -> None:
                pass

        window = SimpleNamespace(
            startup_state=object(),
            isVisible=Mock(return_value=True),
            isMinimized=Mock(return_value=False),
            log_startup_metric=Mock(),
        )
        features = SimpleNamespace(
            runtime=SimpleNamespace(
                configure_notifications=Mock(),
                is_available=Mock(return_value=True),
                cancel_start_after_conflict_prompt=Mock(),
                execute_windivert_autofix=Mock(),
                install_windows_server_wlanapi=Mock(return_value=(True, "")),
                prepare_launch_conflict_resolution=Mock(),
                continue_start_after_conflict_resolution=Mock(),
            ),
            tray=SimpleNamespace(
                show_notification_if_available=Mock(),
                configure=Mock(),
            ),
        )

        with (
            patch.object(window_notifications_setup, "WindowNotificationCenter", NotificationCenter),
            patch.object(window_notifications_setup, "show_page", return_value=True) as routed_show_page,
        ):
            attach_window_notifications(window, features)
            self.assertTrue(captured["show_page"](PageName.SERVERS, allow_internal=True))

        routed_show_page.assert_called_once_with(window, PageName.SERVERS, allow_internal=True)

    def test_control_start_waits_until_runtime_is_available(self) -> None:
        from ui import launch_control as launch_control_module
        from ui.launch_control import LaunchControl

        status_calls: list[str] = []
        runtime = SimpleNamespace(
            is_available=Mock(side_effect=[False, False, True]),
            start=Mock(return_value=True),
        )
        control = LaunchControl(
            runtime_feature=runtime,
            ui_state_store=SimpleNamespace(snapshot=lambda: SimpleNamespace(launch_phase="stopped", launch_running=False)),
            set_status=status_calls.append,
        )
        preparing_calls: list[tuple[bool, str]] = []
        control.preparingChanged.connect(lambda active, text: preparing_calls.append((active, text)))
        scheduled: list[object] = []

        with patch.object(
            launch_control_module.QTimer,
            "singleShot",
            side_effect=lambda _delay_ms, callback: scheduled.append(callback),
        ):
            control.start()
            self.assertEqual(len(scheduled), 1)
            scheduled.pop(0)()
            self.assertEqual(len(scheduled), 1)
            scheduled.pop(0)()

        runtime.start.assert_called_once_with()
        self.assertIn((True, "Подготовка запуска..."), preparing_calls)
        self.assertEqual(preparing_calls[-1], (False, ""))
        self.assertIn("Подготовка запуска...", status_calls)
        self.assertFalse(control.is_preparing())

    def test_post_startup_tasks_install_hosts_page_warmup(self) -> None:
        from main import post_startup
        from main.post_startup import PostStartupDeps, install_post_startup_tasks

        startup_host = object()
        hosts_feature = object()
        profile_feature = object()
        log_startup_metric = Mock()
        deps = PostStartupDeps(
            startup_host=startup_host,
            hosts_feature=hosts_feature,
            profile_feature=profile_feature,
            dns_feature=object(),
            notify=Mock(),
            notify_many=Mock(),
            set_status=Mock(),
            log_startup_metric=log_startup_metric,
            start_proxy_if_enabled_async=Mock(),
            startup_lists_check=Mock(),
            install_tray_post_startup=Mock(),
            updater_feature=Mock(),
        )

        with (
            patch.object(post_startup, "install_startup_checks"),
            patch.object(post_startup, "install_after_interactive_import_warmup"),
            patch.object(post_startup, "install_secondary_page_warmup"),
            patch.object(post_startup, "install_user_preset_contract_migration"),
            patch.object(post_startup, "install_remote_presets_sync"),
            patch.object(post_startup, "install_deferred_maintenance"),
            patch.object(post_startup, "install_telegram_proxy_startup"),
            patch.object(post_startup, "install_telegram_proxy_page_warmup"),
            patch.object(post_startup, "install_lists_check"),
            patch.object(post_startup, "install_dns_address_migration"),
            patch.object(post_startup, "install_hosts_applied_selection_refresh"),
            patch.object(post_startup, "install_onboarding_tour"),
            patch.object(post_startup, "install_dns_page_data_warmup"),
            patch.object(post_startup, "install_hosts_page_warmup") as install_hosts_page_warmup,
            patch.object(post_startup, "install_profile_warmup"),
            patch.object(post_startup, "install_update_check"),
            patch.object(post_startup, "install_cpu_diagnostic"),
            patch.object(post_startup, "install_qt_event_diagnostic_probe"),
            patch.object(post_startup, "install_global_exception_handler"),
        ):
            install_post_startup_tasks(deps)

        install_hosts_page_warmup.assert_called_once_with(
            startup_host,
            hosts_feature=hosts_feature,
            log_startup_metric=log_startup_metric,
        )
        self.assertFalse(hasattr(post_startup, "install_page_warmup"))

    def test_post_startup_tasks_install_telegram_proxy_page_warmup(self) -> None:
        from main import post_startup
        from main.post_startup import PostStartupDeps, install_post_startup_tasks

        startup_host = object()
        log_startup_metric = Mock()
        deps = PostStartupDeps(
            startup_host=startup_host,
            profile_feature=object(),
            dns_feature=object(),
            notify=Mock(),
            notify_many=Mock(),
            set_status=Mock(),
            log_startup_metric=log_startup_metric,
            start_proxy_if_enabled_async=Mock(),
            startup_lists_check=Mock(),
            install_tray_post_startup=Mock(),
            updater_feature=Mock(),
        )

        with (
            patch.object(post_startup, "install_startup_checks"),
            patch.object(post_startup, "install_after_interactive_import_warmup"),
            patch.object(post_startup, "install_secondary_page_warmup"),
            patch.object(post_startup, "install_user_preset_contract_migration"),
            patch.object(post_startup, "install_remote_presets_sync"),
            patch.object(post_startup, "install_deferred_maintenance"),
            patch.object(post_startup, "install_telegram_proxy_startup"),
            patch.object(post_startup, "install_telegram_proxy_page_warmup") as install_telegram_proxy_page_warmup,
            patch.object(post_startup, "install_lists_check"),
            patch.object(post_startup, "install_dns_address_migration"),
            patch.object(post_startup, "install_hosts_applied_selection_refresh"),
            patch.object(post_startup, "install_onboarding_tour"),
            patch.object(post_startup, "install_dns_page_data_warmup"),
            patch.object(post_startup, "install_hosts_page_warmup"),
            patch.object(post_startup, "install_profile_warmup"),
            patch.object(post_startup, "install_update_check"),
            patch.object(post_startup, "install_cpu_diagnostic"),
            patch.object(post_startup, "install_qt_event_diagnostic_probe"),
            patch.object(post_startup, "install_global_exception_handler"),
            patch.object(post_startup, "install_startup_audit"),
        ):
            install_post_startup_tasks(deps)

        install_telegram_proxy_page_warmup.assert_called_once_with(
            startup_host,
            log_startup_metric=log_startup_metric,
        )

    def test_post_startup_tasks_install_profile_warmup(self) -> None:
        from main import post_startup
        from main.post_startup import PostStartupDeps, install_post_startup_tasks

        startup_host = object()
        profile_feature = object()
        log_startup_metric = Mock()
        deps = PostStartupDeps(
            startup_host=startup_host,
            profile_feature=profile_feature,
            dns_feature=object(),
            notify=Mock(),
            notify_many=Mock(),
            set_status=Mock(),
            log_startup_metric=log_startup_metric,
            start_proxy_if_enabled_async=Mock(),
            startup_lists_check=Mock(),
            install_tray_post_startup=Mock(),
            updater_feature=Mock(),
        )

        with (
            patch.object(post_startup, "install_startup_checks"),
            patch.object(post_startup, "install_after_interactive_import_warmup"),
            patch.object(post_startup, "install_secondary_page_warmup"),
            patch.object(post_startup, "install_user_preset_contract_migration"),
            patch.object(post_startup, "install_remote_presets_sync"),
            patch.object(post_startup, "install_deferred_maintenance"),
            patch.object(post_startup, "install_telegram_proxy_startup"),
            patch.object(post_startup, "install_telegram_proxy_page_warmup"),
            patch.object(post_startup, "install_lists_check"),
            patch.object(post_startup, "install_dns_address_migration"),
            patch.object(post_startup, "install_hosts_applied_selection_refresh"),
            patch.object(post_startup, "install_onboarding_tour"),
            patch.object(post_startup, "install_dns_page_data_warmup"),
            patch.object(post_startup, "install_hosts_page_warmup"),
            patch.object(post_startup, "install_profile_warmup") as install_profile_warmup,
            patch.object(post_startup, "install_update_check"),
            patch.object(post_startup, "install_cpu_diagnostic"),
            patch.object(post_startup, "install_qt_event_diagnostic_probe"),
            patch.object(post_startup, "install_global_exception_handler"),
        ):
            install_post_startup_tasks(deps)

        install_profile_warmup.assert_called_once_with(
            startup_host,
            profile_feature=profile_feature,
            log_startup_metric=log_startup_metric,
            current_launch_method="",
            on_profile_warmup_ready=None,
        )

    def test_post_startup_profile_warmup_refreshes_profile_summary_after_ready(self) -> None:
        from main import post_startup
        from main.post_startup import PostStartupDeps, install_post_startup_tasks

        startup_host = object()
        profile_feature = object()
        presets_feature = SimpleNamespace(refresh_profile_strategy_summary_in_store=Mock())
        ui_state_store = object()
        deps = PostStartupDeps(
            startup_host=startup_host,
            profile_feature=profile_feature,
            presets_feature=presets_feature,
            ui_state_store=ui_state_store,
            dns_feature=object(),
            notify=Mock(),
            notify_many=Mock(),
            set_status=Mock(),
            log_startup_metric=Mock(),
            start_proxy_if_enabled_async=Mock(),
            startup_lists_check=Mock(),
            install_tray_post_startup=Mock(),
            updater_feature=Mock(),
        )

        with (
            patch.object(post_startup, "install_startup_checks"),
            patch.object(post_startup, "install_after_interactive_import_warmup"),
            patch.object(post_startup, "install_secondary_page_warmup"),
            patch.object(post_startup, "install_user_preset_contract_migration"),
            patch.object(post_startup, "install_remote_presets_sync"),
            patch.object(post_startup, "install_deferred_maintenance"),
            patch.object(post_startup, "install_telegram_proxy_startup"),
            patch.object(post_startup, "install_telegram_proxy_page_warmup"),
            patch.object(post_startup, "install_lists_check"),
            patch.object(post_startup, "install_dns_address_migration"),
            patch.object(post_startup, "install_hosts_applied_selection_refresh"),
            patch.object(post_startup, "install_onboarding_tour"),
            patch.object(post_startup, "install_dns_page_data_warmup"),
            patch.object(post_startup, "install_hosts_page_warmup"),
            patch.object(post_startup, "install_profile_warmup") as install_profile_warmup,
            patch.object(post_startup, "install_user_presets_warmup"),
            patch.object(post_startup, "install_update_check"),
            patch.object(post_startup, "install_cpu_diagnostic"),
            patch.object(post_startup, "install_qt_event_diagnostic_probe"),
            patch.object(post_startup, "install_global_exception_handler"),
        ):
            install_post_startup_tasks(deps)

        callback = install_profile_warmup.call_args.kwargs["on_profile_warmup_ready"]
        self.assertIsNotNone(callback)

        callback("zapret2_mode")

        presets_feature.refresh_profile_strategy_summary_in_store.assert_called_once_with(
            method="zapret2_mode",
            profile_feature=profile_feature,
            ui_state_store=ui_state_store,
        )

    def test_post_startup_tasks_install_user_presets_warmup(self) -> None:
        from main import post_startup
        from main.post_startup import PostStartupDeps, install_post_startup_tasks

        startup_host = object()
        presets_feature = object()
        log_startup_metric = Mock()
        deps = PostStartupDeps(
            startup_host=startup_host,
            profile_feature=object(),
            presets_feature=presets_feature,
            dns_feature=object(),
            notify=Mock(),
            notify_many=Mock(),
            set_status=Mock(),
            log_startup_metric=log_startup_metric,
            start_proxy_if_enabled_async=Mock(),
            startup_lists_check=Mock(),
            install_tray_post_startup=Mock(),
            updater_feature=Mock(),
        )

        with (
            patch.object(post_startup, "install_startup_checks"),
            patch.object(post_startup, "install_after_interactive_import_warmup"),
            patch.object(post_startup, "install_secondary_page_warmup"),
            patch.object(post_startup, "install_user_preset_contract_migration"),
            patch.object(post_startup, "install_remote_presets_sync"),
            patch.object(post_startup, "install_deferred_maintenance"),
            patch.object(post_startup, "install_telegram_proxy_startup"),
            patch.object(post_startup, "install_telegram_proxy_page_warmup"),
            patch.object(post_startup, "install_lists_check"),
            patch.object(post_startup, "install_dns_address_migration"),
            patch.object(post_startup, "install_hosts_applied_selection_refresh"),
            patch.object(post_startup, "install_onboarding_tour"),
            patch.object(post_startup, "install_dns_page_data_warmup"),
            patch.object(post_startup, "install_hosts_page_warmup"),
            patch.object(post_startup, "install_profile_warmup"),
            patch.object(post_startup, "install_user_presets_warmup") as install_user_presets_warmup,
            patch.object(post_startup, "install_update_check"),
            patch.object(post_startup, "install_cpu_diagnostic"),
            patch.object(post_startup, "install_qt_event_diagnostic_probe"),
            patch.object(post_startup, "install_global_exception_handler"),
        ):
            install_post_startup_tasks(deps)

        install_user_presets_warmup.assert_called_once_with(
            startup_host,
            presets_feature=presets_feature,
            log_startup_metric=log_startup_metric,
            current_launch_method="",
        )

    def test_user_presets_runtime_uses_cached_metadata_before_worker(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        service = UserPresetsRuntimeService(scope_key="winws2")
        page = SimpleNamespace(
            isVisible=Mock(return_value=True),
        )
        service.update_cached_folder_state({})
        service._request_rows_plan_refresh = Mock()
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=Mock(return_value=False),
            read_single_metadata=Mock(return_value=None),
            selected_source_file_name=Mock(return_value="a.txt"),
            presets_dir=Mock(),
            cached_metadata=Mock(return_value={"a.txt": {"display_name": "A"}}),
            load_all_metadata=Mock(return_value={}),
            load_folder_state=Mock(return_value={}),
            build_rows_plan=Mock(),
            apply_rows_plan=Mock(),
        )
        service.attach_page(page, adapter)

        service.refresh_presets_view_if_possible(page)

        service._request_rows_plan_refresh.assert_called_once_with(
            {"a.txt": {"display_name": "A"}},
            {},
            None,
            page,
        )
        adapter.load_all_metadata.assert_not_called()

    def test_post_startup_tasks_install_dns_page_data_warmup(self) -> None:
        from main import post_startup
        from main.post_startup import PostStartupDeps, install_post_startup_tasks

        startup_host = object()
        dns_feature = object()
        log_startup_metric = Mock()
        deps = PostStartupDeps(
            startup_host=startup_host,
            profile_feature=object(),
            dns_feature=dns_feature,
            notify=Mock(),
            notify_many=Mock(),
            set_status=Mock(),
            log_startup_metric=log_startup_metric,
            start_proxy_if_enabled_async=Mock(),
            startup_lists_check=Mock(),
            install_tray_post_startup=Mock(),
            updater_feature=Mock(),
        )

        with (
            patch.object(post_startup, "install_startup_checks"),
            patch.object(post_startup, "install_after_interactive_import_warmup"),
            patch.object(post_startup, "install_secondary_page_warmup"),
            patch.object(post_startup, "install_user_preset_contract_migration"),
            patch.object(post_startup, "install_remote_presets_sync"),
            patch.object(post_startup, "install_deferred_maintenance"),
            patch.object(post_startup, "install_telegram_proxy_startup"),
            patch.object(post_startup, "install_telegram_proxy_page_warmup"),
            patch.object(post_startup, "install_lists_check"),
            patch.object(post_startup, "install_dns_address_migration"),
            patch.object(post_startup, "install_hosts_applied_selection_refresh"),
            patch.object(post_startup, "install_onboarding_tour"),
            patch.object(post_startup, "install_dns_page_data_warmup") as install_dns_page_data_warmup,
            patch.object(post_startup, "install_hosts_page_warmup"),
            patch.object(post_startup, "install_profile_warmup"),
            patch.object(post_startup, "install_update_check"),
            patch.object(post_startup, "install_cpu_diagnostic"),
            patch.object(post_startup, "install_qt_event_diagnostic_probe"),
            patch.object(post_startup, "install_global_exception_handler"),
        ):
            install_post_startup_tasks(deps)

        install_dns_page_data_warmup.assert_called_once_with(
            startup_host,
            dns_feature=dns_feature,
            log_startup_metric=log_startup_metric,
        )


    def test_dns_page_data_warmup_uses_backend_cache_without_page_host(self) -> None:
        from main import post_startup_dns_warmup
        from main.post_startup_dns_warmup import install_dns_page_data_warmup

        class Signal:
            def __init__(self) -> None:
                self._callback = None

            def connect(self, callback) -> None:
                self._callback = callback

            def emit(self, value: str = "") -> None:
                self._callback(value)

        signal = Signal()
        startup_host = SimpleNamespace(
            startup_interactive_ready=signal,
            startup_state=SimpleNamespace(interactive_logged=False),
            is_alive=Mock(return_value=True),
        )
        dns_feature = SimpleNamespace(warm_page_data_cache=Mock(return_value=object()))
        metric = Mock()
        delays: list[int] = []
        queued_tasks: list[tuple[str, str]] = []

        with (
            patch.object(
                post_startup_dns_warmup,
                "schedule_after",
                side_effect=lambda delay_ms, callback: delays.append(delay_ms) or callback(),
            ),
            patch.object(
                post_startup_dns_warmup,
                "enqueue_subsystem_task",
                side_effect=lambda queue, name, target: queued_tasks.append((queue, name)) or target(),
            ),
        ):
            install_dns_page_data_warmup(
                startup_host,
                dns_feature=dns_feature,
                log_startup_metric=metric,
            )
            signal.emit("interactive")

        self.assertEqual(delays, [10000])
        self.assertEqual(queued_tasks, [("dns", "DnsPageDataWarmup")])
        dns_feature.warm_page_data_cache.assert_called_once_with()
        self.assertFalse(hasattr(startup_host, "warm_page"))
        metric.assert_any_call("StartupNetworkDataWarmupQueued", "10000ms after interactive")
        metric.assert_any_call("StartupPostInitNetworkDataWarmupStarted", "backend_cache")


    def test_win11_radio_option_recommended_badge_does_not_require_global_flag(self) -> None:
        import ui.widgets.win11_controls as win11_controls

        class Badge:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

        self.assertTrue(hasattr(win11_controls, "_HAS_INFO_BADGE"))

        with patch.object(win11_controls, "_HAS_INFO_BADGE", True):
            self.assertTrue(win11_controls._should_use_info_badge(Badge, object()))

        with patch.object(win11_controls, "_HAS_INFO_BADGE", False):
            self.assertFalse(win11_controls._should_use_info_badge(Badge, object()))

    def test_hide_window_hides_without_changing_window_state(self) -> None:
        from PyQt6.QtCore import Qt
        from ui.window_adapter import hide_window

        calls: list[str] = []

        class Window:
            def windowState(self):
                return Qt.WindowState.WindowMinimized | Qt.WindowState.WindowMaximized

            def setWindowState(self, state) -> None:
                calls.append(f"state:{int(state.value)}")
                self.state = state

            def hide(self) -> None:
                calls.append("hide")

        window = Window()

        hide_window(window)

        self.assertEqual(calls, ["hide"])
        self.assertFalse(hasattr(window, "state"))

    def test_startup_runtime_keeps_coordinator_alive_for_queued_phase_two(self) -> None:
        from main import startup_coordinator
        from main.window_startup_setup import attach_startup_deps_to_window

        signal = SimpleNamespace(emit=Mock())
        window = SimpleNamespace(
            start_in_tray=False,
            set_status=Mock(),
            mark_startup_core_ready=Mock(),
            mark_startup_post_init_done=Mock(),
            log_startup_metric=Mock(),
            finalize_ui_bootstrap_requested=signal,
        )
        features = SimpleNamespace(
            premium=SimpleNamespace(prepare_subscription=Mock()),
            program_settings=SimpleNamespace(ensure_gui_autostart_migrated=Mock(return_value=False)),
            runtime=SimpleNamespace(
                init_launch_runtime_api=Mock(),
                init_launch_runtime=Mock(),
                init_process_monitor=Mock(),
                init_core_startup=Mock(),
            ),
            tray=SimpleNamespace(
                init=Mock(),
                is_initialized=Mock(return_value=False),
            ),
        )

        runtime = attach_startup_deps_to_window(window, features)

        with patch.object(startup_coordinator, "run_queued", side_effect=lambda _callback: None):
            runtime.continue_deferred_init()

        self.assertIsNotNone(runtime.startup_coordinator)
        self.assertIsInstance(runtime.startup_coordinator, startup_coordinator.StartupCoordinator)
        signal.emit.assert_called_once()


class EarlyStartupCrashTests(unittest.TestCase):
    def test_early_startup_exception_hook_writes_crash_file_under_application_root(self) -> None:
        from config.runtime_layout import ApplicationPaths
        from main import early_startup_crash

        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp)
            app_paths = ApplicationPaths.from_root(app_dir)

            with patch.object(early_startup_crash, "APPLICATION_PATHS", app_paths):
                try:
                    raise RuntimeError("boom")
                except RuntimeError:
                    exc_type, exc, tb = sys.exc_info()
                    assert exc_type is not None
                    assert exc is not None
                    early_startup_crash.write_early_startup_crash(exc_type, exc, tb)

            crash_path = app_dir / "logs" / "crashes" / "early_startup_crash.log"
            text = crash_path.read_text(encoding="utf-8")

        self.assertIn("RuntimeError: boom", text)
        self.assertIn("early startup crash", text.lower())


class _BaseWindowEvents:
    def nativeEvent(self, event_type, message):
        self.calls.append("base_native")
        return (False, 123)

    def showMinimized(self) -> None:
        self.calls.append("base_minimize")

    def changeEvent(self, event) -> None:
        self.calls.append("base_change")

    def moveEvent(self, event) -> None:
        self.calls.append("base_move")

    def resizeEvent(self, event) -> None:
        self.calls.append("base_resize")

    def showEvent(self, event) -> None:
        self.calls.append("base_show")

    def hideEvent(self, event) -> None:
        self.calls.append("base_hide")

    def isActiveWindow(self) -> bool:
        return True


class WindowLifecycleEarlyEventTests(unittest.TestCase):
    def test_resize_move_and_show_events_do_not_require_attached_runtime(self) -> None:
        from main.window_lifecycle import WindowLifecycleMixin

        class Window(WindowLifecycleMixin, _BaseWindowEvents):
            def __init__(self) -> None:
                self.calls: list[str] = []

            def findChildren(self, *_args, **_kwargs):
                return []

        window = Window()

        window.resizeEvent(object())
        window.moveEvent(object())
        window.showEvent(object())

        self.assertEqual(window.calls, ["base_resize", "base_move", "base_show"])

    def test_resize_and_show_events_use_runtime_after_it_is_attached(self) -> None:
        from main.window_lifecycle import WindowLifecycleMixin

        class Window(WindowLifecycleMixin, _BaseWindowEvents):
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.window_geometry_runtime = SimpleNamespace(
                    on_geometry_changed=Mock(),
                    apply_saved_maximized_state_if_needed=Mock(),
                    enable_persistence=Mock(),
                )
                self.window_notification_center = SimpleNamespace(
                    schedule_startup_notification_queue=Mock(),
                )
                self.startup_state = SimpleNamespace(
                    ttff_logged=False,
                    ttff_ms=None,
                )
                self.visual_state = SimpleNamespace(holiday_effects=None)

            def findChildren(self, *_args, **_kwargs):
                return []

        window = Window()

        with patch("main.window_lifecycle.QTimer.singleShot", side_effect=lambda *_args, **_kwargs: None):
            window.resizeEvent(object())
            window.showEvent(object())

        window.window_geometry_runtime.on_geometry_changed.assert_called_once()
        window.window_geometry_runtime.apply_saved_maximized_state_if_needed.assert_called_once()
        window.window_notification_center.schedule_startup_notification_queue.assert_called_once_with(0)
        self.assertTrue(window.startup_state.ttff_logged)

    def test_show_event_schedules_titlebar_layout_refresh_after_first_show(self) -> None:
        from main.window_lifecycle import WindowLifecycleMixin

        class Window(WindowLifecycleMixin, _BaseWindowEvents):
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.window_geometry_runtime = SimpleNamespace(
                    apply_saved_maximized_state_if_needed=Mock(),
                    enable_persistence=Mock(),
                )
                self.window_notification_center = None
                self.startup_state = SimpleNamespace(
                    ttff_logged=False,
                    ttff_ms=None,
                )
                self.visual_state = SimpleNamespace(holiday_effects=None)

            def findChildren(self, *_args, **_kwargs):
                return []

        window = Window()
        scheduled_delays: list[int] = []

        def record_single_shot(delay, callback):
            scheduled_delays.append(delay)

        with (
            patch("main.window_lifecycle.refresh_titlebar_layout", create=True) as refresh_titlebar_layout,
            patch("main.window_lifecycle.QTimer.singleShot", side_effect=record_single_shot),
        ):
            window.showEvent(object())

        refresh_titlebar_layout.assert_not_called()
        self.assertIn(0, scheduled_delays)
        self.assertIn(120, scheduled_delays)


    def test_native_minimize_command_hides_to_tray_when_mode_includes_minimize(self) -> None:
        from main.window_native_commands import SC_MINIMIZE, WM_SYSCOMMAND
        from main.window_lifecycle import WindowLifecycleMixin

        class Window(WindowLifecycleMixin, _BaseWindowEvents):
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.close_to_tray = Mock(side_effect=self._close_to_tray)

            def _close_to_tray(self) -> bool:
                self.calls.append("hide_to_tray")
                return True

            window_close_flow = SimpleNamespace(
                minimize_to_tray_enabled=Mock(return_value=True),
            )

        msg = wintypes.MSG()
        msg.message = WM_SYSCOMMAND
        msg.wParam = SC_MINIMIZE
        window = Window()

        with (
            patch(
                "settings.store.get_tray_close_mode",
                side_effect=AssertionError("settings read must not happen in minimize path"),
                create=True,
            ),
            patch("main.window_native_commands.sys.platform", "win32"),
        ):
            result = window.nativeEvent(b"windows_generic_MSG", int(addressof(msg)))

        self.assertEqual(result, (True, 0))
        window.close_to_tray.assert_called_once()
        self.assertEqual(window.calls, ["hide_to_tray"])

    def test_native_minimize_command_uses_normal_window_flow_when_mode_is_normal(self) -> None:
        from main.window_native_commands import SC_MINIMIZE, WM_SYSCOMMAND
        from main.window_lifecycle import WindowLifecycleMixin

        class Window(WindowLifecycleMixin, _BaseWindowEvents):
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.close_to_tray = Mock(return_value=True)

            window_close_flow = SimpleNamespace(
                minimize_to_tray_enabled=Mock(return_value=False),
            )

        msg = wintypes.MSG()
        msg.message = WM_SYSCOMMAND
        msg.wParam = SC_MINIMIZE
        window = Window()

        with (
            patch(
                "settings.store.get_tray_close_mode",
                side_effect=AssertionError("settings read must not happen in minimize path"),
                create=True,
            ),
            patch("main.window_native_commands.sys.platform", "win32"),
        ):
            result = window.nativeEvent(b"windows_generic_MSG", int(addressof(msg)))

        self.assertEqual(result, (False, 123))
        window.close_to_tray.assert_not_called()
        self.assertEqual(window.calls, ["base_native"])

    def test_show_minimized_hides_to_tray_when_mode_includes_minimize(self) -> None:
        from main.window_lifecycle import WindowLifecycleMixin

        class Window(WindowLifecycleMixin, _BaseWindowEvents):
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.close_to_tray = Mock(side_effect=self._close_to_tray)

            def _close_to_tray(self) -> bool:
                self.calls.append("hide_to_tray")
                return True

            window_close_flow = SimpleNamespace(
                minimize_to_tray_enabled=Mock(return_value=True),
            )

        window = Window()

        with patch(
            "settings.store.get_tray_close_mode",
            side_effect=AssertionError("settings read must not happen in minimize path"),
            create=True,
        ):
            window.showMinimized()

        window.close_to_tray.assert_called_once()
        self.assertEqual(window.calls, ["hide_to_tray"])

    def test_show_minimized_uses_normal_window_flow_when_mode_is_normal(self) -> None:
        from main.window_lifecycle import WindowLifecycleMixin

        class Window(WindowLifecycleMixin, _BaseWindowEvents):
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.close_to_tray = Mock(return_value=True)

            window_close_flow = SimpleNamespace(
                minimize_to_tray_enabled=Mock(return_value=False),
            )

        window = Window()

        with patch(
            "settings.store.get_tray_close_mode",
            side_effect=AssertionError("settings read must not happen in minimize path"),
            create=True,
        ):
            window.showMinimized()

        window.close_to_tray.assert_not_called()
        self.assertEqual(window.calls, ["base_minimize"])

    def test_tray_show_window_uses_fast_sidebar_sync_before_show(self) -> None:
        from ui.window_adapter import show_window

        calls: list[str] = []
        scheduled: list[tuple[int, object]] = []
        geometry_runtime = SimpleNamespace(
            show_from_hidden=Mock(side_effect=lambda: calls.append("show_from_hidden")),
        )
        window = SimpleNamespace(
            window_geometry_runtime=geometry_runtime,
            raise_=Mock(side_effect=lambda: calls.append("raise")),
            activateWindow=Mock(side_effect=lambda: calls.append("activate")),
        )

        with (
            patch(
                "ui.navigation.sidebar_builder.sync_existing_nav_visibility",
                side_effect=lambda current_window: calls.append("sync_existing_nav"),
                create=True,
            ) as sync_existing_nav_visibility,
            patch(
                "ui.navigation.sidebar_builder.sync_nav_visibility",
                side_effect=lambda current_window: calls.append("sync_nav"),
            ) as sync_nav_visibility,
            patch(
                "ui.theme_refresh.flush_pending_theme_refreshes",
                side_effect=lambda current_window: calls.append("flush_theme"),
                create=True,
            ) as flush_theme_refreshes,
            patch(
                "ui.window_adapter.QTimer",
                SimpleNamespace(
                    singleShot=lambda delay, callback: scheduled.append((int(delay), callback)),
                ),
                create=True,
            ),
        ):
            show_window(window)

            sync_existing_nav_visibility.assert_called_once_with(window)
            sync_nav_visibility.assert_not_called()
            self.assertEqual(
                calls,
                [
                    "sync_existing_nav",
                    "show_from_hidden",
                    "raise",
                    "activate",
                ],
            )
            self.assertEqual(len(scheduled), 1)
            self.assertEqual(scheduled[0][0], 0)

            scheduled.pop(0)[1]()
            flush_theme_refreshes.assert_called_once_with(window)
            sync_nav_visibility.assert_called_once_with(window)
            self.assertEqual(calls[-2:], ["flush_theme", "sync_nav"])

    def test_tray_show_window_delegates_window_state_restore_to_geometry_runtime(self) -> None:
        from ui.window_adapter import show_window

        calls: list[str] = []
        geometry_runtime = SimpleNamespace(
            show_from_hidden=Mock(side_effect=lambda: calls.append("show_from_hidden")),
        )
        window = SimpleNamespace(
            window_geometry_runtime=geometry_runtime,
            raise_=Mock(side_effect=lambda: calls.append("raise")),
            activateWindow=Mock(side_effect=lambda: calls.append("activate")),
        )

        with (
            patch("ui.navigation.sidebar_builder.sync_existing_nav_visibility", create=True),
            patch("ui.window_adapter.QTimer", SimpleNamespace(singleShot=lambda *_args, **_kwargs: None), create=True),
        ):
            show_window(window)

        self.assertEqual(
            calls,
            [
                "show_from_hidden",
                "raise",
                "activate",
            ],
        )


class WindowsSessionShutdownTests(unittest.TestCase):
    def test_close_flow_receives_launch_state_snapshot_instead_of_full_runtime_feature(self) -> None:
        from main import window_lifecycle_setup
        from ui.window_close_flow import WindowCloseFlow

        init_signature = inspect.signature(WindowCloseFlow.__init__)
        flow_source = inspect.getsource(WindowCloseFlow)
        setup_source = inspect.getsource(window_lifecycle_setup.attach_window_lifecycle)

        self.assertNotIn("runtime_feature", init_signature.parameters)
        self.assertNotIn("self._runtime =", flow_source)
        self.assertIn("get_launch_state_snapshot", init_signature.parameters)
        self.assertIn("self._get_launch_state_snapshot", flow_source)
        self.assertIn("get_launch_state_snapshot=features.runtime.snapshot", setup_source)

    def test_close_flow_skips_dialog_when_windows_session_is_ending(self) -> None:
        from ui.window_close_flow import WindowCloseFlow

        close_dialog_module = types.ModuleType("ui.close_dialog")
        close_dialog_module.ask_close_action = Mock(return_value=None)
        original_close_dialog = sys.modules.get("ui.close_dialog")
        sys.modules["ui.close_dialog"] = close_dialog_module
        try:
            event = SimpleNamespace(ignore=Mock())
            close_state = SimpleNamespace(
                closing_completely=False,
                windows_session_ending=True,
            )
            runtime = SimpleNamespace(snapshot=Mock())
            flow = WindowCloseFlow(
                parent=object(),
                close_state=close_state,
                get_launch_state_snapshot=runtime.snapshot,
                close_to_tray=Mock(),
                exit_stop_dpi=Mock(),
                exit_keep_dpi=Mock(),
            )

            self.assertTrue(flow.should_continue_final_close(event))
        finally:
            if original_close_dialog is None:
                sys.modules.pop("ui.close_dialog", None)
            else:
                sys.modules["ui.close_dialog"] = original_close_dialog

        event.ignore.assert_not_called()
        close_dialog_module.ask_close_action.assert_not_called()
        runtime.snapshot.assert_not_called()

    def test_close_flow_hides_to_tray_without_dialog_when_mode_includes_close(self) -> None:
        from ui.window_close_flow import WindowCloseFlow

        close_dialog_module = types.ModuleType("ui.close_dialog")
        close_dialog_module.ask_close_action = Mock(return_value=None)
        original_close_dialog = sys.modules.get("ui.close_dialog")
        sys.modules["ui.close_dialog"] = close_dialog_module
        try:
            event = SimpleNamespace(ignore=Mock())
            close_state = SimpleNamespace(
                closing_completely=False,
                windows_session_ending=False,
            )
            runtime = SimpleNamespace(snapshot=Mock())
            close_to_tray = Mock(return_value=True)
            flow = WindowCloseFlow(
                parent=object(),
                close_state=close_state,
                get_launch_state_snapshot=runtime.snapshot,
                close_to_tray=close_to_tray,
                exit_stop_dpi=Mock(),
                exit_keep_dpi=Mock(),
                tray_close_mode=Mock(return_value="minimize_and_close"),
            )

            with patch(
                "settings.store.get_tray_close_mode",
                side_effect=AssertionError("settings read must not happen in close path"),
                create=True,
            ):
                self.assertFalse(flow.should_continue_final_close(event))
        finally:
            if original_close_dialog is None:
                sys.modules.pop("ui.close_dialog", None)
            else:
                sys.modules["ui.close_dialog"] = original_close_dialog

        event.ignore.assert_called_once()
        close_to_tray.assert_called_once()
        close_dialog_module.ask_close_action.assert_not_called()
        runtime.snapshot.assert_not_called()

    def test_close_flow_shows_dialog_when_mode_is_normal(self) -> None:
        from ui.window_close_flow import WindowCloseFlow

        close_dialog_module = types.ModuleType("ui.close_dialog")
        close_dialog_module.ask_close_action = Mock(return_value=None)
        original_close_dialog = sys.modules.get("ui.close_dialog")
        sys.modules["ui.close_dialog"] = close_dialog_module
        try:
            event = SimpleNamespace(ignore=Mock())
            close_state = SimpleNamespace(
                closing_completely=False,
                windows_session_ending=False,
            )
            runtime = SimpleNamespace(snapshot=Mock(return_value=SimpleNamespace(running=True)))
            close_to_tray = Mock(return_value=True)
            flow = WindowCloseFlow(
                parent=object(),
                close_state=close_state,
                get_launch_state_snapshot=runtime.snapshot,
                close_to_tray=close_to_tray,
                exit_stop_dpi=Mock(),
                exit_keep_dpi=Mock(),
                tray_close_mode=Mock(return_value="normal"),
            )

            with patch(
                "settings.store.get_tray_close_mode",
                side_effect=AssertionError("settings read must not happen in close path"),
                create=True,
            ):
                self.assertFalse(flow.should_continue_final_close(event))
        finally:
            if original_close_dialog is None:
                sys.modules.pop("ui.close_dialog", None)
            else:
                sys.modules["ui.close_dialog"] = original_close_dialog

        event.ignore.assert_called_once()
        runtime.snapshot.assert_called_once()
        close_dialog_module.ask_close_action.assert_called_once_with(
            parent=flow._parent,
            launch_running=True,
        )
        close_to_tray.assert_not_called()

    def test_close_flow_shows_dialog_when_only_minimize_hides_to_tray(self) -> None:
        from ui.window_close_flow import WindowCloseFlow

        close_dialog_module = types.ModuleType("ui.close_dialog")
        close_dialog_module.ask_close_action = Mock(return_value=None)
        original_close_dialog = sys.modules.get("ui.close_dialog")
        sys.modules["ui.close_dialog"] = close_dialog_module
        try:
            event = SimpleNamespace(ignore=Mock())
            close_state = SimpleNamespace(
                closing_completely=False,
                windows_session_ending=False,
            )
            runtime = SimpleNamespace(snapshot=Mock(return_value=SimpleNamespace(launch_running=True)))
            close_to_tray = Mock(return_value=True)
            flow = WindowCloseFlow(
                parent=object(),
                close_state=close_state,
                get_launch_state_snapshot=runtime.snapshot,
                close_to_tray=close_to_tray,
                exit_stop_dpi=Mock(),
                exit_keep_dpi=Mock(),
                tray_close_mode=Mock(return_value="minimize_only"),
            )

            with patch(
                "settings.store.get_tray_close_mode",
                side_effect=AssertionError("settings read must not happen in close path"),
                create=True,
            ):
                self.assertFalse(flow.should_continue_final_close(event))
        finally:
            if original_close_dialog is None:
                sys.modules.pop("ui.close_dialog", None)
            else:
                sys.modules["ui.close_dialog"] = original_close_dialog

        event.ignore.assert_called_once()
        runtime.snapshot.assert_called_once()
        close_dialog_module.ask_close_action.assert_called_once_with(
            parent=flow._parent,
            launch_running=True,
        )
        close_to_tray.assert_not_called()

    def test_close_flow_still_shows_dialog_when_runtime_snapshot_fails(self) -> None:
        from ui.window_close_flow import WindowCloseFlow

        close_dialog_module = types.ModuleType("ui.close_dialog")
        close_dialog_module.ask_close_action = Mock(return_value=None)
        original_close_dialog = sys.modules.get("ui.close_dialog")
        sys.modules["ui.close_dialog"] = close_dialog_module
        try:
            event = SimpleNamespace(ignore=Mock())
            close_state = SimpleNamespace(
                closing_completely=False,
                windows_session_ending=False,
            )
            runtime = SimpleNamespace(snapshot=Mock(side_effect=RuntimeError("snapshot failed")))
            flow = WindowCloseFlow(
                parent=object(),
                close_state=close_state,
                get_launch_state_snapshot=runtime.snapshot,
                close_to_tray=Mock(),
                exit_stop_dpi=Mock(),
                exit_keep_dpi=Mock(),
                tray_close_mode=Mock(return_value="normal"),
            )

            with patch(
                "settings.store.get_tray_close_mode",
                side_effect=AssertionError("settings read must not happen in close path"),
                create=True,
            ):
                self.assertFalse(flow.should_continue_final_close(event))
        finally:
            if original_close_dialog is None:
                sys.modules.pop("ui.close_dialog", None)
            else:
                sys.modules["ui.close_dialog"] = original_close_dialog

        event.ignore.assert_called_once()
        runtime.snapshot.assert_called_once()
        close_dialog_module.ask_close_action.assert_called_once_with(
            parent=flow._parent,
            launch_running=False,
        )


if __name__ == "__main__":
    unittest.main()
