from __future__ import annotations

from app.performance_metrics import (
    DEFAULT_UI_METRIC_THRESHOLD_MS,
    SLOW_UI_METRIC_THRESHOLD_MS,
    UI_PERFORMANCE_LOG_LEVEL,
    log_page_timing,
    log_page_timing_since,
    log_ui_timing,
    log_ui_timing_since,
)

__all__ = [
    "DEFAULT_UI_METRIC_THRESHOLD_MS",
    "SLOW_UI_METRIC_THRESHOLD_MS",
    "UI_PERFORMANCE_LOG_LEVEL",
    "log_page_timing",
    "log_page_timing_since",
    "log_ui_timing",
    "log_ui_timing_since",
]
