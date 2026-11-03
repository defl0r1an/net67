"""Зелёная кнопка выключает обход, даже пока завершается проверка DNS."""
from threading import Event
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from oneclick.state import OneClickState
from oneclick.ui.button import OneClickButton
from test_oneclick_runner import _FakeIntegrity, _Recorder, _request


def _wait_until(condition, seconds=3):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert condition()


@pytest.mark.parametrize("theme", [Theme.DARK, Theme.LIGHT])
def test_mouse_click_stops_the_engine_during_pending_dns_without_concurrent_steps(theme):
    app = QApplication.instance() or QApplication([])
    setTheme(theme)
    recorder = _Recorder()
    in_dns = Event()
    release = Event()
    running = [False]
    factories = []

    def deps_factory(**kwargs):
        factories.append(kwargs)
        deps = recorder.build()
        deps.report = kwargs["report"]

        def start():
            running[0] = True
            recorder.calls.append("start_dpi")
            return True, ""

        def stop():
            running[0] = False
            recorder.calls.append("stop_dpi")
            return True, ""

        def dns():
            in_dns.set()
            while not kwargs["should_stop"]() and not release.wait(0.01):
                pass
            return [_FakeIntegrity("example.com", is_consistent=False)]

        deps.start_dpi, deps.stop_dpi, deps.check_dns_integrity = start, stop, dns
        return deps

    feature = SimpleNamespace(is_any_running=lambda **kwargs: running[0])
    button = OneClickButton(get_runtime_feature=lambda: feature)
    states = []
    button.stateChanged.connect(states.append)
    button.resize(1000, 180)
    button.show()
    request = _request(allow_dns_fix=True, needs_telegram_proxy=False, run_selfcheck=False)
    try:
        with patch("oneclick.deps.build_oneclick_deps", side_effect=deps_factory), patch("wizard.apply.build_request_from_settings", return_value=request):
            for cycle in range(3):
                in_dns.clear()
                button.button.click()
                _wait_until(lambda: in_dns.is_set() and button.state is OneClickState.RUNNING)
                assert button.button.is_click_enabled()
                stop_index = len(states)
                QTest.mouseClick(button.button, Qt.MouseButton.LeftButton, pos=button.button.button_rect().center())
                _wait_until(lambda: button._worker is None)
                assert button.state is OneClickState.OFF
                assert button.button.is_click_enabled()
                assert OneClickState.RUNNING not in states[stop_index:]

        assert len(factories) == 6
        assert recorder.calls.count("stop_dpi") == 3
        assert "apply_dns" not in recorder.calls
        assert not running[0]
        assert button.state is OneClickState.OFF
        assert button.button.is_click_enabled()
    finally:
        release.set()
        worker = button._worker
        if worker is not None:
            worker.request_disable()
            worker.wait(3000)
        app.processEvents()
        button.stop_worker()
        button.close()
        button.deleteLater()


def test_cancelled_dns_check_cannot_apply_new_settings():
    from oneclick.runner import OneClickRunner

    recorder = _Recorder()
    cancelled = Event()
    deps = recorder.build()

    def dns():
        cancelled.set()
        return [_FakeIntegrity("example.com", is_consistent=False)]

    deps.check_dns_integrity = dns
    runner = OneClickRunner(deps, should_stop=cancelled.is_set)
    runner.enable(_request(allow_dns_fix=True, run_selfcheck=True))
    assert "apply_dns" not in recorder.calls
    assert "probe_domains" not in recorder.calls


def test_dns_adapter_passes_the_stop_request_to_the_network_check():
    from oneclick.deps import _check_dns_integrity

    cancelled = Event()
    with patch("diagnostics.engine.run_dns_check", return_value={}) as check:
        _check_dns_integrity(should_stop=cancelled.is_set)
    assert check.call_args.kwargs["should_stop"] == cancelled.is_set


@pytest.mark.parametrize("stage", ["telegram", "hosts"])
def test_stop_between_preparation_and_system_write_skips_that_write(stage):
    from oneclick.runner import OneClickRunner

    recorder = _Recorder()
    cancelled = Event()
    deps = recorder.build()
    if stage == "telegram":
        deps.check_telegram_ready = lambda: (cancelled.set(), (True, ""))[1]
        request = _request(needs_telegram_proxy=True)
        forbidden = "start_telegram_proxy"
    else:
        deps.backup_hosts = lambda: (cancelled.set(), (True, ""))[1]
        request = _request(hosts_entries={"example.com": "1.1.1.1"})
        forbidden = "apply_hosts"
    OneClickRunner(deps, should_stop=cancelled.is_set).enable(request)
    assert forbidden not in recorder.calls


def test_late_progress_from_previous_worker_cannot_change_the_current_button():
    from oneclick.ui.oneclick_worker import _OneClickWorker

    app = QApplication.instance() or QApplication([])
    button = OneClickButton()
    old = _OneClickWorker(enable=True, runtime_feature=Mock())
    current = _OneClickWorker(enable=False, runtime_feature=Mock())
    button._worker = current
    button._stopping = True
    button._apply_state(OneClickState.PREPARING, "")
    old.progress.connect(button._on_progress)
    old.finished_with.connect(button._on_finished)
    old.progress.emit(OneClickState.RUNNING, "завершаем настройку")
    old.finished_with.emit(OneClickState.RUNNING, "работает")
    app.processEvents()
    assert button.state is OneClickState.PREPARING
    assert button._worker is current
    button._worker = None
    button.stop_worker()
    button.deleteLater()
    old.deleteLater()
    current.deleteLater()


def test_disable_request_between_success_and_thread_finish_is_not_lost():
    from oneclick.ui.oneclick_worker import _OneClickWorker

    app = QApplication.instance() or QApplication([])
    feature = SimpleNamespace(is_any_running=lambda **kwargs: True)
    button = OneClickButton(get_runtime_feature=lambda: feature)
    worker = _OneClickWorker(enable=True, runtime_feature=feature)
    button._worker = worker
    worker.finished_with.connect(button._on_finished)
    button._apply_state(OneClickState.RUNNING, "работает")
    with patch.object(worker, "isRunning", return_value=True):
        worker.finished_with.emit(OneClickState.RUNNING, "работает")
        button.button.click()
        worker.finished_with.emit(OneClickState.RUNNING, "опоздавший итог")
        assert button.state is OneClickState.PREPARING
        with patch.object(button, "_start_worker") as start:
            button._on_worker_done(worker)
    start.assert_called_once_with(enable=False, feature=feature)
    assert button._pending_disable is None
    button.stop_worker()
    button.deleteLater()


def test_thread_finish_unlocks_a_running_button_even_without_its_result_signal():
    from oneclick.ui.oneclick_worker import _OneClickWorker

    app = QApplication.instance() or QApplication([])
    feature = SimpleNamespace(is_any_running=lambda **kwargs: True)
    button = OneClickButton(get_runtime_feature=lambda: feature)
    worker = _OneClickWorker(enable=True, runtime_feature=feature)
    button._worker = worker
    button._apply_state(OneClickState.RUNNING, "")
    button.button.set_click_enabled(False)
    button._on_worker_done(worker)
    assert button.button.is_click_enabled()
    button.stop_worker()
    button.deleteLater()
