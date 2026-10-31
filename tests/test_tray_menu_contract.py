from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TrayMenuContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_tray_launch_state_reads_runtime_snapshot_contract(self) -> None:
        from app.feature_facades.tray import TrayFeature

        runtime_feature = SimpleNamespace(
            snapshot=Mock(return_value=SimpleNamespace(running=True, phase="running"))
        )
        feature = TrayFeature(
            _deps=SimpleNamespace(),
            _runtime_feature=runtime_feature,
            _telegram_proxy_feature=SimpleNamespace(),
        )

        self.assertEqual(feature.launch_state(), (True, "running"))

    def test_legacy_right_click_callback_opens_context_menu_at_cursor(self) -> None:
        import tray

        tray.WM_CONTEXTMENU = 0x007B
        tray.WM_RBUTTONUP = 0x0205
        tray.WM_LBUTTONUP = 0x0202
        tray.WM_LBUTTONDBLCLK = 0x0203
        tray.NIN_SELECT = 0x0400
        tray.NIN_KEYSELECT = 0x0401

        manager = tray.SystemTrayManager.__new__(tray.SystemTrayManager)
        manager.show_context_menu = Mock()
        manager._schedule_visibility_toggle = Mock()

        with patch.object(tray.QTimer, "singleShot", side_effect=lambda _ms, callback: callback()):
            tray.SystemTrayManager._handle_native_callback(manager, tray.WM_RBUTTONUP, anchor_x=1, anchor_y=0)

        manager.show_context_menu.assert_called_once_with(anchor_x=None, anchor_y=None)
        manager._schedule_visibility_toggle.assert_not_called()

    def _prewarm_manager(self, create_menu):
        import tray

        manager = tray.SystemTrayManager.__new__(tray.SystemTrayManager)
        manager.window_port = SimpleNamespace(create_menu=create_menu, is_visible=Mock(return_value=False))
        manager._tray_feature = SimpleNamespace(
            launch_state=Mock(return_value=(False, "")),
            telegram_proxy_label=Mock(return_value="Telegram Proxy: выкл"),
        )
        manager._menu = None
        manager._show_window_action = None
        manager._tg_proxy_action = None
        manager._exit_stop_action = None
        manager._network_status_action = None
        manager._network_ok = None
        manager._network_latency_ms = 0.0
        manager._tray_menu_min_width = 336
        manager._tray_submenu_min_width = 240
        return manager

    def test_menu_is_built_and_drawn_before_the_first_click(self) -> None:
        from qfluentwidgets import RoundMenu

        menus = []

        def create_menu():
            menu = RoundMenu(parent=None)
            self.addCleanup(menu.deleteLater)
            menu.grab = Mock(wraps=menu.grab)
            menus.append(menu)
            return menu

        manager = self._prewarm_manager(create_menu)

        with patch("tray.log") as log:
            manager.prewarm_menu()

        log.assert_not_called()  # прогрев дошёл до конца, а не проглотил ошибку
        self.assertEqual(len(menus), 1)
        menus[0].grab.assert_called_once()
        self.assertFalse(menus[0].isVisible())  # на экран прогрев ничего не выводит
        # Первый щелчок открывает уже созданное меню, а не строит новое.
        self.assertIs(manager._ensure_qt_menu(), menus[0])

    def test_prewarm_failure_is_swallowed(self) -> None:
        manager = self._prewarm_manager(Mock(side_effect=RuntimeError("нет экрана")))

        manager.prewarm_menu()  # не падает

        self.assertIsNone(manager._menu)

    def test_cached_menu_can_reopen_and_receive_network_updates(self) -> None:
        from PyQt6.QtCore import QCoreApplication, QEvent
        from PyQt6.QtWidgets import QWidget
        from qfluentwidgets import RoundMenu
        from main.tray_window_port import TrayWindowPort

        owner = QWidget()
        self.addCleanup(owner.deleteLater)
        menus = []

        def create_menu():
            menu = RoundMenu(parent=owner)
            menu.exec = Mock(return_value=None)
            menus.append(menu)
            return menu

        manager = self._prewarm_manager(create_menu)
        manager.window_port.exec_popup_menu = TrayWindowPort(owner).exec_popup_menu
        manager._update_tray_tooltip = Mock()
        for iteration in range(3):
            manager.show_context_menu()
            # Нужна настоящая обработка DeferredDelete: живая Python-ссылка
            # иначе прячет уже запланированное удаление меню и его Action.
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            manager._on_network_status_changed(True, 12 + iteration)
            self.assertEqual(manager._network_status_action.text(), f"Сеть: {12 + iteration} мс")
        self.assertEqual(len(menus), 1)

    def test_native_backend_schedules_the_prewarm(self) -> None:
        import inspect

        import tray

        source = inspect.getsource(tray.SystemTrayManager._create_native_backend)
        self.assertIn("prewarm_menu", source)

    def test_round_tray_menu_uses_global_hairline_fix(self) -> None:
        import tray
        from qfluentwidgets import Action, RoundMenu
        from ui.popup_menu_style import install_global_round_menu_hairline_fix

        manager = tray.SystemTrayManager.__new__(tray.SystemTrayManager)
        with patch("ui.popup_menu_style._is_windows_11_or_newer", return_value=True):
            install_global_round_menu_hairline_fix()
            menu = RoundMenu(parent=None)
        self.addCleanup(menu.deleteLater)
        menu.addAction(Action("Скрыть в трей", menu))
        before = menu.styleSheet()

        tray.SystemTrayManager._apply_menu_style(manager, menu)

        self.assertEqual(menu.styleSheet(), before)
        self.assertIn("MenuActionListWidget", menu.styleSheet())
        self.assertIn("border-color", menu.styleSheet())
        self.assertIn("net67-round-menu-hairline-begin", menu.styleSheet())
        self.assertNotIn("border-left", menu.styleSheet())

    def test_native_tray_winapi_calls_have_pointer_safe_ctypes_signatures(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "tray.py").read_text(encoding="utf-8")

        required_signatures = [
            "kernel32.GetModuleHandleW.restype",
            "user32.RegisterClassExW.argtypes",
            "user32.RegisterClassExW.restype",
            "user32.UnregisterClassW.argtypes",
            "user32.UnregisterClassW.restype",
            "user32.CreateWindowExW.argtypes",
            "user32.CreateWindowExW.restype",
            "user32.DestroyWindow.argtypes",
            "user32.DestroyWindow.restype",
            "user32.LoadImageW.argtypes",
            "user32.LoadImageW.restype",
            "user32.LoadIconW.argtypes",
            "user32.LoadIconW.restype",
            "user32.DestroyIcon.argtypes",
            "user32.DestroyIcon.restype",
            "shell32.Shell_NotifyIconW.argtypes",
            "shell32.Shell_NotifyIconW.restype",
        ]

        missing = [signature for signature in required_signatures if signature not in source]

        self.assertEqual(missing, [])

    def test_native_tray_message_window_unregisters_class_on_destroy(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "tray.py").read_text(encoding="utf-8")

        self.assertIn("user32.UnregisterClassW(self.owner._class_name, instance)", source)

    def test_native_tray_class_name_is_unique_per_manager_instance(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "tray.py").read_text(encoding="utf-8")

        self.assertIn('self._class_name = f"{APP_SLUG}TrayWindow_{os.getpid()}_{id(self):x}"', source)


if __name__ == "__main__":
    unittest.main()
