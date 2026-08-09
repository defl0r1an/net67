"""Diagnostics entry points for Telegram Proxy."""

from telegram_proxy.diagnostics.runner import (
    _build_summary,
    run_all,
)

__all__ = ["_build_summary", "run_all"]

