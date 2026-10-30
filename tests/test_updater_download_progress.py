"""Ожидание сети и единые показания независимо от видимости диалога."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from updater.download_progress import DownloadProgress, format_speed
from updater.ui import download_view
from updater.ui.changelog_card import ChangelogCard
from updater.ui.update_dialog import UpdateOfferDialog
from updater.update_page_runtime import UpdatePageRuntime


class DownloadProgressTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.progress = DownloadProgress(clock=lambda: self.now)
        self.progress.set_stage("download", "Скачивание обновления…")

    def test_no_first_byte_then_waiting_without_invented_speed(self):
        self.now = 6
        snapshot = self.progress.snapshot()
        self.assertTrue(snapshot.waiting)
        self.assertEqual(snapshot.status, "Ждём ответа сервера…")
        self.assertIsNone(snapshot.speed)
        self.assertIsNone(snapshot.eta_seconds)

    def test_idle_clears_previous_speed_and_eta_and_new_bytes_restore_them(self):
        self.progress.update(0, 0, 100_000)
        self.now = 1
        self.progress.update(10, 10_000, 100_000)
        self.assertGreater(self.progress.snapshot().speed, 0)
        self.now = 7
        snapshot = self.progress.snapshot()
        self.assertTrue(snapshot.waiting)
        self.assertIsNone(snapshot.speed)
        self.assertIsNone(snapshot.eta_seconds)
        self.now = 8
        self.progress.update(20, 20_000, 100_000)
        snapshot = self.progress.snapshot()
        self.assertFalse(snapshot.waiting)
        self.assertGreater(snapshot.speed, 0)
        self.assertIsNotNone(snapshot.eta_seconds)

    def test_small_regular_transfers_do_not_look_stalled(self):
        self.progress.update(0, 0, 100_000)
        for second in range(1, 15):
            self.now = second
            self.progress.update(second, second * 1000, 100_000)
            self.assertFalse(self.progress.snapshot().waiting)
        self.assertEqual(format_speed(1024), "1.0 КБ/с")

    def test_saved_prefix_is_not_counted_as_fresh_download_speed(self):
        self.now = 10
        self.progress.update(50, 50_000, 100_000)
        self.assertIsNone(self.progress.snapshot().speed)
        self.now = 11
        self.progress.update(51, 51_000, 100_000)
        self.assertEqual(self.progress.snapshot().speed, 1000)

    def test_verification_does_not_turn_into_waiting_for_network(self):
        self.progress.update(100, 100_000, 100_000)
        self.progress.set_stage("verify", "Проверка SHA-256…")
        self.now = 50
        snapshot = self.progress.snapshot()
        self.assertFalse(snapshot.waiting)
        self.assertEqual(snapshot.status, "Проверка SHA-256…")
        self.assertIsNone(snapshot.eta_seconds)

    def test_restart_from_zero_resets_speed_without_negative_estimate(self):
        self.progress.update(50, 50_000, 100_000)
        self.now = 1
        self.progress.update(0, 0, 100_000)
        self.assertIsNone(self.progress.snapshot().speed)


class DownloadProgressViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host = QWidget()
        self.host.resize(1200, 900)
        self.host.show()
        self.addCleanup(self.host.deleteLater)
        self.addCleanup(download_view.clear)
        self.dialog = UpdateOfferDialog(self.host, current_version="0.26.67", target_version="0.27.67")
        self.addCleanup(lambda: None if sip.isdeleted(self.dialog) else self.dialog.deleteLater())
        self.handler = Mock()
        self.dialog.set_install_handler(self.handler)
        self.dialog.open()
        self.dialog.install_btn.click()
        self.card = ChangelogCard(self.host)
        self.card.start_download("0.27.67")
        self.now = 0.0
        self.view = Mock()
        self.view.update_download_snapshot.side_effect = self._render
        self.runtime = UpdatePageRuntime(self.view, runtime_actions=SimpleNamespace(), updater_feature=SimpleNamespace())
        self.runtime._download_progress = DownloadProgress(clock=lambda: self.now)
        self.addCleanup(self.runtime.deleteLater)
        self.addCleanup(self.runtime._stop_download_progress_timer)

    def _render(self, snapshot):
        self.card.apply_download_snapshot(snapshot)
        download_view.forward("set_download_snapshot", snapshot)

    def test_timer_and_byte_signals_show_same_numbers_and_clear_eta_on_silence(self):
        self.runtime._on_update_stage_changed("download", "Скачивание обновления…")
        self.assertTrue(self.runtime._download_progress_timer.isActive())
        self.runtime._on_update_download_progress(0, 0, 100_000)
        self.now = 1
        self.runtime._on_update_download_progress(10, 10_000, 100_000)
        self.assertEqual(self.card.speed_label.text(), self.dialog.speed_label.text())
        self.assertEqual(self.card.eta_label.text(), self.dialog.eta_label.text())
        self.assertNotEqual(self.dialog.eta_label.text(), "Осталось: —")
        self.now = 7
        QTest.qWait(1100)
        self.assertEqual(self.dialog.download_status.text(), "Ждём ответа сервера…")
        self.assertIn("Ждём ответа сервера…", self.card.version_label.text())
        self.assertEqual(self.card.speed_label.text(), "Скорость: —")
        self.assertEqual(self.dialog.eta_label.text(), "Осталось: —")
        self.assertIn("Ждём ответа сервера", self.dialog.download_status.accessibleName())
        self.runtime._on_update_stage_changed("verify", "Проверка SHA-256…")
        self.assertFalse(self.runtime._download_progress_timer.isActive())
        self.assertEqual(self.dialog.download_status.text(), "Проверка SHA-256…")

    def test_hide_dialog_keeps_page_progress_and_deleted_dialog_receives_nothing(self):
        self.runtime._on_update_stage_changed("download", "Скачивание обновления…")
        self.dialog.hide_btn.click()
        download_view.clear(self.dialog)
        self.runtime._on_update_download_progress(25, 25_000, 100_000)
        self.assertEqual(self.card.progress_label.text(), "25%")
        self.assertTrue(self.runtime._download_progress_timer.isActive())
        self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.runtime._download_progress_timer.timeout.emit()

    def test_error_offers_retry_in_dialog_without_duplicate_start(self):
        self.dialog.download_failed("Сервер долго не отвечает")
        self.assertEqual(self.dialog.install_btn.text(), "Повторить")
        self.assertTrue(self.dialog.install_btn.isVisibleTo(self.dialog))
        self.assertTrue(self.dialog.close_btn.isVisibleTo(self.dialog))
        self.assertEqual(self.dialog.install_btn.accessibleName(), "Повторить загрузку обновления")
        self.dialog.install_btn.click()
        self.dialog.install_btn.click()
        self.assertEqual(self.handler.call_count, 2)
        self.assertTrue(self.dialog.hide_btn.isVisibleTo(self.dialog))
        self.assertFalse(self.dialog.install_btn.isEnabled())

    def test_failure_stops_heartbeat_and_keeps_retry_available(self):
        self.runtime._on_download_failed = Mock()
        self.runtime._download_state.is_installing = True
        self.runtime._on_update_stage_changed("download", "Скачивание обновления…")
        self.runtime._fail_update_pipeline("Соединение прервалось")
        self.assertFalse(self.runtime._download_progress_timer.isActive())
        self.assertFalse(self.runtime._download_state.is_installing)
        self.view.mark_update_download_failed.assert_called_once()


if __name__ == "__main__":
    unittest.main()
