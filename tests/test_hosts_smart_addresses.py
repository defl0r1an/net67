"""Умная проверка адресов hosts — только когда человек включил её в редакторе.

Движок адресов (hosts.address_engine) в net67 работал только по кнопке
«Обновить адреса». У апстрима он ходит в сеть сам: раз в шесть часов и
после каждого переключения сервиса. На рабочих компьютерах программа
без спроса не должна ни перебирать адреса, ни переписывать hosts, поэтому
здесь это выключатель, и выключен он по умолчанию.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from test_hosts_page_draft import _manual_snapshot  # noqa: E402


class SmartCheckCommandTests(unittest.TestCase):
    def _run(self, *, enabled: bool, changed: bool):
        from hosts import commands
        from hosts.state import HostsCommandResult
        from utils.probe_gate import Why

        report = SimpleNamespace(changed=changed, checked=3, silent=False)
        check = Mock(return_value=report)
        refresh = Mock(return_value=HostsCommandResult(success=True, message="переписано", changed=True))
        with (
            patch("settings.store.get_hosts_smart_addresses", return_value=enabled),
            patch.object(commands, "check_addresses", check),
            patch.object(commands, "refresh_applied_selection", refresh),
            patch.object(commands, "describe_address_check", return_value=""),
        ):
            result = commands.smart_check_applied(why=Why.SCHEDULE)
        return result, check, refresh

    def test_switched_off_goes_nowhere(self) -> None:
        result, check, refresh = self._run(enabled=False, changed=True)

        check.assert_not_called()
        refresh.assert_not_called()
        self.assertFalse(result.changed)

    def test_better_order_rewrites_only_the_net67_block(self) -> None:
        result, check, refresh = self._run(enabled=True, changed=True)

        check.assert_called_once()
        refresh.assert_called_once()
        self.assertTrue(result.changed)

    def test_nothing_found_leaves_the_file_alone(self) -> None:
        _result, check, refresh = self._run(enabled=True, changed=False)

        check.assert_called_once()
        refresh.assert_not_called()

    def test_smart_addresses_are_off_by_default(self) -> None:
        from settings.normalize import normalize_settings

        self.assertFalse(normalize_settings({})["hosts"]["smart_addresses"])


class HostsPageSmartToggleTests(unittest.TestCase):
    def _page(self, *, smart_enabled: bool):
        from hosts.ui.page import HostsPage

        snapshot = _manual_snapshot()
        self.rechecks: list[tuple[str, ...]] = []
        self.saved: list[bool] = []
        feature = SimpleNamespace(
            peek_page_snapshot=lambda: snapshot,
            create_snapshot_worker=lambda request_id, parent=None: None,
            create_apply_worker=lambda request_id, selection, adobe, parent=None: None,
            create_smart_addresses_load_worker=lambda request_id, parent=None: None,
            create_smart_addresses_save_worker=lambda request_id, enabled, parent=None: self.saved.append(enabled),
            create_smart_recheck_worker=lambda request_id, names, parent=None: self.rechecks.append(tuple(names)),
        )
        page = HostsPage(deps=SimpleNamespace(hosts_feature=feature, open_file_page=lambda: None))
        self.addCleanup(page.deleteLater)
        self.apply_callbacks: list[dict] = []

        def _start_apply(**kwargs):
            self.apply_callbacks.append(kwargs)
            return len(self.apply_callbacks), None

        def _start_now(**kwargs):
            kwargs["worker_factory"](1)
            return 1, None

        for target, side_effect in (
            (page._apply_runtime, _start_apply),
            (page._smart_save_runtime, _start_now),
            (page._smart_recheck_runtime, _start_now),
        ):
            patcher = patch.object(target, "start_qthread_worker", side_effect=side_effect)
            patcher.start()
            self.addCleanup(patcher.stop)
        for runtime in (page._apply_runtime, page._smart_runtime, page._smart_recheck_runtime):
            current = patch.object(runtime, "is_current", return_value=True)
            current.start()
            self.addCleanup(current.stop)
        reread = patch.object(page, "_request_snapshot")
        reread.start()
        self.addCleanup(reread.stop)
        page._set_snapshot(snapshot)
        page._on_smart_addresses_loaded(1, smart_enabled)
        return page

    def test_toggle_starts_disabled_until_setting_is_read(self) -> None:
        from hosts.ui.page import HostsPage

        QApplication.instance() or QApplication([])
        feature = SimpleNamespace(peek_page_snapshot=lambda: None)
        page = HostsPage(deps=SimpleNamespace(hosts_feature=feature, open_file_page=lambda: None))
        self.addCleanup(page.deleteLater)

        self.assertFalse(page.smart_addresses_toggle.isEnabled())
        self.assertFalse(page.smart_addresses_toggle.isChecked())

    def test_toggle_saves_the_choice(self) -> None:
        QApplication.instance() or QApplication([])
        page = self._page(smart_enabled=False)

        # Как щелчок человека: программная установка сигнала не шлёт.
        page.smart_addresses_toggle._switch_button.setChecked(True)

        self.assertEqual(self.saved, [True])

    def test_enabled_service_is_rechecked_after_write_only_when_switched_on(self) -> None:
        QApplication.instance() or QApplication([])
        for smart, expected in ((True, [("Direct",)]), (False, [])):
            with self.subTest(smart=smart):
                page = self._page(smart_enabled=smart)
                page._on_tile_activated("Direct")
                self.apply_callbacks[-1]["on_loaded"](
                    len(self.apply_callbacks),
                    SimpleNamespace(
                        success=True,
                        snapshot=_manual_snapshot(block_lines=("4.4.4.4 direct.example",), direct="hosts"),
                        message="",
                    ),
                )
                self.assertEqual(self.rechecks, expected)

    def test_failed_write_does_not_recheck(self) -> None:
        QApplication.instance() or QApplication([])
        page = self._page(smart_enabled=True)
        page._on_tile_activated("Direct")

        with patch("hosts.ui.page.InfoBar"):
            self.apply_callbacks[-1]["on_loaded"](
                len(self.apply_callbacks), SimpleNamespace(success=False, snapshot=None, message="нет прав")
            )

        self.assertEqual(self.rechecks, [])


if __name__ == "__main__":
    unittest.main()
