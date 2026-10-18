"""Нажатие на прошлую проверку BlockCheck открывает её, а не роняет программу.

18 октября 2026 нажатие давало TypeError: обработчик передавал в
OneShotWorkerRuntime.is_current параметр sender, которого у нас нет.
"""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from blockcheck.ui.page import BlockcheckPage
from ui.one_shot_worker_runtime import OneShotWorkerRuntime


class PastCheckOpenTests(unittest.TestCase):
    def _page(self, request_id: int):
        runtime = OneShotWorkerRuntime()
        runtime.request_id = request_id
        return SimpleNamespace(_past_report_runtime=runtime, _cleanup_in_progress=False, _show_past_check=Mock())

    def test_current_answer_is_shown(self) -> None:
        page = self._page(3)
        BlockcheckPage._on_past_check_loaded(page, 3, {"text": ["отчёт"]})
        page._show_past_check.assert_called_once_with({"text": ["отчёт"]})

    def test_late_answer_of_previous_click_is_dropped(self) -> None:
        page = self._page(4)
        BlockcheckPage._on_past_check_loaded(page, 3, {"text": ["старый"]})
        page._show_past_check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
