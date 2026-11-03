"""Выход не бросает выключенный подбором обход и не запускает его ради установщика."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from main.application_lifecycle import ApplicationLifecycle


class ExitAfterStrategyScanTests(TestCase):
    def make_lifecycle(self, *, waiting: bool):
        port = SimpleNamespace(
            persist_geometry=Mock(), persist_sidebar_state=Mock(),
            finish_strategy_scan_before_exit=Mock(return_value=waiting),
        )
        runtime = SimpleNamespace(is_running=Mock(return_value=False))
        lifecycle = ApplicationLifecycle(
            window_port=port, close_state=SimpleNamespace(), runtime_feature=runtime,
            telegram_proxy_feature=Mock(), tray_feature=Mock(),
        )
        lifecycle._quit_application = Mock()
        return lifecycle, port, runtime

    def test_active_scan_is_cancelled_and_exit_waits_for_actual_start(self):
        lifecycle, port, runtime = self.make_lifecycle(waiting=True)
        scheduled = []
        with patch("main.application_lifecycle.QTimer.singleShot", side_effect=lambda _ms, callback: scheduled.append(callback)):
            lifecycle.exit_keep_dpi()
            lifecycle._quit_application.assert_not_called()
            on_done = port.finish_strategy_scan_before_exit.call_args.args[0]
            on_done(True)
            lifecycle._quit_application.assert_not_called()
            self.assertEqual(len(scheduled), 1)
            runtime.is_running.return_value = True
            scheduled.pop()()
        lifecycle._quit_application.assert_called_once()

    def test_no_active_scan_exits_without_waiting(self):
        lifecycle, _port, _runtime = self.make_lifecycle(waiting=False)
        lifecycle.exit_keep_dpi()
        lifecycle._quit_application.assert_called_once()

    def test_installer_exit_does_not_restore_or_wait_for_scan(self):
        lifecycle, port, _runtime = self.make_lifecycle(waiting=True)
        lifecycle.request_exit(stop_dpi=False, restore_after_scan=False)
        port.finish_strategy_scan_before_exit.assert_not_called()
        lifecycle._quit_application.assert_called_once()

    def test_wait_for_failed_restart_is_bounded(self):
        lifecycle, _port, _runtime = self.make_lifecycle(waiting=True)
        with patch("main.application_lifecycle.time.monotonic", return_value=30):
            lifecycle._wait_dpi_running_then(True, lifecycle._quit_application, deadline=29)
        lifecycle._quit_application.assert_called_once()
