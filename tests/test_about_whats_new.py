"""Кнопка «Что нового» в «О программе».

«Что нового» после обновления показывается один раз. Закрыл не читая —
перечитать было негде, кроме страницы выпуска на GitHub. Кнопка
показывает изменения установленной версии в любой момент: сохранённые
перед установкой, а если их нет — из списка выпусков GitHub.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QThread, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def _releases(*versions: str) -> list[dict]:
    return [{"version": version, "release_notes": f"изменения {version}"} for version in versions]


class InstalledReleaseHistoryTests(unittest.TestCase):
    def _history(self, *, state: dict, releases=None, version: str = "0.23.67"):
        from updater import commands

        with (
            patch("config.build_info.APP_VERSION", version),
            patch("settings.store.get_whats_new_state", lambda: dict(state)),
            patch("updater.github_release.get_all_releases_with_exe", lambda: list(releases or ())),
        ):
            return commands.installed_release_history()

    def test_saved_history_of_this_version_needs_no_network(self) -> None:
        saved = [{"version": "0.23.67", "notes": "сохранено", "is_new": True}]
        version, history = self._history(
            state={"pending_version": "0.23.67", "pending_history": saved},
            releases=None,
        )

        self.assertEqual(version, "0.23.67")
        self.assertEqual(history, saved)

    def test_github_list_marks_only_installed_version_as_new(self) -> None:
        version, history = self._history(
            state={"pending_version": "0.22.67", "pending_history": [{"version": "0.22.67"}]},
            releases=_releases("0.24.67", "0.23.67", "0.22.67", "0.21.67"),
        )

        self.assertEqual(version, "0.23.67")
        self.assertEqual([item["version"] for item in history], ["0.23.67", "0.22.67", "0.21.67"])
        self.assertEqual([item["is_new"] for item in history], [True, False, False])

    def test_no_releases_is_an_error_not_an_empty_window(self) -> None:
        with self.assertRaises(RuntimeError):
            self._history(state={}, releases=[])


class _FakeWorker(QThread):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id: int, result, parent=None) -> None:
        super().__init__(parent)
        self._request_id = int(request_id)
        self._result = result

    def run(self) -> None:
        self.loaded.emit(self._request_id, self._result)


class AboutPageWhatsNewButtonTests(unittest.TestCase):
    def test_button_opens_whats_new_with_loaded_history(self) -> None:
        from ui.pages.about_page import AboutPage

        app = QApplication.instance() or QApplication([])
        history = ({"version": "0.23.67", "notes": "новое", "is_new": True},)
        created = []

        def factory(request_id, parent=None):
            worker = _FakeWorker(request_id, ("0.23.67", history), parent)
            created.append(worker)
            return worker

        page = AboutPage(
            open_updates=lambda: None,
            create_open_action_worker=lambda *_a, **_k: None,
            ui_state_store=None,
            create_whats_new_worker=factory,
        )
        self.addCleanup(page.deleteLater)
        page.show()
        app.processEvents()
        self.assertIsNotNone(page.whats_new_btn)

        with patch("updater.ui.update_dialog.show_whats_new") as show:
            page.whats_new_btn.click()
            deadline = time.monotonic() + 5
            while not show.called and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)

        self.assertEqual(len(created), 1)
        show.assert_called_once()
        self.assertEqual(show.call_args.kwargs["version"], "0.23.67")
        self.assertEqual(show.call_args.kwargs["history"], history)


if __name__ == "__main__":
    unittest.main()
