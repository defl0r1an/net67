from __future__ import annotations

import time

from PyQt6.QtCore import QObject, pyqtSignal

from app.performance_metrics import log_ui_timing_since


class LogsOverviewWorker(QObject):
    loaded = pyqtSignal(object, object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, *, list_logs_fn, build_stats_fn, run_cleanup: bool):
        super().__init__()
        self._list_logs_fn = list_logs_fn
        self._build_stats_fn = build_stats_fn
        self._run_cleanup = bool(run_cleanup)
        self._stopped = False

    def run(self) -> None:
        started_at = time.perf_counter()
        try:
            logs_state = self._list_logs_fn(run_cleanup=self._run_cleanup)
            stats_state = self._build_stats_fn()
            if not self._stopped:
                self.loaded.emit(logs_state, stats_state)
        except Exception as exc:
            if not self._stopped:
                self.failed.emit(str(exc))
        finally:
            log_ui_timing_since("worker", "logs_overview", "logs_feature.overview_worker.total", started_at)
            self.finished.emit()

    def stop(self) -> None:
        self._stopped = True


__all__ = ["LogsOverviewWorker"]
