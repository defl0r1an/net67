from __future__ import annotations

from log.log import log
from main.post_startup_gate import bind_startup_gate, is_startup_host_alive
from main.post_startup_dns_workers import schedule_dns_startup


def install_dns_startup(
    startup_host,
    *,
    apply_dns_on_startup_async,
    set_status,
    log_startup_metric,
) -> None:
    def _handle_startup_dns_status(message: str) -> None:
        text = str(message or "").strip()
        if not text:
            return

        silent_prefixes = (
            "DNS будет применен",
            "⚙️ Принудительный DNS отключен",
            "⏳ Применение DNS настроек",
        )
        if text.startswith(silent_prefixes):
            log(f"DNS startup status suppressed from main status: {text}", "DEBUG")
            return

        try:
            set_status(text)
        except Exception as exc:
            log(f"Не удалось обновить DNS-статус запуска: {exc}", "DEBUG")

    def _schedule_dns_startup() -> None:
        if not is_startup_host_alive(startup_host):
            return
        try:
            duration_ms = schedule_dns_startup(
                apply_dns_on_startup_async=apply_dns_on_startup_async,
                status_callback=_handle_startup_dns_status,
            )
            log_startup_metric(
                "StartupPostInitDnsQueued",
                f"{duration_ms}ms",
            )
        except Exception as exc:
            log(f"❌ Ошибка планирования DNS при запуске: {exc}", "ERROR")

    bind_startup_gate(
        startup_host.startup_post_init_ready,
        _schedule_dns_startup,
        is_ready=lambda: bool(startup_host.startup_state.post_init_ready),
    )
