from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from ui.pages.about_page import AboutPage
from ui.pages.support_page import SupportPage


class SupportAboutOpenWorkerQueueTests(unittest.TestCase):
    def test_stale_support_open_worker_object_finished_does_not_start_pending_action(self) -> None:
        old_worker = object()
        current_worker = object()
        pending = ("telegram", object(), "error.key", "error")
        page = SupportPage.__new__(SupportPage)
        page._cleanup_in_progress = False
        page._support_open_runtime = SimpleNamespace(request_id=2, worker=current_worker)
        page._support_open_pending = [pending]
        page._schedule_support_open_action_worker_start = Mock()

        SupportPage._on_support_open_action_worker_finished(page, old_worker)

        page._schedule_support_open_action_worker_start.assert_not_called()
        self.assertEqual(page._support_open_pending, [pending])

    def test_stale_about_open_worker_object_finished_does_not_start_pending_action(self) -> None:
        old_worker = object()
        current_worker = object()
        pending = ("github", object(), "error", "")
        page = AboutPage.__new__(AboutPage)
        page._cleanup_in_progress = False
        page._about_open_runtime = SimpleNamespace(request_id=2, worker=current_worker)
        page._about_open_pending = [pending]
        page._schedule_about_open_action_worker_start = Mock()

        AboutPage._on_about_open_action_worker_finished(page, old_worker)

        page._schedule_about_open_action_worker_start.assert_not_called()
        self.assertEqual(page._about_open_pending, [pending])


if __name__ == "__main__":
    unittest.main()
