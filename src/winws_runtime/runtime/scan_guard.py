# winws_runtime/runtime/scan_guard.py
"""Global "external winws scan is running" flag.

BlockCheck's strategy scanner kills all winws processes before a scan and
spawns the canonical winws2 in parallel during it. While a scan is active,
unexpected-exit diagnostics, auto-restart, and foreign-process warnings must
stay silent — the scanner owns the winws lifecycle for that window.

The flag carries a TTL so a scanner that dies without cleanup cannot suppress
diagnostics forever.
"""

from __future__ import annotations

import threading
import time


_DEFAULT_TTL_SECONDS = 1800.0

_lock = threading.Lock()
_active_until = 0.0


def mark_external_winws_scan_active(active: bool, *, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
    global _active_until
    with _lock:
        if active:
            _active_until = time.monotonic() + max(1.0, float(ttl_seconds))
        else:
            _active_until = 0.0


def is_external_winws_scan_active() -> bool:
    with _lock:
        return time.monotonic() < _active_until
