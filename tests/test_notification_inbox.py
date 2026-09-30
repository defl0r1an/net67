"""Колокольчик: фоновое копится, всплывает только ответ на действие человека.

Под OneDrive у человека на первом запуске всплывали две плашки об одном и
том же прямо поверх мастера, а ошибка подбора стратегии показывала на
экране английский traceback.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ui.notification_inbox import NotificationInbox, human_content, routes_to_inbox  # noqa: E402

TRACEBACK_MESSAGE = (
    "[ERROR] Failed to restore net67 after strategy scan\n"
    "Traceback (most recent call last):\n"
    ' File "blockcheck\\ui\\strategy_scan_page.py", line 700, in _restore_runtime_after_scan\n'
    "RuntimeError: wrapped C/C++ object of type StrategyScanWorker has been deleted"
)


class RoutingTests(unittest.TestCase):
    def test_background_goes_to_inbox(self) -> None:
        for source in ("global_logger", "startup.onedrive_path", "startup", "deferred.telega", "presets.remote_sync"):
            self.assertTrue(routes_to_inbox({"source": source}), source)

    def test_answers_to_actions_still_pop_up(self) -> None:
        for source in ("launch.dpi_error", "startup.proxy.action", "system.clipboard", "presets.user.activation", ""):
            self.assertFalse(routes_to_inbox({"source": source}), source)


class InboxTests(unittest.TestCase):
    def test_traceback_never_reaches_the_screen(self) -> None:
        self.assertEqual(human_content(TRACEBACK_MESSAGE), "Failed to restore net67 after strategy scan")
        self.assertEqual(
            human_content("[ERROR] ERROR: Обнаружен OneDrive в пути: C:\\Users\\Quine\\OneDrive"),
            "Обнаружен OneDrive в пути: C:\\Users\\Quine\\OneDrive",
        )

    def test_repeats_are_glued_and_counted(self) -> None:
        inbox = NotificationInbox()
        for _ in range(3):
            inbox.add({"level": "error", "source": "global_logger", "content": TRACEBACK_MESSAGE})
        inbox.add({"level": "warning", "source": "startup.onedrive_path", "title": "Проверка при запуске", "content": "OneDrive"})

        entries = inbox.entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1].count, 3)
        self.assertEqual(entries[1].title, "Техническая ошибка")
        self.assertEqual(inbox.unread_count(), 2)
        self.assertEqual(inbox.worst_unread_level(), "error")

    def test_success_and_seen_do_not_light_the_counter(self) -> None:
        inbox = NotificationInbox()
        inbox.add({"level": "success", "source": "startup.update_check", "title": "Обновлений нет"})
        inbox.add({"level": "error", "source": "launch.dpi_error", "title": "Не запустилось"}, seen=True)
        self.assertEqual(inbox.unread_count(), 0)
        self.assertEqual(len(inbox.entries()), 2)

    def test_history_is_bounded(self) -> None:
        inbox = NotificationInbox(limit=5)
        for index in range(12):
            inbox.add({"level": "warning", "source": "startup", "content": f"проверка {index}"})
        self.assertEqual(len(inbox.entries()), 5)
        self.assertEqual(inbox.entries()[0].content, "проверка 11")


class CenterRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _center(self):
        from PyQt6.QtWidgets import QWidget

        from ui.widgets.notification_bell import NotificationBell
        from ui.window_notification_actions import WindowNotificationRuntimeActions
        from ui.window_notification_center import WindowNotificationCenter

        window = QWidget()
        self.addCleanup(window.deleteLater)
        noop = lambda *a, **k: None  # noqa: E731
        center = WindowNotificationCenter(
            window,
            startup_state=None,
            runtime_actions=WindowNotificationRuntimeActions(
                is_available=lambda: True,
                cancel_start_after_conflict_prompt=noop,
                execute_windivert_autofix=noop,
                install_windows_server_wlanapi=noop,
                prepare_launch_conflict_resolution=noop,
                continue_start_after_conflict_resolution=noop,
            ),
            create_open_url_worker=noop,
            create_notification_action_worker=noop,
            show_tray_notification=lambda *a: False,
            show_page=noop,
            is_window_visible=lambda: True,
            is_window_minimized=lambda: False,
        )
        bell = NotificationBell(window)
        center.attach_bell(bell)
        return center, bell

    def test_background_error_lights_bell_without_popup(self) -> None:
        center, bell = self._center()
        with patch.object(center, "_show_infobar_notification") as popup:
            center._present_notification({"level": "error", "source": "global_logger", "content": TRACEBACK_MESSAGE})
        popup.assert_not_called()
        self.assertEqual(bell.unread, 1)

    def test_answer_to_action_pops_up_and_is_kept_as_seen(self) -> None:
        center, bell = self._center()
        with patch.object(center, "_show_infobar_notification") as popup:
            center._present_notification({"level": "error", "source": "launch.dpi_error", "title": "Не запустилось"})
        popup.assert_called_once()
        self.assertEqual(bell.unread, 0)
        self.assertEqual(len(center.inbox.entries()), 1)

    def test_opening_panel_marks_everything_read(self) -> None:
        center, bell = self._center()
        center._present_notification({"level": "warning", "source": "startup.onedrive_path", "content": "OneDrive"})
        center.open_inbox_panel()
        self.assertEqual(bell.unread, 0)
        panel = center._inbox_panel
        self.assertIsNotNone(panel)
        panel.close()


if __name__ == "__main__":
    unittest.main()
