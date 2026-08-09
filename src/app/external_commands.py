from __future__ import annotations

import webbrowser
from typing import Callable

from app.external_actions import ExternalActionResult


def open_url(url: str, *, open_url_fn: Callable | None = None):
    if open_url_fn is not None:
        return open_url_fn(url)

    target = str(url or "").strip()
    if not target:
        # Ссылки на внешние ресурсы задаются в branding.py и в net67 пустые.
        # Раньше пустой адрес поднимал красную плашку «Пустая ссылка» поверх
        # окна, хотя само действие (например, сбор архива логов) уже прошло
        # успешно. Считаем это тихим отказом: открывать нечего.
        return ExternalActionResult(ok=True)
    try:
        webbrowser.open(target)
        return ExternalActionResult(ok=True)
    except Exception as exc:
        return ExternalActionResult(ok=False, error=str(exc))


__all__ = ["open_url"]
