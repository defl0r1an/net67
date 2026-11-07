"""Настоящее окно: фильтр сохраняет выбор, отмена и ответы потоков безопасны."""

import threading
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication, QListWidget


@pytest.fixture
def vpn_page(tmp_path, monkeypatch):
    from vpn.ui.page import VpnPage
    real_refresh = VpnPage._refresh_connection_state
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("vpn.ui.page._profiles_root", lambda: tmp_path)
    monkeypatch.setattr(VpnPage, "_clear_stale_system_proxy", lambda self: None)
    monkeypatch.setattr(VpnPage, "_clear_stale_tunnel", lambda self: None)
    monkeypatch.setattr(VpnPage, "_refresh_connection_state", lambda self: None)
    monkeypatch.setattr("vpn.link_runtime.tun_mode_enabled", lambda: False)
    monkeypatch.setattr("vpn.link_runtime.active_connection", lambda: (None, "none"))
    page = VpnPage()
    page._test_refresh = real_refresh.__get__(page, VpnPage)
    yield page, app
    page.cleanup()
    page.deleteLater()
    app.processEvents()


def populate(page):
    from vpn.links import parse_link
    page._profiles = [parse_link("vless://00000000-0000-0000-0000-000000000001@cy.test:443#Кипр"),
                      parse_link("vless://00000000-0000-0000-0000-000000000002@aq.test:443#Антарктида")]
    page._refill_combo()


def wait(app, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert predicate()


def test_full_page_builds_and_filter_does_not_switch_or_lose_selection(vpn_page):
    page, _app = vpn_page
    populate(page)
    first = page._current_profile()
    page.search_edit.setText("Antarctica")
    assert len([i for i in page._row_profiles if i >= 0]) == 1
    assert page._current_profile() is first
    page.search_edit.setText("ничего подобного")
    assert page._current_profile() is first
    assert "Ничего не найдено" in page.empty_label.text()
    page.search_edit.clear()
    assert isinstance(page.profile_list, QListWidget)
    assert page.profile_combo.isHidden()


def test_ping_group_checks_hidden_members_and_keeps_selection(vpn_page, monkeypatch):
    from dataclasses import replace
    from vpn.http_probe import HttpProbeResult
    from vpn.links import parse_link
    from vpn.ui.experience import ROW_STATUS_ROLE

    page, app = vpn_page
    populate(page)
    source = "https://first.test/sub"
    page._profiles = [replace(profile, source=source) for profile in page._profiles]
    other = parse_link("vless://00000000-0000-0000-0000-000000000003@de.test:443#Германия")
    page._profiles.append(replace(other, source="https://other.test/sub"))
    page._refill_combo()
    first = page._current_profile()
    seen = []

    def probe(profile, *, should_stop):
        seen.append(profile.host)
        return HttpProbeResult(True, 42, "Ответ получен")

    monkeypatch.setattr("vpn.probing.check_profile", probe)
    page.search_edit.setText("Cyprus")
    assert len([i for i in page._row_profiles if i >= 0]) == 1
    button = page._group_check_buttons[(page._tab, source)]
    button.click()
    wait(app, lambda: page._ping_worker is None)
    assert sorted(seen) == ["aq.test", "cy.test"]
    assert page._current_profile() is first
    assert page.profile_list.item(1).data(ROW_STATUS_ROLE) == "42 мс"
    assert button.isEnabled() and page.ping_btn.isEnabled()
    seen.clear()
    page.ping_btn.click()
    wait(app, lambda: page._ping_worker is None)
    assert seen == ["cy.test"]


def test_cancel_group_stops_queued_probes(vpn_page, monkeypatch):
    from vpn.http_probe import HttpProbeResult
    from vpn.links import parse_link

    page, app = vpn_page
    page._profiles = [parse_link(f"vless://00000000-0000-0000-0000-{i:012}@server{i}.test:443#Кипр {i}")
                      for i in range(12)]
    page._refill_combo()
    started = []

    def probe(profile, *, should_stop):
        started.append(profile.host)
        deadline = time.monotonic() + 2.5
        while not should_stop() and time.monotonic() < deadline:
            time.sleep(.005)
        return HttpProbeResult(True, 42, "Ответ получен")

    monkeypatch.setattr("vpn.probing.check_profile", probe)
    button = page._group_check_buttons[(page._tab, "")]
    button.click()
    wait(app, lambda: len(started) >= 4)
    assert len(started) == 4
    assert button.isEnabled() and not page.ping_btn.isEnabled()
    button.click()
    wait(app, lambda: page._ping_worker is None)
    assert len(started) == 4
    assert not page._experience.checks
    assert button.isEnabled() and page.ping_btn.isEnabled()


def test_server_list_keeps_space_with_65_servers_and_compact_import(vpn_page):
    from PyQt6.QtWidgets import QDialog
    from vpn.links import parse_link
    from vpn.ui.connect_button import VpnConnectButton
    page, app = vpn_page
    page._profiles = [parse_link(f"vless://00000000-0000-0000-0000-{i:012}@server{i}.test:443#Кипр {i}")
                      for i in range(65)]
    page._refill_combo()
    page.resize(1920, 930)
    page.show()
    app.processEvents()
    assert page.profile_list.count() == 66  # Заголовок и 65 серверов.
    header = page.profile_list.itemWidget(page.profile_list.item(0))
    group_button = page._group_check_buttons[(page._tab, "")]
    assert header.rect().contains(group_button.geometry())
    assert page.profile_list.height() > page.height() * .6
    assert isinstance(page.connect_button, VpnConnectButton)
    assert page.connect_button.width() >= 96
    initial = page.profile_list.geometry()
    page._experience.toggle_import()
    app.processEvents()
    assert isinstance(page.add_section, QDialog) and page.add_section.isVisible()
    assert page.add_section.height() < 260
    assert page.profile_list.geometry() == initial
    page.add_section.reject()
    app.processEvents()
    assert not page.add_section.isVisible()
    assert page.profile_list.geometry() == initial


def test_lambda_worker_result_is_delivered_in_gui_thread(vpn_page):
    page, app = vpn_page
    received = []
    page._start_worker("_ping_worker", lambda: QThread.currentThread(),
                       lambda worker_thread: received.append((worker_thread, QThread.currentThread())))
    wait(app, lambda: bool(received) and page._ping_worker is None)
    assert received[0][0] is not app.thread()
    assert received[0][1] is app.thread()


def test_cancellation_stays_clickable_and_uses_cooperative_token(vpn_page, monkeypatch):
    page, app = vpn_page
    populate(page)
    monkeypatch.setattr("vpn.link_runtime.check_core_available", lambda: (True, ""))
    monkeypatch.setattr("vpn.link_runtime.is_connected", lambda: False)
    started = threading.Event()

    def connect(profile, *, should_stop, progress):
        started.set()
        progress("Ожидаем ответ…")
        while not should_stop():
            time.sleep(.005)
        return False, "Подключение отменено"

    monkeypatch.setattr("vpn.link_runtime.connect", connect)
    page._on_toggle_connection()
    wait(app, started.is_set)
    assert page.connect_button.isEnabled()
    assert page.connect_button.text() == "Отменить"
    page._on_toggle_connection()
    wait(app, lambda: page._experience.operation is None and page._tunnel_worker is None)
    assert page.connect_button.isEnabled()
    assert page.connect_button.text() == "Подключить"
    assert page.state_label.text() == "Подключение отменено"


def test_deleted_page_does_not_receive_pending_worker_callback(vpn_page):
    page, app = vpn_page
    release = threading.Event()
    seen = []
    worker = page._start_worker("_ping_worker", lambda: release.wait(2), seen.append)
    page._stop_workers()
    release.set()
    wait(app, lambda: not worker.isRunning())
    app.processEvents()
    assert seen == []


def test_cancelled_wait_does_not_wait_for_startup_deadline():
    from vpn.xray import wait_until_listening
    started = time.monotonic()
    assert not wait_until_listening(probe=lambda: False, should_stop=lambda: True, timeout_s=6)
    assert time.monotonic() - started < .1


def test_late_probe_is_saved_for_its_row_but_does_not_replace_current_card(vpn_page):
    from vpn.http_probe import HttpProbeResult
    from vpn.operation import connection_marker
    from vpn.profiles import profile_id
    page, _app = vpn_page
    populate(page)
    first = page._current_profile()
    experience = page._experience
    experience.check_request = 1
    payload = HttpProbeResult(True, 12, "Ответ сервера А"), first, "HTTPS", experience.generation, False, connection_marker(), 1
    page.profile_list.setCurrentRow(page._row_for_profile(1))
    page.ping_label.setText("Сведения о сервере Б")
    experience.checked(payload)
    assert page.ping_label.text() == "Сведения о сервере Б"
    assert profile_id(first) in experience.checks
    context = profile_id(first), experience.generation, connection_marker(), 1
    experience.check_failed("ошибка сервера А", context)
    assert page.ping_label.text() == "Сведения о сервере Б"


def test_card_names_the_server_that_disconnect_will_stop(vpn_page):
    page, _app = vpn_page
    populate(page)
    active = page._current_profile()
    page._experience.active = active
    page._experience.connected = True
    # Выбор на другой вкладке не меняет действующее соединение.
    page._visible_profiles = []
    page._row_profiles = []
    page.profile_list.blockSignals(True)
    page._group_check_buttons.clear()
    page.profile_list.clear()
    page.profile_list.blockSignals(False)
    page._experience.sync()
    assert "Кипр" in page.server_title.text()
    assert page.connect_button.text() == "Отключить"


@pytest.mark.parametrize("scope, expected", [("local", "Только локальный прокси"),
                                            ("proxy", "Сейчас: прокси приложений")])
def test_actual_scope_stays_visible_when_requested_tunnel_did_not_apply(vpn_page, monkeypatch, scope, expected):
    page, _app = vpn_page
    populate(page)
    profile = page._current_profile()
    page._experience.active = profile
    page._experience.connected = True
    monkeypatch.setattr("vpn.link_runtime.active_connection", lambda: (profile, scope))
    monkeypatch.setattr("vpn.link_runtime.tun_mode_enabled", lambda: True)
    page._experience.sync()
    assert page.scope_label.text() == expected
    assert not page.scope_label.isHidden()


def test_older_session_result_cannot_verify_a_new_connection(vpn_page):
    from vpn.http_probe import HttpProbeResult
    from vpn.operation import connection_marker
    page, _app = vpn_page
    populate(page)
    experience = page._experience
    experience.connected = True
    experience.active = page._current_profile()
    experience.check_request = 1
    experience.generation += 1
    payload = (HttpProbeResult(True, 1, "старый ответ"), experience.active, "HTTPS",
               experience.generation - 1, True, connection_marker(), 1)
    experience.checked(payload)
    assert experience.verified_generation == -1
    experience.sync()
    assert "старый ответ" not in page.ping_label.text()


def test_checking_selected_b_keeps_active_a_card_attached_to_a(vpn_page):
    from vpn.http_probe import HttpProbeResult
    from vpn.operation import connection_marker
    page, _app = vpn_page
    populate(page)
    experience = page._experience
    active, other = page._profiles
    experience.active, experience.connected = active, True
    page.profile_list.blockSignals(True)
    page.profile_list.setCurrentRow(page._row_for_profile(1))
    page.profile_list.blockSignals(False)
    experience.check_request = 1
    experience.checked((HttpProbeResult(True, 9, "Ответ сервера Б"), other, "HTTPS",
                         experience.generation, False, connection_marker(), 1))
    experience.sync()
    assert "Кипр" in page.server_title.text()
    assert "Ответ сервера Б" not in page.ping_label.text()


def test_refresh_queries_active_awg_name_independently_of_selection(vpn_page, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from vpn.tunnel import TunnelState, TunnelStatus
    page, _app = vpn_page
    populate(page)
    active = SimpleNamespace(name="Рабочий туннель", endpoint="wg.example:51820", protocol="WireGuard", raw="")
    monkeypatch.setattr("vpn.link_runtime.is_connected", lambda: False)
    monkeypatch.setattr("vpn.tunnel_runtime.active_connection", lambda: (active, "work-tunnel"))
    get_status = Mock(return_value=TunnelStatus(TunnelState.CONNECTED))
    get_stats = Mock(return_value=None)
    monkeypatch.setattr("vpn.tunnel_runtime.get_status", get_status)
    monkeypatch.setattr("vpn.tunnel_runtime.get_stats", get_stats)
    monkeypatch.setattr(page, "_start_worker", lambda attr, call, done, failed: done(call()))
    page._test_refresh()
    get_status.assert_called_once_with("work-tunnel")
    get_stats.assert_called_once_with("work-tunnel")
    assert page._experience.active is active
    assert "Рабочий туннель" in page.server_title.text()
    assert "Кипр" in page.selection_label.text()
    assert page.connect_button.text() == "Отключить"


def test_selected_row_background_covers_metadata_too(vpn_page):
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QColor
    from vpn.ui.experience import ROW_STATUS_ROLE
    page, app = vpn_page
    populate(page)
    view = page.profile_list
    view.setStyleSheet("QListWidget { background: #202020; } QListWidget::item:selected { background: #ffffff; color: #101010; }")
    item = view.item(view.currentRow())
    item.setData(ROW_STATUS_ROLE, "Подключён · HTTPS · 164 мс")
    item.setSizeHint(QSize(0, 46))
    page.resize(1000, 800)
    page.show()
    app.processEvents()
    rect = view.visualItemRect(item)
    image = view.viewport().grab().toImage()
    # Правая часть строки вне букв должна иметь ту же подложку, что и имя.
    x, y = rect.right() - 18, rect.top() + 7
    color = image.pixelColor(x, y)
    assert color.red() > 235 and color.green() > 235 and color.blue() > 235, color.name()


def test_failed_switch_does_not_rename_a_preserved_active_connection(vpn_page, monkeypatch):
    from unittest.mock import Mock
    from vpn.operation import VpnOperation
    page, _app = vpn_page
    populate(page)
    active, other = page._profiles
    monkeypatch.setattr("vpn.link_runtime.is_connected", lambda: True)
    monkeypatch.setattr("vpn.link_runtime.active_connection", lambda: (active, "proxy"))
    monkeypatch.setattr(page, "_error", Mock())
    check = Mock()
    monkeypatch.setattr(page._experience, "check", check)
    page._experience.operation = VpnOperation(other)
    page._experience.finished((False, "Ядро не найдено"))
    assert page._experience.active is active
    assert "Кипр" in page.server_title.text()
    check.assert_not_called()
