from __future__ import annotations

import time

from app.page_names import PageName
from log.log import log


UI_PERFORMANCE_LOG_LEVEL = "⏱ UI"
SLOW_UI_METRIC_THRESHOLD_MS = 80
DEFAULT_UI_METRIC_THRESHOLD_MS = 15


def _metric_name(value: PageName | str | None) -> str:
    if isinstance(value, PageName):
        return value.name
    text = str(value or "").strip()
    return text or "UNKNOWN"


def _metric_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _rounded_ms(elapsed_ms: float) -> int:
    try:
        return int(round(float(elapsed_ms)))
    except Exception:
        return 0


def _metric_level(elapsed_ms: int, *, budget_ms: int | None, important: bool) -> str:
    if budget_ms is not None and elapsed_ms > int(budget_ms):
        return "WARNING"
    if important or elapsed_ms >= SLOW_UI_METRIC_THRESHOLD_MS:
        return UI_PERFORMANCE_LOG_LEVEL
    return "DEBUG"


def log_ui_timing(
    scope: str,
    name: PageName | str | None,
    stage: str,
    elapsed_ms: float,
    *,
    budget_ms: int | None = None,
    extra: str | None = None,
    important: bool = False,
    threshold_ms: int = DEFAULT_UI_METRIC_THRESHOLD_MS,
) -> None:
    """Единый формат метрик UI и фоновых этапов."""

    rounded = _rounded_ms(elapsed_ms)
    if not important and rounded < int(threshold_ms):
        return

    scope_text = _metric_text(scope) or "unknown"
    name_text = _metric_name(name)
    stage_text = _metric_text(stage) or "unknown"
    parts = [
        f"scope={scope_text}",
        f"name={name_text}",
        f"stage={stage_text}",
        f"elapsed={rounded}ms",
    ]
    if budget_ms is not None:
        parts.append(f"budget={int(budget_ms)}ms")
    extra_text = _metric_text(extra)
    if extra_text:
        parts.append(f"detail={extra_text}")

    try:
        log(
            "⏱ UiMetric: " + " ".join(parts),
            _metric_level(rounded, budget_ms=budget_ms, important=bool(important)),
        )
    except Exception:
        pass


def log_ui_timing_since(
    scope: str,
    name: PageName | str | None,
    stage: str,
    started_at: float,
    *,
    budget_ms: int | None = None,
    extra: str | None = None,
    important: bool = False,
    threshold_ms: int = DEFAULT_UI_METRIC_THRESHOLD_MS,
) -> None:
    try:
        elapsed_ms = (time.perf_counter() - float(started_at)) * 1000.0
    except Exception:
        elapsed_ms = 0.0
    log_ui_timing(
        scope,
        name,
        stage,
        elapsed_ms,
        budget_ms=budget_ms,
        extra=extra,
        important=important,
        threshold_ms=threshold_ms,
    )


def log_page_timing(
    page_name: PageName | str | None,
    stage: str,
    elapsed_ms: float,
    *,
    budget_ms: int | None = None,
    extra: str | None = None,
    important: bool = False,
    threshold_ms: int = DEFAULT_UI_METRIC_THRESHOLD_MS,
) -> None:
    log_ui_timing(
        "page",
        page_name,
        stage,
        elapsed_ms,
        budget_ms=budget_ms,
        extra=extra,
        important=important,
        threshold_ms=threshold_ms,
    )


def log_page_timing_since(
    page_name: PageName | str | None,
    stage: str,
    started_at: float,
    *,
    budget_ms: int | None = None,
    extra: str | None = None,
    important: bool = False,
    threshold_ms: int = DEFAULT_UI_METRIC_THRESHOLD_MS,
) -> None:
    log_ui_timing_since(
        "page",
        page_name,
        stage,
        started_at,
        budget_ms=budget_ms,
        extra=extra,
        important=important,
        threshold_ms=threshold_ms,
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
