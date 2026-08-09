from __future__ import annotations

from threading import Lock


_warmed_sidebar_expanded_lock = Lock()
_warmed_sidebar_expanded: bool | None = None


def store_warmed_sidebar_expanded(expanded: bool | None) -> None:
    global _warmed_sidebar_expanded
    normalized = None if expanded is None else bool(expanded)
    with _warmed_sidebar_expanded_lock:
        _warmed_sidebar_expanded = normalized


def peek_warmed_sidebar_expanded() -> bool | None:
    with _warmed_sidebar_expanded_lock:
        return _warmed_sidebar_expanded


def clear_warmed_sidebar_expanded() -> None:
    store_warmed_sidebar_expanded(None)


__all__ = [
    "clear_warmed_sidebar_expanded",
    "peek_warmed_sidebar_expanded",
    "store_warmed_sidebar_expanded",
]
