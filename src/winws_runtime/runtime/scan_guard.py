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
from typing import Callable


_DEFAULT_TTL_SECONDS = 1800.0

_lock = threading.Lock()
_active_until = 0.0
_listeners: list[Callable[[bool], None]] = []


def add_scan_listener(listener: Callable[[bool], None]) -> None:
    """Подписка на начало и конец проверки стратегий.

    Нужна интерфейсу. Сканер снимал обход молча, и кнопка «Включить»
    оставалась нажимаемой всю проверку: запуск отклонялся уже после
    нажатия, а человек видел исправную на вид кнопку. Слушатель
    вызывается из потока сканера — хранилище состояния само доставит
    оповещение в главный поток.
    """
    with _lock:
        if listener not in _listeners:
            _listeners.append(listener)


def mark_external_winws_scan_active(active: bool, *, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
    global _active_until
    with _lock:
        if active:
            _active_until = time.monotonic() + max(1.0, float(ttl_seconds))
        else:
            _active_until = 0.0
        listeners = list(_listeners)
    for listener in listeners:
        try:
            listener(bool(active))
        except Exception:
            # Слушатель — оформление. Сорвать из-за него проверку нельзя.
            pass


def is_external_winws_scan_active() -> bool:
    with _lock:
        return time.monotonic() < _active_until
