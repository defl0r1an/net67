from __future__ import annotations

import time

from log.log import log


def collect_deferred_maintenance_payload() -> dict:
    started_at = time.perf_counter()
    telega_found_path = None
    notifications: list[dict] = []

    try:
        try:
            from startup.telega_check import _check_telega_installed, build_telega_notification

            telega_found_path = _check_telega_installed()
            log(
                "Telega deferred check: "
                f"found={'yes' if bool(telega_found_path) else 'no'}"
                + (f", value={telega_found_path}" if telega_found_path else ""),
                "⏱ STARTUP",
            )
            if telega_found_path:
                log(f"Обнаружена Telega Desktop: {telega_found_path}", "🚨 TELEGA")
                telega_notification = build_telega_notification(found_path=str(telega_found_path))
                if telega_notification is not None:
                    notifications.append(telega_notification)
        except Exception:
            telega_found_path = None
    except Exception as exc:
        log(f"Ошибка поздних служебных проверок: {exc}", "❌ ERROR")
    finally:
        try:
            log(
                f"Deferred maintenance notifications collected: count={len(notifications)}",
                "⏱ STARTUP",
            )
        except Exception:
            pass

    return {
        "notifications": notifications,
        "telega_found_path": telega_found_path,
        "duration_ms": int((time.perf_counter() - started_at) * 1000),
    }
