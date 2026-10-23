"""Проверка применения не трогает новый подбор и не публикует устаревший итог."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from blockcheck.strategy_apply_check import ApplyCheck, CHECK_OK, StrategyApplyCheckWorker
from blockcheck.ui.strategy_scan_page import StrategyScanPage
from ui.one_shot_worker_runtime import OneShotWorkerRuntime
from ui.page_deps.system import build_blockcheck_page_kwargs


def test_stale_apply_check_does_not_notify_after_new_request():
    page = StrategyScanPage.__new__(StrategyScanPage)
    page._cleanup_in_progress = False
    page._apply_check_runtime = OneShotWorkerRuntime()
    old = page._apply_check_runtime.next_request_id()
    page._apply_check_runtime.cancel()
    page._on_log = Mock()
    with patch("blockcheck.strategy_apply_check.apply_check_message") as message:
        page._on_apply_check_finished(old, "example.org", CHECK_OK, "")
    message.assert_not_called()
    page._on_log.assert_not_called()


def test_apply_check_cannot_notify_a_closed_page():
    page = StrategyScanPage.__new__(StrategyScanPage)
    page._cleanup_in_progress = True
    page._apply_check_runtime = OneShotWorkerRuntime()
    current = page._apply_check_runtime.next_request_id()
    with patch("blockcheck.strategy_apply_check.apply_check_message") as message:
        page._on_apply_check_finished(current, "example.org", CHECK_OK, "")
    message.assert_not_called()


def test_apply_worker_carries_request_and_suppresses_cancelled_result():
    for cancelled in (False, True):
        worker = StrategyApplyCheckWorker(7, "example.org", is_running=lambda: True, restarting=False)
        got = []
        worker.completed.connect(lambda *args: got.append(args))
        if cancelled:
            worker.stop()
        with patch("blockcheck.strategy_apply_check.run_apply_check", return_value=ApplyCheck(CHECK_OK)):
            worker.run()
        assert got == ([] if cancelled else [(7, "example.org", CHECK_OK, "")])


def _ensure_callback(runtime):
    return build_blockcheck_page_kwargs(
        page_name=None, blockcheck_feature=None, dns_feature=None,
        runtime_feature=runtime,
    )["ensure_bypass_for_strategy"]


def test_applying_while_scan_owns_engine_cannot_start_second_engine():
    runtime = SimpleNamespace(is_strategy_scan_active=lambda: True, is_running=Mock(), start=Mock(), stop=Mock(), restart=Mock())
    assert _ensure_callback(runtime)() == "scan_running"
    runtime.start.assert_not_called()
    runtime.restart.assert_not_called()


def test_apply_restarts_active_engine_and_starts_inactive_engine():
    for running, result in ((True, "restarting"), (False, "started")):
        runtime = SimpleNamespace(is_strategy_scan_active=lambda: False, is_running=lambda: running,
                                  start=Mock(return_value=True), stop=Mock(return_value=True), restart=Mock(return_value=True))
        assert _ensure_callback(runtime)() == result
        (runtime.restart if running else runtime.start).assert_called_once()
        (runtime.start if running else runtime.restart).assert_not_called()
