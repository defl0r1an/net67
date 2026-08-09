from __future__ import annotations

import unittest
from unittest.mock import Mock

from ui.one_shot_worker_runtime import OneShotWorkerRuntime


class OneShotWorkerRuntimeTests(unittest.TestCase):
    def test_qthread_finished_callback_ignored_after_cancel(self) -> None:
        runtime = OneShotWorkerRuntime()
        worker = object()
        on_finished = Mock()
        runtime.worker = worker

        runtime.cancel()
        runtime._finish_qthread_worker(worker, on_finished)

        on_finished.assert_not_called()

    def test_qthread_finished_callback_ignored_for_replaced_worker(self) -> None:
        runtime = OneShotWorkerRuntime()
        old_worker = object()
        current_worker = object()
        on_finished = Mock()
        runtime.worker = current_worker

        runtime._finish_qthread_worker(old_worker, on_finished)

        self.assertIs(runtime.worker, current_worker)
        on_finished.assert_not_called()

    def test_qobject_finished_callback_ignored_for_replaced_thread(self) -> None:
        runtime = OneShotWorkerRuntime()
        old_thread = object()
        current_thread = object()
        on_finished = Mock()
        runtime.thread = current_thread

        runtime._finish_qobject_worker(1, old_thread, on_finished)

        self.assertIs(runtime.thread, current_thread)
        on_finished.assert_not_called()


if __name__ == "__main__":
    unittest.main()
