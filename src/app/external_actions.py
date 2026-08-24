from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExternalActionResult:
    ok: bool
    error: str = ""


def open_url(url: str) -> ExternalActionResult:
    from app.external_commands import open_url as command_open_url

    return command_open_url(url)
