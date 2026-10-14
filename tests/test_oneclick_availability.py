"""Проверка доступности не задерживает выключение и не откатывает запуск."""
from dataclasses import replace
from unittest.mock import Mock, patch

from oneclick.state import OneClickState


def test_running_is_reported_before_network_measurement():
    from oneclick.runner import OneClickRunner
    from test_oneclick_runner import _Recorder, _request
    recorder = _Recorder()
    deps = recorder.build()
    events = []
    deps.report = lambda state, message: events.append(state)
    def probe():
        assert OneClickState.RUNNING in events
        return 1, ()
    deps.probe_domains = probe
    assert OneClickRunner(deps).enable(_request()).ok


def test_failed_measurement_keeps_running_engine():
    from oneclick.runner import OneClickRunner
    from test_oneclick_runner import _Recorder, _request
    recorder = _Recorder()
    deps = recorder.build()
    deps.probe_domains = Mock(side_effect=OSError('Нет ответа'))
    outcome = OneClickRunner(deps).enable(_request())
    assert outcome.ok
    assert 'проверить не удалось' in outcome.message
    assert 'stop_dpi' not in recorder.calls
    assert 'restore_hosts' not in recorder.calls


def test_telegram_note_does_not_hide_the_running_engine():
    from oneclick.runner import OneClickRunner
    from test_oneclick_runner import _Recorder, _request
    deps = _Recorder().build()
    deps.check_telegram_ready = lambda: (True, 'Подтвердите подключение в Telegram')
    events = []
    deps.report = lambda state, message: events.append((state, message))
    assert OneClickRunner(deps).enable(replace(_request(), needs_telegram_proxy=True)).ok
    assert (OneClickState.RUNNING, 'Подтвердите подключение в Telegram') in events


def test_ui_start_finishes_without_waiting_for_sites():
    from oneclick.ui.oneclick_worker import _OneClickWorker
    from test_oneclick_runner import _Recorder, _request
    recorder = _Recorder()
    deps = recorder.build()
    deps.probe_domains = Mock(side_effect=AssertionError('Сеть в цепочке запуска'))
    worker = _OneClickWorker(enable=True, runtime_feature=Mock())
    results = []
    worker.finished_with.connect(lambda state, message: results.append(state))
    with patch('oneclick.deps.build_oneclick_deps', return_value=deps), patch('wizard.apply.build_request_from_settings', return_value=_request()):
        worker.run()
    assert worker.needs_selfcheck
    assert results == [OneClickState.RUNNING]
    deps.probe_domains.assert_not_called()


def test_cancelled_check_does_not_resolve_names():
    from diagnostics.tls_probe import ProbeCancel
    from oneclick.deps import check_availability
    token = ProbeCancel()
    token.cancel()
    with patch('socket.getaddrinfo') as resolver:
        assert check_availability(token) == ''
    resolver.assert_not_called()


def test_late_check_cannot_restore_running_after_stop():
    from oneclick.ui.button import OneClickButton
    from ui.one_shot_worker_runtime import OneShotWorkerRuntime
    button = OneClickButton.__new__(OneClickButton)
    button._availability_runtime = OneShotWorkerRuntime()
    request = button._availability_runtime.next_request_id()
    button._closed = False
    button._state = OneClickState.OFF
    button._apply_state = Mock()
    button._on_availability(request, 'Сайты открываются')
    button._apply_state.assert_not_called()
    button._state = OneClickState.RUNNING
    button._cancel_availability()
    button._on_availability(request, 'Сайты открываются')
    button._apply_state.assert_not_called()
