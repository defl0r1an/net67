"""Загрузка обновления прямо в окне «Доступно обновление».

Раньше «Обновить» закрывало окно, и ход загрузки был виден только на
странице «Серверы», куда человек не смотрел. Теперь окно остаётся: под
списком изменений бежит логотип по полосе, видны процент, объём, скорость
и сколько осталось; «Скрыть» убирает окно, загрузка не прерывается.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402


class FormatTests(unittest.TestCase):
    def test_speed_switches_to_megabytes(self) -> None:
        from updater.ui.update_dialog import format_speed

        self.assertEqual(format_speed(685 * 1024), "685 КБ/с")
        self.assertEqual(format_speed(1.5 * 1024 * 1024), "1.5 МБ/с")

    def test_eta_in_minutes_and_seconds(self) -> None:
        from updater.ui.update_dialog import format_eta

        self.assertEqual(format_eta(49), "49 сек")
        self.assertEqual(format_eta(130), "2 мин 10 сек")
        self.assertEqual(format_eta(120), "2 мин")

    def test_speed_uses_recent_samples_only(self) -> None:
        from updater.ui.update_dialog import DownloadSpeed

        now = [0.0]
        speed = DownloadSpeed(clock=lambda: now[0])
        # Медленный старт не тянет скорость вниз до конца загрузки.
        for second, done in ((0, 0), (1, 10_000), (10, 20_000), (11, 1_020_000), (12, 2_020_000)):
            now[0] = float(second)
            speed.add(done)
        self.assertAlmostEqual(speed.bytes_per_second(), 1_000_000, delta=1)
        self.assertAlmostEqual(speed.eta_seconds(2_020_000, 4_020_000), 2.0, delta=0.01)


class DialogDownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        self.host = QWidget()
        self.host.resize(1200, 900)
        self.host.show()
        self.addCleanup(self.host.deleteLater)

    def _dialog(self):
        from updater.ui.update_dialog import UpdateOfferDialog

        dialog = UpdateOfferDialog(
            self.host,
            current_version="0.25.67",
            target_version="0.26.67",
            history=[{"version": "0.26.67", "notes": "- новое", "is_new": True}],
            source="GitHub",
        )
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_install_with_handler_keeps_window_and_shows_download(self) -> None:
        from updater.ui import download_view
        from updater.ui.update_dialog import RESULT_INSTALL

        dialog = self._dialog()
        calls = []
        dialog.set_install_handler(lambda: calls.append(True))
        self.addCleanup(download_view.clear)
        dialog.open()

        dialog.install_btn.click()

        self.assertEqual(calls, [True])
        self.assertEqual(dialog.result_action, RESULT_INSTALL)
        self.assertTrue(dialog.isVisible())
        self.assertTrue(dialog.download_box.isVisibleTo(dialog))
        self.assertTrue(dialog.hide_btn.isVisibleTo(dialog))
        self.assertFalse(dialog.install_btn.isVisibleTo(dialog))
        self.assertIn("0.26.67", dialog.title_label.text())

        # Ход приходит со страницы «Серверы» через download_view.
        download_view.forward("set_download_status", "Скачивание обновления…")
        download_view.forward("set_download_progress", 21, 9_437_184, 44_249_907)
        self.assertEqual(dialog.download_status.text(), "Скачивание обновления…")
        self.assertEqual(dialog.percent_label.text(), "21%")
        self.assertEqual(dialog.size_label.text(), "Загружено 9.0 / 42.2 МБ")
        self.assertEqual(dialog.runway.value(), 21.0)

    def test_failure_offers_close_instead_of_hide(self) -> None:
        from updater.ui import download_view

        dialog = self._dialog()
        dialog.set_install_handler(lambda: None)
        self.addCleanup(download_view.clear)
        dialog.open()
        dialog.install_btn.click()

        download_view.forward("download_failed", "Не удалось скачать файл")

        self.assertTrue(dialog.close_btn.isVisibleTo(dialog))
        self.assertFalse(dialog.hide_btn.isVisibleTo(dialog))
        self.assertIn("Не удалось скачать файл", dialog.download_status.text())

    def test_without_handler_install_closes_as_before(self) -> None:
        from updater.ui.update_dialog import RESULT_INSTALL

        dialog = self._dialog()
        dialog.open()

        dialog.install_btn.click()
        self.app.processEvents()

        self.assertEqual(dialog.result_action, RESULT_INSTALL)
        self.assertFalse(dialog.download_box.isVisibleTo(dialog))

    def test_closed_window_stops_receiving_progress(self) -> None:
        from updater.ui import download_view

        dialog = self._dialog()
        dialog.set_install_handler(lambda: None)
        dialog.open()
        dialog.install_btn.click()
        self.assertIs(download_view.get_active(), dialog)

        download_view.clear(dialog)

        self.assertIsNone(download_view.get_active())
        download_view.forward("set_download_progress", 50, 1, 2)  # не падает


if __name__ == "__main__":
    unittest.main()
