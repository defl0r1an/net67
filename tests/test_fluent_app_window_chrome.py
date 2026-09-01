from __future__ import annotations

import os
import inspect
import unittest
from types import SimpleNamespace


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.fluent_app_window import AppFluentWindow
from ui.window_ui_facade import _SidebarSearchNavWidget


class FluentAppWindowChromeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_window_uses_qfluentwidgets_content_margins_without_resize_compensation(self) -> None:
        window = AppFluentWindow()
        margins = window.widgetLayout.contentsMargins()

        self.assertEqual(margins.top(), 48)
        self.assertEqual(margins.right(), 0)
        self.assertEqual(margins.bottom(), 0)

    def test_window_chrome_has_no_legacy_border_radius_or_handle_hooks(self) -> None:
        source = inspect.getsource(AppFluentWindow)

        self.assertNotIn("WINDOW_RESIZE_SAFE_MARGIN", source)
        self.assertNotIn("_apply_window_content_margins", source)
        self.assertNotIn("_update_border_radius", source)
        self.assertNotIn("_set_handles_visible", source)
        self.assertFalse(hasattr(AppFluentWindow, "set_zoom_chrome_compact"))

    def test_replaced_titlebar_is_removed_from_window_event_filters(self) -> None:
        class EventFilterTrackingWindow(AppFluentWindow):
            def removeEventFilter(self, event_filter) -> None:  # noqa: N802
                detached = self.__dict__.setdefault("_detached_event_filters", [])
                detached.append(event_filter)
                super().removeEventFilter(event_filter)

        window = EventFilterTrackingWindow()
        detached = window.__dict__.get("_detached_event_filters", [])

        self.assertGreaterEqual(len(detached), 1)
        self.assertNotIn(window.titleBar, detached)
        self.assertTrue(all(hasattr(title_bar, "maxBtn") for title_bar in detached))

    def test_fluent_window_does_not_own_app_geometry_policy(self) -> None:
        source = inspect.getsource(AppFluentWindow)

        self.assertNotIn("setMinimumSize(", source)

    def test_window_only_renders_application_owned_icon(self) -> None:
        source = inspect.getsource(AppFluentWindow)

        self.assertIn("_sync_titlebar_icon_from_application", source)
        self.assertIn("app.windowIcon()", source)
        self.assertNotIn("resolve_existing_app_icon_path", source)
        self.assertNotIn("setWindowIcon", source)
        self.assertNotIn("singleShot", source)
        self.assertNotIn("os.path.exists", source)
        self.assertNotIn("ICON_DEV_PATH", source)
        self.assertNotIn("ICON_PATH", source)

if __name__ == "__main__":
    unittest.main()
