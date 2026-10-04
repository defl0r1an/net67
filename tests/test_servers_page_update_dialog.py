"""Ручная проверка на странице «Серверы» показывает то же окно, что и запуск.

Раньше найденное обновление на «Серверах» было только карточкой внизу
страницы: при запуске человек видел окно с изменениями и «Пропустить
версию», а здесь — строчку с кнопкой.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.feature_facades.updater import UpdaterFeature  # noqa: E402
from updater.update_page_runtime import UpdatePageRuntime, UpdateRuntimeActions  # noqa: E402


def _wait(seconds: float = 0.05) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()


class ServersPageUpdateDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _runtime(self, action: str):
        view = Mock()
        view.is_update_download_in_progress.return_value = False
        view.ask_update_offer.return_value = action
        # Фасад — замороженный dataclass: подменяем метод на классе.
        patcher = patch.object(UpdaterFeature, "remember_skipped_update")
        remember = patcher.start()
        self.addCleanup(patcher.stop)
        feature = UpdaterFeature()
        self.remember = remember
        runtime = UpdatePageRuntime(
            view,
            runtime_actions=UpdateRuntimeActions(
                is_any_running=Mock(return_value=False),
                shutdown_sync=Mock(),
                is_available=Mock(return_value=True),
                restart=Mock(),
                mark_stopped=Mock(),
                request_exit=Mock(),
            ),
            updater_feature=feature,
        )
        return runtime, view, feature

    def _found(self, runtime, *, manual: bool) -> None:
        runtime._offer_dialog_pending = manual
        runtime._set_found_update_state("9.99.67", "**Что нового**\n- всё")
        with patch.object(runtime, "_finish_checking_workflow"):
            runtime._on_versions_complete()
        _wait()

    def test_manual_check_opens_the_dialog_and_install_starts_update(self) -> None:
        runtime, view, _feature = self._runtime("install")
        with patch.object(runtime, "install_update") as install:
            self._found(runtime, manual=True)
        view.ask_update_offer.assert_called_once_with("9.99.67", "**Что нового**\n- всё")
        install.assert_called_once_with()
        # Карточка тоже на месте: из неё можно поставить и после «Позже».
        view.show_update_offer.assert_called()

    def test_skip_is_remembered(self) -> None:
        runtime, _view, feature = self._runtime("skip")
        with patch.object(runtime, "install_update") as install:
            self._found(runtime, manual=True)
        self.remember.assert_called_once_with("9.99.67")
        install.assert_not_called()

    def test_later_does_nothing(self) -> None:
        runtime, _view, feature = self._runtime("later")
        with patch.object(runtime, "install_update") as install:
            self._found(runtime, manual=True)
        install.assert_not_called()
        self.remember.assert_not_called()

    def test_check_not_requested_by_the_person_shows_only_the_card(self) -> None:
        runtime, view, _feature = self._runtime("install")
        with patch.object(runtime, "install_update") as install:
            self._found(runtime, manual=False)
        view.ask_update_offer.assert_not_called()
        install.assert_not_called()
        view.show_update_offer.assert_called()


if __name__ == "__main__":
    unittest.main()
