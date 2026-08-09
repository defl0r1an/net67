from __future__ import annotations

import ctypes
import inspect
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class RemoveNativeMenuBorderTests(unittest.TestCase):
    """DWM-рамка Win11 снимается атрибутом DWMWA_BORDER_COLOR=COLOR_NONE."""

    def test_sets_border_color_none_on_menu_hwnd(self) -> None:
        import ui.popup_menu_style as pms

        captured: dict = {}

        def fake_dwm_set(hwnd, attr, value_ref, size):
            captured["hwnd"] = hwnd.value if hasattr(hwnd, "value") else hwnd
            captured["attr"] = attr.value if hasattr(attr, "value") else attr
            captured["value"] = ctypes.cast(
                value_ref, ctypes.POINTER(ctypes.c_uint)
            ).contents.value
            captured["size"] = size
            return 0

        fake_windll = SimpleNamespace(
            dwmapi=SimpleNamespace(DwmSetWindowAttribute=Mock(side_effect=fake_dwm_set))
        )
        window = SimpleNamespace(winId=lambda: 4242)

        with (
            patch.object(pms, "_is_windows_11_or_newer", return_value=True),
            patch.object(ctypes, "windll", fake_windll, create=True),
        ):
            pms._remove_native_menu_border(window)

        self.assertEqual(captured["hwnd"], 4242)
        self.assertEqual(captured["attr"], 34)
        self.assertEqual(captured["value"], 0xFFFFFFFE)
        self.assertEqual(captured["size"], ctypes.sizeof(ctypes.c_uint))

    def test_noop_below_windows_11(self) -> None:
        import ui.popup_menu_style as pms

        dwm_mock = Mock()
        fake_windll = SimpleNamespace(dwmapi=SimpleNamespace(DwmSetWindowAttribute=dwm_mock))
        window = SimpleNamespace(winId=lambda: 4242)

        with (
            patch.object(pms, "_is_windows_11_or_newer", return_value=False),
            patch.object(ctypes, "windll", fake_windll, create=True),
        ):
            pms._remove_native_menu_border(window)

        dwm_mock.assert_not_called()

    def test_noop_for_none_window_and_zero_hwnd(self) -> None:
        import ui.popup_menu_style as pms

        dwm_mock = Mock()
        fake_windll = SimpleNamespace(dwmapi=SimpleNamespace(DwmSetWindowAttribute=dwm_mock))

        with (
            patch.object(pms, "_is_windows_11_or_newer", return_value=True),
            patch.object(ctypes, "windll", fake_windll, create=True),
        ):
            pms._remove_native_menu_border(None)
            pms._remove_native_menu_border(SimpleNamespace(winId=lambda: 0))

        dwm_mock.assert_not_called()


class ShowFilterTests(unittest.TestCase):
    """Show-фильтр снимает рамку при каждом показе виджета меню."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_filter_installed_once_and_fires_on_show(self) -> None:
        from PyQt6.QtWidgets import QWidget

        import ui.popup_menu_style as pms

        widget = QWidget()
        calls: list = []

        with (
            patch.object(pms, "_is_windows_11_or_newer", return_value=True),
            patch.object(pms, "_remove_native_menu_border", side_effect=lambda w: calls.append(w)),
        ):
            pms._install_native_border_removal(widget)
            pms._install_native_border_removal(widget)  # повторная установка — no-op

            widget.show()
            widget.hide()
            widget.show()

        self.assertEqual(calls, [widget.window(), widget.window()])
        widget.deleteLater()

    def test_filter_not_installed_below_windows_11(self) -> None:
        from PyQt6.QtWidgets import QWidget

        import ui.popup_menu_style as pms

        widget = QWidget()
        with patch.object(pms, "_is_windows_11_or_newer", return_value=False):
            pms._install_native_border_removal(widget)

        self.assertFalse(getattr(widget, "_zapretgui_menu_border_filter_installed", False))
        widget.deleteLater()


class GlobalHookContractTests(unittest.TestCase):
    def test_global_hook_installs_border_removal(self) -> None:
        import ui.popup_menu_style as pms

        source = inspect.getsource(pms.install_global_round_menu_hairline_fix)
        self.assertIn("_install_native_border_removal", source)
        self.assertIn("_apply_round_menu_hairline_qss", source)

    def test_compat_entry_point_installs_border_removal(self) -> None:
        import ui.popup_menu_style as pms

        source = inspect.getsource(pms.suppress_round_menu_hairline)
        self.assertIn("_install_native_border_removal", source)


if __name__ == "__main__":
    unittest.main()
