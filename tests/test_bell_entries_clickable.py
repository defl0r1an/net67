"""Каждая запись в колокольчике открывает свой раздел.

Раньше открыть что-то из списка можно было только кнопкой действия, а она
есть у немногих записей. «Пресет сохранён», ошибка редактора профилей —
только читались, и куда смотреть, человек искал сам.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from ui.notification_inbox import (  # noqa: E402
    FALLBACK_PAGE,
    InboxEntry,
    NotificationInbox,
    source_page,
    target_page,
)


def _wait(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()


class TargetPageTests(unittest.TestCase):
    def test_sources_lead_to_their_sections(self) -> None:
        cases = {
            "global_logger": "LOGS",
            "startup.update_check": "SERVERS",
            "deferred.telega": "TELEGRAM_PROXY",
            "launch.dpi_error": "ZAPRET2_MODE_CONTROL",
            "dpi_start": "ZAPRET2_MODE_CONTROL",
            "presets.user.activation": "ZAPRET2_USER_PRESETS",
        }
        for source, page in cases.items():
            with self.subTest(source=source):
                self.assertEqual(source_page(source), page)

    def test_answer_to_a_button_leads_where_the_notice_did(self) -> None:
        self.assertEqual(source_page("launch.conflicting_processes.action"), "ZAPRET2_MODE_CONTROL")

    def test_recorded_section_beats_the_source_rule(self) -> None:
        entry = InboxEntry(level="info", title="t", content="", source="launch.autofix", page="HOSTS")
        self.assertEqual(target_page(entry), "HOSTS")

    def test_every_entry_leads_somewhere(self) -> None:
        entry = InboxEntry(level="info", title="t", content="", source="system.clipboard")
        self.assertEqual(target_page(entry), FALLBACK_PAGE)

    def test_all_named_sections_exist(self) -> None:
        from app.page_names import PageName
        from ui import notification_inbox

        names = {page for _prefix, page in notification_inbox._SOURCE_PAGES} | {FALLBACK_PAGE}
        self.assertEqual(names - set(PageName.__members__), set())

    def test_inbox_keeps_the_section_and_updates_it_on_repeat(self) -> None:
        inbox = NotificationInbox()
        entry = inbox.add({"level": "info", "title": "Сохранено", "content": "", "source": "infobar.X"})
        self.assertEqual(entry.page, "")
        again = inbox.add({"level": "info", "title": "Сохранено", "content": "", "source": "infobar.X", "page": "HOSTS"})
        self.assertIs(again, entry)
        self.assertEqual(entry.page, "HOSTS")


class PanelClickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self, *entries: dict):
        from ui.widgets.notification_bell import NotificationPanel

        inbox = NotificationInbox()
        for payload in reversed(entries):
            inbox.add(payload)
        opened = Mock()
        panel = NotificationPanel(inbox, build_action=lambda *_a: None, on_changed=lambda: None, open_entry=opened)
        panel.show()
        _wait(0.05)
        self.addCleanup(panel.deleteLater)
        return panel, opened

    @staticmethod
    def _rows(panel):
        from ui.widgets.notification_bell import _EntryRow

        return panel.findChildren(_EntryRow)

    def test_every_row_is_clickable_and_opens_its_entry(self) -> None:
        panel, opened = self._panel(
            {"level": "success", "title": "Пресет сохранён", "content": "", "source": "infobar.X"},
            {"level": "error", "title": "Ошибка", "content": "", "source": "global_logger"},
        )
        rows = self._rows(panel)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row.cursor().shape(), Qt.CursorShape.PointingHandCursor)

        QTest.mouseClick(rows[1], Qt.MouseButton.LeftButton, pos=QPoint(rows[1].width() - 4, 6))

        opened.assert_called_once()
        self.assertEqual(opened.call_args.args[0].source, "global_logger")
        self.assertFalse(panel.isVisible())

    def test_click_on_selectable_text_opens_too(self) -> None:
        panel, opened = self._panel(
            {"level": "warning", "title": "Внимание", "content": "Длинный текст ошибки", "source": "launch.x"},
        )
        body = next(label for label in panel.findChildren(QLabel) if label.text() == "Длинный текст ошибки")

        QTest.mouseClick(body, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))

        opened.assert_called_once()

    def test_dragging_over_text_selects_instead_of_opening(self) -> None:
        panel, opened = self._panel(
            {"level": "warning", "title": "Внимание", "content": "Длинный текст ошибки", "source": "launch.x"},
        )
        body = next(label for label in panel.findChildren(QLabel) if label.text() == "Длинный текст ошибки")

        QTest.mousePress(body, Qt.MouseButton.LeftButton, pos=QPoint(2, 4))
        QTest.mouseMove(body, QPoint(60, 4))
        QTest.mouseRelease(body, Qt.MouseButton.LeftButton, pos=QPoint(60, 4))

        opened.assert_not_called()


class CenterOpensEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _center(self, show_page):
        from ui.window_notification_center import WindowNotificationCenter

        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        return WindowNotificationCenter(
            parent,
            startup_state=None,
            runtime_actions=Mock(),
            create_open_url_worker=Mock(),
            create_notification_action_worker=Mock(),
            show_tray_notification=Mock(),
            show_page=show_page,
            is_window_visible=lambda: True,
            is_window_minimized=lambda: False,
        )

    def test_opens_the_entry_section_as_inner_page(self) -> None:
        from app.page_names import PageName

        show_page = Mock(return_value=True)
        center = self._center(show_page)
        entry = InboxEntry(level="info", title="t", content="", source="x", page="HOSTS_FILE")

        self.assertTrue(center._open_inbox_entry(entry))

        show_page.assert_called_once_with(PageName.HOSTS_FILE, allow_internal=True)

    def test_falls_back_to_logs_when_section_does_not_open(self) -> None:
        from app.page_names import PageName

        show_page = Mock(side_effect=[False, True])
        center = self._center(show_page)
        entry = InboxEntry(level="info", title="t", content="", source="launch.x")

        self.assertTrue(center._open_inbox_entry(entry))

        self.assertEqual(
            [call.args[0] for call in show_page.call_args_list],
            [PageName.ZAPRET2_MODE_CONTROL, PageName.LOGS],
        )

    def test_unknown_section_name_goes_to_logs(self) -> None:
        from app.page_names import PageName

        show_page = Mock(return_value=True)
        center = self._center(show_page)
        entry = InboxEntry(level="info", title="t", content="", source="x", page="НЕТ_ТАКОГО")

        center._open_inbox_entry(entry)

        show_page.assert_called_once_with(PageName.LOGS, allow_internal=True)


if __name__ == "__main__":
    unittest.main()
