"""Обновление: надпись перед закрытием, перезапуск установщиком, защита от раннего запуска.

При обновлении net67 молча закрывался и сам не открывался (запуск после
установки стоял с skipifsilent, а обновление идёт с /VERYSILENT). Человек
открывал программу вручную посреди установки — установщик в это время
убивает net67.exe и заменяет файлы, открытая программа держит свой exe, и
замена с /SUPPRESSMSGBOXES срывалась молча.
"""

from __future__ import annotations

import os
import re
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


class ClosingNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_text_says_it_reopens_and_not_to_launch(self) -> None:
        from updater.ui.closing_notice import closing_notice_text

        title, body = closing_notice_text("0.13.67")
        self.assertIn("0.13.67", title)
        self.assertIn("откроется сам", body)
        self.assertIn("не запускайте", body)

    def test_notice_is_shown_on_top_without_stealing_focus(self) -> None:
        from PyQt6.QtCore import Qt

        from updater.ui.closing_notice import show_update_closing_notice

        notice = show_update_closing_notice(None, "0.13.67")
        self.addCleanup(notice.deleteLater)
        self.assertTrue(notice.isVisible())
        self.assertTrue(notice.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(notice.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        self.assertFalse(notice.grab().isNull())

    def _runtime(self):
        from updater.update_page_runtime import UpdateDownloadState, UpdatePageRuntime

        runtime = UpdatePageRuntime.__new__(UpdatePageRuntime)
        runtime._cleanup_in_progress = False
        runtime._download_state = UpdateDownloadState(is_installing=True)
        runtime._download_state.handoff = SimpleNamespace(version="0.13.67")
        runtime._view = Mock()
        runtime._update_installer_runtime = Mock()
        runtime._updater_feature = Mock()
        return runtime

    def test_notice_comes_first_and_installer_after_the_lead(self) -> None:
        """Надпись — до установщика: после него Restart Manager закрывает net67 сам."""
        from updater.update_page_runtime import UpdatePageRuntime
        from updater.ui.closing_notice import UPDATE_CLOSING_NOTICE_LEAD_MS

        runtime = self._runtime()
        scheduled = []
        with (
            patch("updater.ui.closing_notice.show_update_closing_notice", return_value=Mock()) as shown,
            patch(
                "updater.update_page_runtime.QTimer.singleShot",
                side_effect=lambda delay, callback: scheduled.append((delay, callback)),
            ),
        ):
            UpdatePageRuntime._start_update_installer_stage(runtime)

        shown.assert_called_once()
        runtime._update_installer_runtime.start_qobject_worker.assert_not_called()
        self.assertEqual([delay for delay, _ in scheduled], [UPDATE_CLOSING_NOTICE_LEAD_MS])
        scheduled[0][1]()
        runtime._update_installer_runtime.start_qobject_worker.assert_called_once()

    def test_failed_update_takes_the_promise_back(self) -> None:
        from updater.update_page_runtime import UpdatePageRuntime

        runtime = self._runtime()
        runtime._closing_notice = Mock()
        runtime._on_download_failed = Mock()
        runtime._download_state.dpi_stopped_by_update = False
        notice = runtime._closing_notice

        UpdatePageRuntime._fail_update_pipeline(runtime, "сеть")

        notice.close.assert_called_once_with()
        self.assertIsNone(runtime._closing_notice)


class SetupMutexTests(unittest.TestCase):
    def test_running_setup_is_seen_through_its_mutex(self) -> None:
        from startup.single_instance import create_mutex, release_mutex, setup_is_running

        name = f"net67-test-setup-{uuid.uuid4().hex}"
        self.assertFalse(setup_is_running((name,)))
        handle, _ = create_mutex(name)
        try:
            self.assertTrue(setup_is_running((name,)))
        finally:
            release_mutex(handle)
        self.assertFalse(setup_is_running((name,)))

    def test_wait_ends_when_setup_finishes(self) -> None:
        from startup.single_instance import wait_for_setup_to_finish

        states = iter([True, True, False])
        self.assertTrue(wait_for_setup_to_finish(timeout_s=5, poll_s=0.01, is_running=lambda: next(states)))
        self.assertFalse(wait_for_setup_to_finish(timeout_s=0.05, poll_s=0.01, is_running=lambda: True))


class ShellGuardTests(unittest.TestCase):
    def test_manual_launch_during_setup_exits_at_once(self) -> None:
        from main import shell

        with (
            patch("startup.single_instance.setup_is_running", return_value=True),
            patch("startup.single_instance.wait_for_setup_to_finish") as wait,
        ):
            with self.assertRaises(SystemExit):
                shell._respect_running_setup(["net67.exe"])
        wait.assert_not_called()

    def test_launch_by_installer_waits_for_it(self) -> None:
        from main import shell

        with (
            patch("startup.single_instance.setup_is_running", return_value=True),
            patch("startup.single_instance.wait_for_setup_to_finish", return_value=True) as wait,
        ):
            shell._respect_running_setup(["net67.exe", "--after-update"])
        wait.assert_called_once_with()

    def test_no_setup_no_delay(self) -> None:
        from main import shell

        with patch("startup.single_instance.setup_is_running", return_value=False):
            shell._respect_running_setup(["net67.exe"])


class InstallerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.iss = (ROOT / "installer" / "net67.iss").read_text(encoding="utf-8")

    def test_setup_holds_the_mutex_the_app_checks(self) -> None:
        from startup.single_instance import SETUP_MUTEX_NAMES

        line = re.search(r"^SetupMutex=(.+)$", self.iss, re.M)
        self.assertIsNotNone(line)
        self.assertEqual(tuple(n.strip() for n in line.group(1).split(",")), SETUP_MUTEX_NAMES)

    def test_auto_update_reopens_the_app(self) -> None:
        """Без этой строки после тихого обновления программа не открывалась."""
        from startup.single_instance import AFTER_UPDATE_ARG

        entry = re.search(r"^Filename:.*Parameters: \"--after-update\".*\n.*$", self.iss, re.M)
        self.assertIsNotNone(entry)
        text = entry.group(0)
        self.assertIn(AFTER_UPDATE_ARG, text)
        self.assertIn("Check: IsAutoUpdate", text)
        self.assertNotIn("skipifsilent", text)
        self.assertIn("shellexec", text)
        self.assertIn("function IsAutoUpdate(): Boolean;", self.iss)

    def test_updater_passes_the_flag_the_installer_checks(self) -> None:
        source = (ROOT / "src" / "updater" / "update_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('"/AUTOUPDATE"', source)
        self.assertIn("'/AUTOUPDATE'", self.iss)


if __name__ == "__main__":
    unittest.main()
