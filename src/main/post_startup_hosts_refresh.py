from __future__ import annotations

from log.log import log
from main.post_startup_gate import bind_startup_gate, is_startup_host_alive
from main.post_startup_threading import enqueue_subsystem_task, schedule_after

#: Как часто спрашивать шлюз проб, не пора ли умной проверке адресов.
#:
#: Сам интервал проверки — раз в шесть часов, и через перезапуск тоже —
#: решает шлюз (utils.probe_gate.HOSTS_ADDRESSES). Час здесь — только как
#: часто стучаться к нему: программа живёт в трее сутками, и проверка
#: должна случаться не только при запуске.
HOSTS_ADDRESS_CHECK_TICK_MS = 3600 * 1000


def install_hosts_applied_selection_refresh(
    startup_host,
    *,
    hosts_feature=None,
    log_startup_metric,
) -> None:
    """Сразу после запуска обновляет адреса в уже записанном блоке net67 в hosts.

    Если в новой версии каталога у выбранных DNS-профилей сменились адреса,
    пользователю не нужно заново нажимать «применить»: блок переписывается сам.
    Задача ставится в очередь «hosts» раньше прогрева страницы Hosts.

    Следом — умная проверка адресов, если человек включил её в редакторе
    hosts. Выключена — программа сама по адресам не ходит: ни при запуске,
    ни по часам.
    """

    def _run_hosts_applied_selection_refresh() -> None:
        if not is_startup_host_alive(startup_host) or hosts_feature is None:
            return
        try:
            result = hosts_feature.refresh_applied_selection()
        except Exception as exc:
            log(f"Обновление адресов hosts при запуске не выполнено: {exc}", "WARNING")
            return
        changed = bool(getattr(result, "changed", False))
        # Причина нужна в журнале поддержки: по «changed=False» не понять, почему старые адреса остались.
        reason = str(getattr(result, "message", "") or "причина не названа")
        log_startup_metric("StartupHostsAppliedSelectionRefreshFinished", f"changed={changed} ({reason})")

    def _run_smart_address_check() -> None:
        if not is_startup_host_alive(startup_host) or hosts_feature is None:
            return
        from hosts.public import smart_addresses_enabled
        from utils.probe_gate import HOSTS_ADDRESSES, Why, try_background

        # Выключатель — раньше шлюза: шлюз записывает время проверки при выдаче
        # пропуска, и выключенная проверка не должна занимать его окно.
        if not smart_addresses_enabled():
            return
        try:
            permit = try_background(HOSTS_ADDRESSES)
            if permit is None:
                log_startup_metric("StartupHostsAddressCheckSkipped", "шлюз проб: ещё рано или идёт проверка по кнопке")
                return
            with permit:
                result = hosts_feature.smart_check_applied(why=Why.SCHEDULE)
            log_startup_metric(
                "StartupHostsAddressCheckFinished",
                f"changed={bool(getattr(result, 'changed', False))} ({getattr(result, 'message', '') or 'без замечаний'})",
            )
        except Exception as exc:
            log(f"Умная проверка адресов hosts не выполнена: {exc}", "WARNING")

    def _start_hosts_applied_selection_refresh() -> None:
        if not is_startup_host_alive(startup_host):
            return
        enqueue_subsystem_task(
            "hosts",
            "HostsAppliedSelectionRefresh",
            _run_hosts_applied_selection_refresh,
        )

    def _start_smart_address_check() -> None:
        if not is_startup_host_alive(startup_host):
            return
        # Ожидание сети — в своей очереди: остальным задачам запуска оно не мешает.
        enqueue_subsystem_task("dns", "HostsSmartAddressCheck", _run_smart_address_check)

    def _on_periodic_tick() -> None:
        if not is_startup_host_alive(startup_host):
            return
        _start_smart_address_check()
        schedule_after(HOSTS_ADDRESS_CHECK_TICK_MS, _on_periodic_tick)

    def _start_and_schedule() -> None:
        _start_hosts_applied_selection_refresh()
        _start_smart_address_check()
        schedule_after(HOSTS_ADDRESS_CHECK_TICK_MS, _on_periodic_tick)

    bind_startup_gate(
        startup_host.startup_interactive_ready,
        _start_and_schedule,
        is_ready=lambda: bool(startup_host.startup_state.interactive_logged),
    )


__all__ = ["HOSTS_ADDRESS_CHECK_TICK_MS", "install_hosts_applied_selection_refresh"]
