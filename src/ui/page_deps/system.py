from __future__ import annotations

from app.page_names import PageName
from ui.page_deps.types import (
    DnsPageDeps,
    HostsPageDeps,
    UpdateRuntimeActions,
)


def build_network_page_kwargs(*, page_name: PageName, dns_feature) -> dict:
    _ = page_name
    return {
        "deps": DnsPageDeps(dns_feature=dns_feature),
    }


def build_hosts_page_kwargs(*, page_name: PageName, hosts_feature) -> dict:
    _ = page_name
    return {
        "deps": HostsPageDeps(hosts_feature=hosts_feature),
    }


def build_winws_log_analyzer_page_kwargs(*, page_name: PageName) -> dict:
    _ = page_name
    # Страница самодостаточна: путь к папке логов берёт из единого APPLICATION_PATHS.
    return {}


def build_vpn_page_kwargs(*, page_name: PageName) -> dict:
    _ = page_name
    # Профили и клиент AmneziaWG страница находит сама через APPLICATION_PATHS.
    return {}


def build_configs_page_kwargs(*, page_name: PageName) -> dict:
    _ = page_name
    # Настройки читаются и пишутся напрямую через settings.store.
    return {}


def build_support_page_kwargs(*, page_name: PageName, external_actions_feature) -> dict:
    _ = page_name

    def _create_support_open_action_worker(request_id: int, *, action_name: str, parent=None):
        import about.commands as about_commands

        # Каналы автора (Telegram zaprethelp и Discord) удалены, осталось
        # только обращение по адресу из branding.py.
        actions = {
            "discussions": about_commands.open_support_discussions,
        }
        action_key = str(action_name or "").strip()
        if action_key not in actions:
            return None
        return external_actions_feature.create_external_action_worker(
            request_id,
            action_name=action_name,
            action_fn=actions[action_key],
            parent=parent,
        )

    return {
        "create_open_action_worker": _create_support_open_action_worker,
    }


def build_autostart_page_kwargs(*, page_name: PageName, autostart_feature, show_page, notify, ui_state_store) -> dict:
    _ = page_name
    return {
        "autostart_feature": autostart_feature,
        "notify": notify,
        "ui_state_store": ui_state_store,
    }


def build_about_page_kwargs(*, page_name: PageName, external_actions_feature, show_page, ui_state_store) -> dict:
    _ = page_name

    def _create_about_open_action_worker(request_id: int, *, action_name: str, parent=None):
        import about.commands as about_commands

        # Удалены действия, которые вели на ресурсы автора исходного
        # проекта: Telegram-каналы zaprethelp и bypassblock, его Discord,
        # бот подписки и репозитории zapret-kvn. Остались только те, что
        # ведут на адреса из branding.py.
        actions = {
            "support_discussions": about_commands.open_support_discussions,
            "forum_for_beginners": about_commands.open_docs_home,
        }
        action_key = str(action_name or "").strip()
        if action_key not in actions:
            # Обработчик мог остаться в неудалённом виджете — молча
            # игнорируем вместо KeyError.
            return None
        return external_actions_feature.create_external_action_worker(
            request_id,
            action_name=action_name,
            action_fn=actions[action_key],
            parent=parent,
        )

    return {
        "open_updates": lambda: show_page(PageName.SERVERS, allow_internal=True),
        "create_open_action_worker": _create_about_open_action_worker,
        "ui_state_store": ui_state_store,
    }


def build_servers_page_kwargs(
    *,
    page_name: PageName,
    runtime_feature,
    updater_feature,
    external_actions_feature,
    show_page,
    request_exit,
) -> dict:
    _ = page_name

    def _open_parent_page() -> None:
        """Возврат из «Серверов» — в «Обход», а не в «О программе».

        Крошка вела на AboutPage, а та убрана из интерфейса
        (`is_hidden=True` в схеме навигации): человек уходил на
        страницу, которой нет в панели, и возвращался только через
        боковое меню.

        Точку входа по-прежнему берём из `MODE_ENTRY_PAGES`, а не
        подставляем страницу напрямую: способ запуска остался один, но
        карта входа — то место, где это записано, и дублировать её
        здесь значило бы завести второй источник правды.
        """
        from settings.mode import DEFAULT_LAUNCH_METHOD
        from ui.navigation.schema import get_mode_entry_page

        show_page(get_mode_entry_page(DEFAULT_LAUNCH_METHOD))

    def _mark_runtime_stopped_after_update() -> None:
        runtime_service = runtime_feature.objects.runtime_service
        if runtime_service is not None:
            runtime_service.mark_stopped(clear_error=True)

    def _create_changelog_link_open_worker(request_id: int, *, url: str, parent=None):
        return external_actions_feature.create_open_url_worker(
            request_id,
            url=url,
            parent=parent,
        )

    return {
        "runtime_actions": UpdateRuntimeActions(
            is_any_running=runtime_feature.is_any_running,
            shutdown_sync=runtime_feature.shutdown_sync,
            is_available=runtime_feature.is_available,
            restart=runtime_feature.restart,
            mark_stopped=_mark_runtime_stopped_after_update,
            request_exit=request_exit,
        ),
        "updater_feature": updater_feature,
        "open_about": _open_parent_page,
        "create_changelog_link_open_worker": _create_changelog_link_open_worker,
    }


def build_blockcheck_page_kwargs(
    *,
    page_name: PageName,
    blockcheck_feature,
    diagnostics_feature,
    dns_feature,
    runtime_feature,
) -> dict:
    _ = page_name

    def _create_strategy_scan_worker(**kwargs):
        return blockcheck_feature.create_strategy_scan_worker(
            **kwargs,
            shutdown_sync=runtime_feature.shutdown_sync,
        )

    return {
        "blockcheck_feature": blockcheck_feature,
        "diagnostics_feature": diagnostics_feature,
        "dns_feature": dns_feature,
        "create_strategy_scan_worker": _create_strategy_scan_worker,
    }


def build_logs_page_kwargs(*, page_name: PageName, logs_feature) -> dict:
    _ = page_name
    return {
        "logs_feature": logs_feature,
    }


def build_telegram_proxy_page_kwargs(*, page_name: PageName, runtime_feature, telegram_proxy_feature) -> dict:
    _ = page_name

    def _get_zapret_running() -> bool:
        return bool(runtime_feature.is_running())

    return {
        "telegram_proxy_feature": telegram_proxy_feature,
        "get_zapret_running": _get_zapret_running,
    }


__all__ = [
    "build_about_page_kwargs",
    "build_autostart_page_kwargs",
    "build_blockcheck_page_kwargs",
    "build_hosts_page_kwargs",
    "build_logs_page_kwargs",
    "build_network_page_kwargs",
    "build_premium_page_kwargs",
    "build_servers_page_kwargs",
    "build_winws_log_analyzer_page_kwargs",
    "build_support_page_kwargs",
    "build_telegram_proxy_page_kwargs",
]
