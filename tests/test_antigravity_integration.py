"""Настоящий протокол и очередь проверяются без включения обхода Windows."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]


class FakeController(QObject):
    received = pyqtSignal(dict)
    failed = pyqtSignal(str)
    busy_changed = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.busy = False
        self.send = Mock(return_value=True)
        self.start = Mock(return_value=True)
        self.stop = Mock()


class AntigravityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_pipe_reassembles_split_utf8_and_keeps_off_note_off(self):
        from antigravity.controller import AntigravityController

        controller = AntigravityController(directory=Path("missing"))
        events = []
        controller.received.connect(events.append)
        payload = json.dumps({"event": "log", "message": "Проверяю"}, ensure_ascii=False).encode("utf-8") + b"\n"
        for byte in payload:
            controller.feed_output(bytes([byte]))
        self.assertEqual(events, [{"event": "log", "message": "Проверяю"}])
        controller.feed_output(b'null\nnot-json\n')
        self.assertEqual(events[-1]["message"], "not-json")

    def test_intermediate_snapshot_does_not_unlock_action(self):
        from antigravity.controller import AntigravityController

        controller = AntigravityController(directory=Path("missing"))
        controller._initializing = True
        controller._set_busy(True)
        controller.feed_output(b'{"event":"status","status":{}}\n')
        self.assertFalse(controller.busy)
        controller._set_busy(True)
        controller._active_request = 7
        controller.feed_output(b'{"event":"status","status":{}}\n')
        self.assertTrue(controller.busy)
        controller.feed_output(b'{"event":"busy","message":null}\n')
        self.assertTrue(controller.busy)
        controller.feed_output(b'{"event":"completed","request_id":6}\n')
        self.assertTrue(controller.busy)
        controller.feed_output(b'{"event":"completed","request_id":7}\n')
        self.assertFalse(controller.busy)

    def test_page_renders_system_state_without_emitting_commands(self):
        from antigravity.ui.page import AntigravityPage

        controller = FakeController()
        page = AntigravityPage(controller=controller)
        self.addCleanup(page.cleanup)
        status = {"caps": {"bypass": {"on": True}, "dns_rotation": {"on": False, "note": "только первый сервер"}},
                  "providers": [{"name": "DNS A", "enabled": True}, {"name": "DNS B", "enabled": False}]}
        controller.received.emit({"event": "status", "status": status})
        main = {tile.key: tile for tile in page.main_tiles._tiles}
        extra = {tile.key: tile for tile in page.advanced_tiles._tiles}
        self.assertTrue(main["bypass"].is_on)
        self.assertFalse(extra["dns_rotation"].is_on)
        self.assertEqual(extra["dns_rotation"].note, "только первый сервер")
        controller.send.assert_not_called()
        page.advanced_tiles.activated.emit("dns_rotation")
        controller.send.assert_called_once_with("set", cap="dns_rotation", on=True)
        controller.send.reset_mock()
        controller.received.emit({"event": "status", "status": status})
        controller.send.assert_not_called()

    def test_command_error_keeps_the_page_usable(self):
        from antigravity.ui.page import AntigravityPage

        controller = FakeController()
        page = AntigravityPage(controller=controller)
        self.addCleanup(page.cleanup)
        controller.received.emit({"event": "status", "status": {}})
        controller.received.emit({"event": "error", "message": "Папка не найдена"})
        self.assertTrue(page._ready)
        self.assertTrue(page.refresh_button.isEnabled())

    def test_opening_and_touring_page_never_start_controller_or_apply_changes(self):
        from antigravity.ui.page import AntigravityPage

        controller = FakeController()
        page = AntigravityPage(controller=controller, open_hosts=lambda: None)
        self.addCleanup(page.cleanup)
        page.on_page_activated()
        page.on_page_activated()
        page._set_section("network")
        for state in ("main", "log", "main"):
            page.onboarding_set_state(state)
            self.assertTrue(page.onboarding_target("controls"))
            page.onboarding_set_state(None)
            self.assertEqual(page._section, "network")
        controller.start.assert_not_called()
        controller.send.assert_not_called()
        page.refresh_button.click()
        controller.start.assert_called_once_with()
        controller.send.assert_not_called()

    def test_repair_is_available_only_when_diagnosis_requires_it(self):
        from antigravity.ui.page import AntigravityPage

        controller = FakeController()
        page = AntigravityPage(controller=controller)
        self.addCleanup(page.cleanup)
        controller.received.emit({"event": "status", "status": {}})
        controller.received.emit({"event": "headline", "action": "EnableAll"})
        self.assertTrue(page.repair_button.isHidden())
        self.assertFalse(page.repair_button.isEnabled())
        controller.received.emit({"event": "headline", "action": "Repair"})
        self.assertFalse(page.repair_button.isHidden())
        self.assertTrue(page.repair_button.isEnabled())

    def test_enable_all_is_always_visible_and_cold_click_checks_then_sends_once(self):
        from antigravity.ui.page import AntigravityPage

        controller = FakeController()
        page = AntigravityPage(controller=controller)
        self.addCleanup(page.cleanup)
        self.assertFalse(page.enable_button.isHidden())
        self.assertTrue(page.enable_button.isEnabled())
        page.enable_button.click()
        controller.start.assert_called_once_with()
        controller.send.assert_not_called()
        controller.received.emit({"event": "status", "status": {"installs": [{"path": "C:/Antigravity"}]}})
        controller.send.assert_called_once_with("enable_all")
        controller.received.emit({"event": "status", "status": {}})
        controller.send.assert_called_once_with("enable_all")
        for action in (None, "Repair", "Verify"):
            controller.received.emit({"event": "headline", "action": action})
            self.assertFalse(page.enable_button.isHidden())

    def test_failed_preparation_never_enables_later_and_no_install_is_not_started(self):
        from antigravity.ui.page import AntigravityPage

        controller = FakeController()
        page = AntigravityPage(controller=controller)
        self.addCleanup(page.cleanup)
        page.enable_button.click()
        controller.failed.emit("Не удалось проверить")
        controller.received.emit({"event": "status", "status": {}})
        controller.send.assert_not_called()
        page._ready = False
        page.enable_button.click()
        controller.received.emit({"event": "status", "status": {"installs": [{"path": None}]}})
        controller.send.assert_not_called()
        self.assertFalse(page.enable_button.isEnabled())
        self.assertIsNone(page._requested_action)

    def test_cold_enable_all_does_not_reapply_already_enabled_functions(self):
        from antigravity.ui.page import AntigravityPage

        controller = FakeController()
        page = AntigravityPage(controller=controller)
        self.addCleanup(page.cleanup)
        page.enable_button.click()
        controller.received.emit({"event": "status", "status": {
            "caps": {name: {"on": True} for name in ("client_patch", "watchdog", "dns", "local_proxy", "builtin_exits", "group_proxy")},
            "installs": [{"path": "C:/Antigravity"}],
        }})
        controller.send.assert_not_called()
        self.assertFalse(page.enable_button.isEnabled())
        self.assertIsNone(page._requested_action)
        self.assertEqual(page._pending_cap, "")

    def test_hosts_link_focuses_service_before_showing_page(self):
        from main.window_page_actions import open_hosts_service
        from app.page_names import PageName
        from hosts.ui.page import HostsPage

        window = object()
        with patch("ui.window_adapter.send_page_command", return_value=True) as send, patch("main.window_page_actions.show_page", return_value=True) as show:
            self.assertTrue(open_hosts_service(window, "Antigravity"))
            send.assert_called_once_with(window, PageName.HOSTS, "focus_service", {"service": "Antigravity"}, ensure=True)
            show.assert_called_once_with(window, PageName.HOSTS)
        page = HostsPage.__new__(HostsPage)
        page.focus_service = Mock()
        self.assertTrue(page.handle_page_command("focus_service", {"service": "Antigravity"}))
        page.focus_service.assert_called_once_with("Antigravity")

    def test_hosts_jump_waits_for_catalog_and_scrolls_full_list_without_writing(self):
        from types import SimpleNamespace
        from hosts.ui.page import HostsPage
        from hosts.page_snapshot import HostsPageSnapshot, HostsServiceEntry, CATEGORY_AI

        entries = tuple(HostsServiceEntry(name, CATEGORY_AI, "fa5s.globe", None, ("dns",), "dns")
                        for name in [*(f"Сервис {i}" for i in range(60)), "Google Antigravity", "После Antigravity"])
        snapshot = HostsPageSnapshot(entries, (("dns", "DNS"),), None)
        for loaded_first in (False, True):
            with self.subTest(loaded_first=loaded_first):
                feature = SimpleNamespace(peek_page_snapshot=lambda: None, create_apply_worker=Mock())
                page = HostsPage(deps=SimpleNamespace(hosts_feature=feature, open_file_page=lambda: None))
                page.resize(700, 450)
                with patch.object(page, "_request_snapshot"):
                    if loaded_first:
                        page._set_snapshot(snapshot)
                        page.show()
                        self.app.processEvents()
                        page.search_edit.setText("Сервис 1")
                    page.focus_service("Antigravity")
                    if not loaded_first:
                        page.show()
                        self.app.processEvents()
                        self.assertEqual(page._focus_service_pending, "antigravity")
                        page._set_snapshot(snapshot)
                    for _ in range(20):
                        self.app.processEvents()
                    self.assertEqual(page.search_edit.text(), "")
                    self.assertTrue(page.search_edit.isHidden())
                    self.assertEqual(sum(tile.kind == "tile" for tile in page.tiles.tiles()), len(entries) + 1)
                    self.assertGreater(page.verticalScrollBar().value(), 0)
                    rect = page.tiles.tile_rect("Google Antigravity")
                    center = page.tiles.mapTo(page.viewport(), rect.center())
                    self.assertTrue(page.viewport().rect().contains(center), (center, page.verticalScrollBar().value()))
                    self.assertEqual(page.tiles.tiles()[page.tiles._cursor].key, "Google Antigravity")
                    self.assertFalse(page._draft.has_user_changes())
                    feature.create_apply_worker.assert_not_called()
                page.cleanup()
                page.close()
                page.deleteLater()

    def test_sections_preserve_controls_and_hosts_link_remains_available_during_check(self):
        from antigravity.ui.page import AntigravityPage

        controller = FakeController()
        open_hosts = Mock()
        page = AntigravityPage(controller=controller, open_hosts=open_hosts)
        self.addCleanup(page.cleanup)
        page._busy_changed(True, "Проверяю…")
        page.hosts_button.click()
        open_hosts.assert_called_once_with()
        page._set_section("network")
        self.assertTrue(page.main_card.isHidden())
        self.assertFalse(page.advanced_card.isHidden())
        page.route_code.setText("незавершённый ввод")
        page._set_section("log")
        page._set_section("network")
        self.assertEqual(page.route_code.text(), "незавершённый ввод")
        controller.send.assert_not_called()

    def test_hosts_jump_in_real_window_survives_first_load_and_resize(self):
        script = r'''
from unittest.mock import patch
from main.qt_runtime import ensure_qt_runtime
app = ensure_qt_runtime()
from main.application_controller import ApplicationController
from main.window import LupiDPIApp
from app.page_names import PageName
from ui.window_adapter import ensure_page, show_page
from hosts.page_snapshot import build_page_snapshot
controller = ApplicationController(window_cls=LupiDPIApp, start_in_tray=True)
window = controller.create_window()
window.build_ui(1280, 900)
for _ in range(20): app.processEvents()
with patch('hosts.ui.page.HostsPage._request_snapshot'):
    hosts = ensure_page(window, PageName.HOSTS)
    antigravity = ensure_page(window, PageName.ANTIGRAVITY)
    snapshot = build_page_snapshot(hosts_text='', hosts_path='hosts', hosts_exists=True,
                                   readable=True, read_only=False, ipv6_available=True)
    for width in (960, 1280):
        window.resize(width, 900)
        window.show()
        show_page(window, PageName.ANTIGRAVITY)
        for _ in range(20): app.processEvents()
        antigravity.hosts_button.click()
        if hosts._snapshot is None:
            for _ in range(10): app.processEvents()
            assert hosts._focus_service_pending == 'antigravity'
            hosts._set_snapshot(snapshot)
        for _ in range(40): app.processEvents()
        rect = hosts.tiles.tile_rect('Google Antigravity')
        center = hosts.tiles.mapTo(hosts.viewport(), rect.center())
        assert hosts.viewport().rect().contains(center), (width, center, hosts.verticalScrollBar().value())
        assert hosts.tiles.tiles()[hosts.tiles._cursor].key == 'Google Antigravity'
        assert hosts.search_edit.text() == ''
        assert not hosts._draft.has_user_changes()
print('JUMP-OK', flush=True)
import os
if os.name == 'nt':
    # Показанное окно Qt иногда держит DLL при штатном _exit. Этот тест
    # проверяет прокрутку, поэтому завершаем только его изолированный процесс.
    import ctypes
    api = ctypes.windll.kernel32
    api.GetCurrentProcess.restype = ctypes.c_void_p
    api.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    api.TerminateProcess(api.GetCurrentProcess(), 0)
os._exit(0)
'''
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT / "src"))
        result = subprocess.run([os.sys.executable, "-c", script], cwd=ROOT, env=env,
                                capture_output=True, timeout=90)
        output = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
        self.assertEqual(result.returncode, 0, output[-3000:])
        self.assertIn("JUMP-OK", output)

    def test_report_requests_do_not_mix_and_write_failure_keeps_controls(self):
        from antigravity.ui.page import AntigravityPage

        controller = FakeController()
        page = AntigravityPage(controller=controller)
        self.addCleanup(page.cleanup)
        controller.received.emit({"event": "status", "status": {}})
        page._copy_report()
        page._copy_report()
        controller.send.assert_called_once_with("report")
        self.assertFalse(page.copy_button.isEnabled())
        controller.received.emit({"event": "report", "text": "Отчёт"})
        self.assertFalse(page._report_pending)
        self.assertTrue(page.copy_button.isEnabled())
        page._report_path = "report.txt"
        with patch("pathlib.Path.write_text", side_effect=OSError("нет доступа")):
            page._accept_report("Отчёт")
        self.assertTrue(page._ready)
        self.assertTrue(page.enable_button.isEnabled())
        page._copy_report()
        page._failed("Контроллер остановился")
        self.assertFalse(page._report_pending)
        controller.received.emit({"event": "status", "status": {}})
        self.assertTrue(page.copy_button.isEnabled())

    def test_shutdown_queues_stop_without_killing_controller(self):
        from antigravity.controller import AntigravityController

        controller = AntigravityController(directory=Path("missing"))
        process = Mock()
        process.poll.return_value = None
        process.stdin.closed = False
        controller.process = process
        controller.stop()
        process.stdin.write.assert_called_once_with(b'{"command":"stop"}\n')
        process.stdin.close.assert_called_once()
        process.kill.assert_not_called()
        process.terminate.assert_not_called()

    def test_route_is_in_tools_and_catalog_has_antigravity(self):
        from app.page_names import PageName
        from ui.navigation.schema import get_page_spec, get_sidebar_pages_for_method
        from ui.page_composition import validate_page_deps_builder_coverage

        self.assertEqual(get_page_spec(PageName.ANTIGRAVITY).sidebar_group, "system")
        self.assertIn(PageName.ANTIGRAVITY, get_sidebar_pages_for_method("zapret2", sidebar_group="system", advanced=True))
        validate_page_deps_builder_coverage(PageName)
        catalog = json.loads((ROOT / "json/hosts_catalog/dns/114_google_antigravity.json").read_text(encoding="utf-8"))
        self.assertIn("antigravity.google", catalog["main"])

    def test_pinned_binaries_and_readonly_backend_startup(self):
        directory = ROOT / "bin/antigravity"
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), expected)
        with tempfile.TemporaryDirectory(prefix="net67-ag-test-") as temporary:
            env = dict(os.environ)
            for key in ("LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "ProgramData"):
                env[key] = temporary
            result = subprocess.run([str(directory / "net67_antigravity.exe")],
                                    input=b'{"command":"refresh","request_id":11}\n{"command":"stop"}\n', capture_output=True,
                                    env=env, timeout=90, cwd=str(directory))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            events = []
            for line in result.stdout.splitlines():
                try:
                    events.append(json.loads(line))
                except (ValueError, UnicodeDecodeError):
                    pass
            snapshots = [event["status"] for event in events if event.get("event") == "status"]
            self.assertTrue(snapshots, result.stdout.decode("utf-8", "replace"))
            self.assertIn("bypass", snapshots[0]["caps"])
            self.assertFalse(snapshots[0]["caps"]["builtin_exits"]["on"])
            self.assertFalse(snapshots[0]["caps"]["group_proxy"]["on"])
            self.assertEqual([event["request_id"] for event in events if event.get("event") == "completed"], [11])
            self.assertFalse((Path(temporary) / "AGUnlocker/settings.json").exists())

    def test_hosts_marks_separate_antigravity_block(self):
        from hosts.hosts_blocks import BLOCK_ANTIGRAVITY, BLOCK_USER, parse_hosts_blocks

        blocks = parse_hosts_blocks(
            "127.0.0.1 localhost\n# AG_UNLOCKER_HOSTS_BEGIN build-identifier\n"
            "192.0.2.1 daily-cloudcode-pa.googleapis.com\n# AG_UNLOCKER_HOSTS_END\n"
            "192.0.2.2 intranet.example\n"
        )
        by_kind = {block.kind: block.lines for block in blocks}
        self.assertEqual(by_kind[BLOCK_ANTIGRAVITY], ("192.0.2.1 daily-cloudcode-pa.googleapis.com",))
        self.assertEqual(by_kind[BLOCK_USER], ("127.0.0.1 localhost", "192.0.2.2 intranet.example"))
