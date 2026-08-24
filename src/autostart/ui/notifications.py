from __future__ import annotations

from app_notifications import advisory_notification


def build_autostart_error_notification(message: str) -> dict:
    text = str(message or "").strip()
    if not text:
        text = "Windows не смог создать ярлык автозапуска."

    return advisory_notification(
        level="error",
        title="Автозапуск не включён",
        content=text,
        source="autostart.gui",
        presentation="infobar",
        queue="immediate",
        duration=12000,
        dedupe_key=f"autostart.gui.error:{' '.join(text.split()).lower()}",
        dedupe_window_ms=2000,
    )


__all__ = ["build_autostart_error_notification"]
