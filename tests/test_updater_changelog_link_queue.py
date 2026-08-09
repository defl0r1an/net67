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


class UpdaterChangelogLinkQueueTests(unittest.TestCase):
    def test_changelog_link_open_uses_shared_latest_worker_state(self) -> None:
        from ui.latest_value_worker_state import LatestValueWorkerState
        from updater.ui.page import ServersPage

        page = ServersPage.__new__(ServersPage)
        page._changelog_link_open_runtime = SimpleNamespace(is_running=Mock(return_value=False))

        init_source = inspect.getsource(ServersPage.__init__)
        request_source = inspect.getsource(ServersPage._request_changelog_link_open)
        schedule_source = inspect.getsource(ServersPage._schedule_changelog_link_open_worker_start)
        cleanup_source = inspect.getsource(ServersPage._stop_changelog_link_open_worker)

        self.assertIsInstance(ServersPage._changelog_link_open_state_obj(page), LatestValueWorkerState)
        self.assertNotIn("_changelog_link_open_pending: str | None = None", init_source)
        self.assertNotIn("_changelog_link_open_start_scheduled = False", init_source)
        self.assertIn("_changelog_link_open_state_obj()", request_source)
        self.assertIn("_changelog_link_open_state_obj()", schedule_source)
        self.assertIn("_changelog_link_open_state_obj().reset()", cleanup_source)

    def test_changelog_link_pending_restarts_after_event_loop_turn(self) -> None:
        import updater.ui.page as updater_page
        from updater.ui.page import ServersPage

        page = ServersPage.__new__(ServersPage)
        page._cleanup_in_progress = False
        page._changelog_link_open_runtime_worker = None
        page._changelog_link_open_pending = "https://example.org"
        page._start_changelog_link_open_worker = Mock()
        single_shot = Mock(side_effect=lambda _delay, _callback: None)

        with patch.object(updater_page, "QTimer", SimpleNamespace(singleShot=single_shot)):
            ServersPage._on_changelog_link_open_worker_finished(page, object())

        single_shot.assert_called_once()
        self.assertEqual(single_shot.call_args.args[0], 0)
        page._start_changelog_link_open_worker.assert_not_called()

        single_shot.call_args.args[1]()

        page._start_changelog_link_open_worker.assert_called_once_with("https://example.org")

    def test_stale_changelog_link_worker_finished_does_not_restart_pending_open(self) -> None:
        import updater.ui.page as updater_page
        from updater.ui.page import ServersPage

        current_worker = object()
        page = ServersPage.__new__(ServersPage)
        page._cleanup_in_progress = False
        page._changelog_link_open_runtime_worker = current_worker
        page._changelog_link_open_pending = "https://example.org"
        page._start_changelog_link_open_worker = Mock()
        single_shot = Mock()

        with patch.object(updater_page, "QTimer", SimpleNamespace(singleShot=single_shot)):
            ServersPage._on_changelog_link_open_worker_finished(page, object())

        single_shot.assert_not_called()
        page._start_changelog_link_open_worker.assert_not_called()
        self.assertIs(page._changelog_link_open_runtime_worker, current_worker)
        self.assertEqual(page._changelog_link_open_pending, "https://example.org")

    def test_changelog_link_request_queues_while_start_is_scheduled(self) -> None:
        from updater.ui.page import ServersPage

        runtime = SimpleNamespace(is_running=Mock(return_value=False))
        page = ServersPage.__new__(ServersPage)
        page._changelog_link_open_runtime = runtime
        page._changelog_link_open_start_scheduled = True
        page._changelog_link_open_pending = None
        page._start_changelog_link_open_worker = Mock()

        ServersPage._request_changelog_link_open(page, "https://example.org")

        page._start_changelog_link_open_worker.assert_not_called()
        self.assertEqual(page._changelog_link_open_pending, "https://example.org")

    def test_changelog_link_scheduled_start_uses_latest_pending_url(self) -> None:
        import updater.ui.page as updater_page
        from updater.ui.page import ServersPage

        runtime = SimpleNamespace(is_running=Mock(return_value=False))
        page = ServersPage.__new__(ServersPage)
        page._cleanup_in_progress = False
        page._changelog_link_open_runtime = runtime
        page._changelog_link_open_runtime_worker = None
        page._changelog_link_open_pending = "https://old.example.org"
        page._changelog_link_open_start_scheduled = False
        page._start_changelog_link_open_worker = Mock()
        single_shot = Mock(side_effect=lambda _delay, _callback: None)

        with patch.object(updater_page, "QTimer", SimpleNamespace(singleShot=single_shot)):
            ServersPage._on_changelog_link_open_worker_finished(page, object())
            ServersPage._request_changelog_link_open(page, "https://new.example.org")

        single_shot.call_args.args[1]()

        page._start_changelog_link_open_worker.assert_called_once_with("https://new.example.org")

    def test_changelog_link_result_is_ignored_when_new_link_is_pending(self) -> None:
        from updater.ui.page import ServersPage

        page = ServersPage.__new__(ServersPage)
        page._cleanup_in_progress = False
        page._changelog_link_open_pending = "https://new.example.org"
        page._changelog_link_open_runtime = Mock()
        page._changelog_link_open_runtime.is_current.return_value = True
        page._show_changelog_link_open_error = Mock()
        result = SimpleNamespace(ok=False, error="old error")

        ServersPage._on_changelog_link_open_finished(page, 5, result)

        page._show_changelog_link_open_error.assert_not_called()

    def test_changelog_link_error_is_ignored_when_new_link_is_pending(self) -> None:
        from updater.ui.page import ServersPage

        page = ServersPage.__new__(ServersPage)
        page._cleanup_in_progress = False
        page._changelog_link_open_pending = "https://new.example.org"
        page._changelog_link_open_runtime = Mock()
        page._changelog_link_open_runtime.is_current.return_value = True
        page._show_changelog_link_open_error = Mock()

        ServersPage._on_changelog_link_open_failed(page, 5, "old error")

        page._show_changelog_link_open_error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
