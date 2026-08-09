import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from blockcheck.ui.strategy_scan_page import StrategyScanPage


class StrategyScanFinalizeRuntimeArchitectureTests(unittest.TestCase):
    def test_finalize_state_uses_shared_latest_value_helper(self) -> None:
        import blockcheck.ui.strategy_scan_page as strategy_scan_page
        from ui.latest_value_worker_state import LatestValueWorkerState

        init_source = inspect.getsource(StrategyScanPage.__init__)
        request_source = inspect.getsource(StrategyScanPage._request_strategy_scan_finalize)
        finished_source = inspect.getsource(StrategyScanPage._on_strategy_scan_finalize_worker_finished)
        cleanup_source = inspect.getsource(StrategyScanPage.cleanup)

        self.assertTrue(hasattr(strategy_scan_page, "LatestValueWorkerState"))
        self.assertIs(strategy_scan_page.LatestValueWorkerState, LatestValueWorkerState)
        self.assertIn("_strategy_scan_finalize_state = LatestValueWorkerState", init_source)
        self.assertIn("_strategy_scan_finalize_state_obj()", request_source)
        self.assertIn("schedule_pending_after_finish", finished_source)
        self.assertIn("_strategy_scan_finalize_state_obj().reset()", cleanup_source)

    def test_finalize_uses_runtime_not_manual_page_worker(self) -> None:
        page_source = inspect.getsource(StrategyScanPage)
        request_source = inspect.getsource(StrategyScanPage._request_strategy_scan_finalize)
        finished_source = inspect.getsource(StrategyScanPage._on_strategy_scan_finalize_finished)
        failed_source = inspect.getsource(StrategyScanPage._on_strategy_scan_finalize_failed)
        cleanup_source = inspect.getsource(StrategyScanPage.cleanup)

        self.assertIn("_strategy_scan_finalize_runtime = OneShotWorkerRuntime()", page_source)
        self.assertIn("_strategy_scan_finalize_state = LatestValueWorkerState", page_source)
        self.assertIn("state.is_busy()", request_source)
        self.assertIn("start_qthread_worker", request_source)
        self.assertIn("bind_worker", request_source)
        self.assertIn("_strategy_scan_finalize_runtime.is_current", finished_source)
        self.assertIn("_strategy_scan_finalize_runtime.is_current", failed_source)
        self.assertIn("_strategy_scan_finalize_runtime.stop", cleanup_source)
        self.assertIn("_strategy_scan_finalize_runtime.cancel", cleanup_source)
        self.assertNotIn("_strategy_scan_finalize_worker =", page_source)
        self.assertNotIn("_strategy_scan_finalize_request_id", page_source)
        self.assertNotIn("worker.start()", request_source)

    def test_finalize_request_waits_while_restart_is_scheduled(self) -> None:
        page = StrategyScanPage.__new__(StrategyScanPage)
        report = object()
        page._strategy_scan_finalize_runtime = SimpleNamespace(is_running=Mock(return_value=False), start_qthread_worker=Mock())
        page._strategy_scan_finalize_start_scheduled = True
        page._strategy_scan_finalize_pending = None

        StrategyScanPage._request_strategy_scan_finalize(page, report)

        page._strategy_scan_finalize_runtime.start_qthread_worker.assert_not_called()
        self.assertIs(page._strategy_scan_finalize_pending, report)

    def test_pending_finalize_restarts_after_event_loop_turn(self) -> None:
        import blockcheck.ui.strategy_scan_page as strategy_scan_page

        page = StrategyScanPage.__new__(StrategyScanPage)
        report = object()
        page._cleanup_in_progress = False
        page._strategy_scan_finalize_pending = report
        page._strategy_scan_finalize_start_scheduled = False
        page._request_strategy_scan_finalize = Mock()
        single_shot = Mock(side_effect=lambda _delay, _callback: None)

        with patch.object(strategy_scan_page, "QTimer", SimpleNamespace(singleShot=single_shot), create=True):
            StrategyScanPage._on_strategy_scan_finalize_worker_finished(page, object())

        single_shot.assert_called_once()
        self.assertEqual(single_shot.call_args.args[0], 0)
        page._request_strategy_scan_finalize.assert_not_called()

        single_shot.call_args.args[1]()

        page._request_strategy_scan_finalize.assert_called_once_with(report)
        self.assertIsNone(page._strategy_scan_finalize_pending)

    def test_stale_finalize_worker_finished_does_not_restart_pending_finalize(self) -> None:
        import blockcheck.ui.strategy_scan_page as strategy_scan_page

        page = StrategyScanPage.__new__(StrategyScanPage)
        report = object()
        page._cleanup_in_progress = False
        page._strategy_scan_finalize_runtime = SimpleNamespace(worker=object())
        page._strategy_scan_finalize_pending = report
        page._strategy_scan_finalize_start_scheduled = False
        page._request_strategy_scan_finalize = Mock()
        single_shot = Mock()

        with patch.object(strategy_scan_page, "QTimer", SimpleNamespace(singleShot=single_shot), create=True):
            StrategyScanPage._on_strategy_scan_finalize_worker_finished(page, object())

        single_shot.assert_not_called()
        page._request_strategy_scan_finalize.assert_not_called()
        self.assertIs(page._strategy_scan_finalize_pending, report)

    def test_finalize_result_is_ignored_when_new_finalize_is_pending(self) -> None:
        import blockcheck.ui.strategy_scan_page as strategy_scan_page

        page = StrategyScanPage.__new__(StrategyScanPage)
        page._cleanup_in_progress = False
        page._strategy_scan_finalize_pending = object()
        page._strategy_scan_finalize_runtime = Mock()
        page._strategy_scan_finalize_runtime.is_current.return_value = True
        page._blockcheck = Mock()
        page._reset_ui = Mock()
        page._set_support_status = Mock()
        page._scan_protocol = "tcp_https"
        page._progress_bar = object()
        page._status_label = object()
        page.window = Mock(return_value=object())

        with patch.object(strategy_scan_page, "apply_finished_scan") as apply_finished_scan:
            StrategyScanPage._on_strategy_scan_finalize_finished(page, 8, object())

        apply_finished_scan.assert_not_called()

    def test_finalize_error_is_ignored_when_new_finalize_is_pending(self) -> None:
        page = StrategyScanPage.__new__(StrategyScanPage)
        page._cleanup_in_progress = False
        page._strategy_scan_finalize_pending = object()
        page._strategy_scan_finalize_runtime = Mock()
        page._strategy_scan_finalize_runtime.is_current.return_value = True
        page._reset_ui = Mock()
        page._status_label = SimpleNamespace(setText=Mock())
        page._set_support_status = Mock()

        StrategyScanPage._on_strategy_scan_finalize_failed(page, 8, "old error")

        page._reset_ui.assert_not_called()
        page._status_label.setText.assert_not_called()
        page._set_support_status.assert_not_called()


if __name__ == "__main__":
    unittest.main()
