from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class ThemeManagerPersistenceTests(unittest.TestCase):
    def test_theme_persistence_runs_through_worker(self) -> None:
        # Отдельного ThemePersistWorker больше нет: он писал ключ
        # appearance.selected_theme, который никто не читал. Светлая или
        # тёмная тема хранится в appearance.display_mode и сохраняется общим
        # воркером настроек вида. Смысл проверки прежний — ThemeManager не
        # пишет настройки в GUI-потоке.
        from PyQt6.QtCore import QThread

        from app.feature_facades.appearance import AppearanceFeature
        import settings.appearance_workers as appearance_workers
        import ui.theme as theme

        apply_source = inspect.getsource(theme.ThemeManager._apply_css_only)
        for write_call in ("set_selected_theme", "set_display_mode", "save_display_mode", "settings_store"):
            self.assertNotIn(write_call, apply_source)

        worker = appearance_workers.AppearanceSettingsSaveWorker
        self.assertTrue(issubclass(worker, QThread))
        self.assertIn('self._action == "display_mode"', inspect.getsource(worker.run))
        self.assertIn("save_display_mode=", inspect.getsource(AppearanceFeature))


    def test_theme_build_runs_through_runtime(self) -> None:
        import ui.one_shot_worker_runtime as one_shot_runtime
        import ui.theme as theme

        manager_init_source = inspect.getsource(theme.ThemeManager.__init__)
        apply_source = inspect.getsource(theme.ThemeManager.apply_theme_async)
        cleanup_source = inspect.getsource(theme.ThemeManager.cleanup)
        runtime_source = inspect.getsource(one_shot_runtime.OneShotWorkerRuntime.start_qobject_worker)

        self.assertIn("OneShotWorkerRuntime", manager_init_source)
        self.assertIn("_active_theme_build_jobs", manager_init_source)
        self.assertIn("start_qobject_worker", apply_source)
        self.assertIn('failed_signal_name="error"', apply_source)
        self.assertIn("theme build worker", cleanup_source)
        self.assertNotIn("QThread", apply_source)
        self.assertNotIn("moveToThread", apply_source)
        self.assertNotIn("thread.start()", apply_source)
        self.assertIn("failed_signal.connect(thread.quit)", runtime_source)
        self.assertIn("failed_signal.connect(worker.deleteLater)", runtime_source)

    def test_cleanup_does_not_wait_for_theme_build_workers(self) -> None:
        import ui.theme as theme

        build_runtime = SimpleNamespace(stop=Mock(), cancel=Mock())
        manager = theme.ThemeManager.__new__(theme.ThemeManager)
        manager._cleanup_in_progress = False
        manager._active_theme_build_jobs = {1: build_runtime}
        manager._cleanup_theme_build_thread = Mock()

        theme.ThemeManager.cleanup(manager)

        self.assertTrue(manager._cleanup_in_progress)
        build_runtime.stop.assert_called_once_with(
            blocking=False,
            wait_timeout_ms=1000,
            log_fn=theme.log,
            warning_prefix="theme build worker",
        )
        build_runtime.cancel.assert_called_once_with()
        manager._cleanup_theme_build_thread.assert_called_once_with()


class ThemeModeSyncTests(unittest.TestCase):
    def test_same_theme_mode_does_not_restyle_all_widgets(self) -> None:
        from unittest.mock import patch

        from qfluentwidgets import Theme, qconfig

        from ui import theme as theme_module

        with patch("qfluentwidgets.setTheme") as set_theme:
            qconfig.themeMode.value = Theme.DARK
            theme_module._sync_theme_mode_to_qfluent("dark")
            set_theme.assert_not_called()
            theme_module._sync_theme_mode_to_qfluent("light")
            set_theme.assert_called_once_with(Theme.LIGHT)


if __name__ == "__main__":
    unittest.main()
