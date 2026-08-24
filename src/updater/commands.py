from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class UpdateChannelActionResult:
    ok: bool
    message: str


@dataclass(slots=True)
class ServerFullCheckGateResult:
    telegram_only: bool
    keep_existing_rows: bool
    message: str = ""


def is_auto_update_enabled() -> bool:
    from settings.store import get_auto_update_enabled

    return bool(get_auto_update_enabled())


def set_auto_update_enabled(enabled: bool) -> None:
    from settings.store import set_auto_update_enabled

    set_auto_update_enabled(bool(enabled))


def run_startup_update_check() -> dict:
    from updater.startup_update_check import check_for_update_sync

    return check_for_update_sync()


def open_update_channel(channel: str) -> UpdateChannelActionResult:
    """Открывает телеграм-канал выпусков. Пока открывать нечего.

    Здесь были вписаны каналы автора исходного проекта: кнопка в разделе
    обновлений уводила человека в чужой телеграм, где лежит другая
    программа. Для внутреннего приложения это ещё и утечка — двадцать
    менеджеров ушли бы читать не наши объявления.

    Своего канала у net67 нет, поэтому имя берётся из общего списка
    (`updater.telegram_updater.TELEGRAM_CHANNELS`) и там пусто. Появится
    канал — впишите его туда, кнопка заработает без правок здесь.
    """
    from config.telegram_links import open_telegram_link
    from updater.channel_utils import is_dev_update_channel
    from updater.telegram_updater import TELEGRAM_CHANNELS

    key = "dev" if is_dev_update_channel(channel) else "stable"
    domain = str(TELEGRAM_CHANNELS.get(key) or "").strip()
    if not domain:
        return UpdateChannelActionResult(False, "Канал обновлений не настроен")

    try:
        open_telegram_link(domain)
        return UpdateChannelActionResult(True, domain)
    except Exception as exc:
        return UpdateChannelActionResult(False, str(exc))


def prepare_server_full_check(*, skip_rate_limit: bool = False) -> ServerFullCheckGateResult:
    from updater.rate_limiter import UpdateRateLimiter

    if not bool(skip_rate_limit):
        can_full, message = UpdateRateLimiter.can_check_servers_full()
        if not can_full:
            return ServerFullCheckGateResult(
                telegram_only=True,
                keep_existing_rows=True,
                message=(
                    f"⏱️ Полная проверка VPS заблокирована: {message}. "
                    "fallback=telegram-only"
                ),
            )

    UpdateRateLimiter.record_servers_full_check()
    return ServerFullCheckGateResult(
        telegram_only=False,
        keep_existing_rows=False,
    )


def retry_server_check_without_dpi(*, is_any_running, shutdown_sync) -> tuple[bool, bool, str]:
    if not is_any_running():
        return False, False, ""

    shutdown_result = shutdown_sync(
        reason="server_status_probe_retry",
        include_cleanup=True,
    )
    if bool(getattr(shutdown_result, "still_running", False)):
        return False, False, "DPI не остановился"
    return True, True, ""


def restart_dpi_after_update(*, is_available, restart) -> bool:
    if not is_available():
        return False
    return bool(restart())


def stop_dpi_for_download(*, is_any_running, shutdown_sync) -> bool:
    if not is_any_running():
        return False
    shutdown_sync(reason="updater_download_connectivity", include_cleanup=True)
    return True


def stop_dpi_for_update(*, is_any_running, shutdown_sync, reason: str) -> tuple[bool, bool, str]:
    """Останавливает DPI в отдельной управляемой стадии обновления."""
    if not is_any_running():
        return False, True, ""

    result = shutdown_sync(
        reason=str(reason or "updater_pipeline"),
        include_cleanup=True,
        update_runtime_state=False,
    )
    if bool(getattr(result, "still_running", False)):
        return True, False, "DPI не остановился"
    return True, True, ""
