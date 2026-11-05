"""Отмена старой страницы не останавливает новый сеанс; имя AWG сохраняется."""

import threading
from types import SimpleNamespace
from unittest.mock import patch


def test_old_cancel_finishes_cleanup_before_new_connect_can_start(monkeypatch):
    from vpn import link_runtime
    entered = threading.Event()
    release = threading.Event()
    cancel = threading.Event()
    events = []
    old_serial = link_runtime._CONNECTION_SERIAL

    def connect(profile, **options):
        events.append("start-" + profile)
        if profile == "A":
            entered.set()
            assert release.wait(3)
        return True, profile

    def disconnect():
        events.append("stop-A")
        return True, "Отключено"

    monkeypatch.setattr(link_runtime, "_connect", connect)
    monkeypatch.setattr(link_runtime, "_disconnect", disconnect)
    monkeypatch.setattr(link_runtime, "_CONNECTION_SERIAL", old_serial)
    a = threading.Thread(target=lambda: link_runtime.connect("A", should_stop=cancel.is_set))
    b = threading.Thread(target=lambda: link_runtime.connect("B"))
    a.start()
    assert entered.wait(3)
    cancel.set()
    b.start()
    release.set()
    a.join(3); b.join(3)
    assert not a.is_alive() and not b.is_alive()
    assert events == ["start-A", "stop-A", "start-B"]


def test_disconnect_for_an_old_session_does_not_stop_a_new_one(monkeypatch):
    from vpn import link_runtime
    monkeypatch.setattr(link_runtime, "_CONNECTION_SERIAL", 9)
    with patch.object(link_runtime, "_disconnect") as stop:
        ok, message = link_runtime.disconnect(expected_serial=8)
    assert not ok and "изменилось" in message
    stop.assert_not_called()
