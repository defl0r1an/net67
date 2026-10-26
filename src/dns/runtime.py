"""DNS-слой программы: состояние адаптеров и действия над ними.

Цепочка: dns.winapi (вызовы Windows) → dns.adapters (какие адаптеры наши)
→ этот модуль (что сделать) → dns.commands (публичные команды для фасада).

Адаптеры опознаются по GUID. Всё здесь блокирующее и вызывается только из
фоновых воркеров.
"""

from __future__ import annotations

from threading import RLock

from dns import winapi
from dns.adapters import DnsAdapter, build_dns_adapters, is_dns_adapter
from dns.custom_servers import custom_doh_templates
from dns.dns_providers import doh_templates
from dns.state import DnsCommandResult, DnsState
from dns.reachability import check_servers
from log.log import log

_warmed_state: DnsState | None = None
_warmed_lock = RLock()


# ── состояние ─────────────────────────────────────────────────────────────


def load_state() -> DnsState:
    """Адаптеры для страницы DNS с их текущими DNS, наличие IPv6 и DoH."""
    interfaces = winapi.list_interfaces()
    route = winapi.internet_route()
    static = {}
    for interface in interfaces:
        if not is_dns_adapter(interface, route):
            continue
        try:
            static[interface.guid] = winapi.read_static_dns(interface.guid)
        except winapi.DnsWinApiError as exc:
            log(f"DNS: не удалось прочитать DNS адаптера «{interface.name}»: {exc}", "WARNING")
    from dns.line_check import load_line_check

    return DnsState(
        adapters=build_dns_adapters(interfaces, route, static),
        ipv6_available=route.has_ipv6,
        doh_supported=winapi.is_doh_supported(),
        custom_servers=tuple(load_custom_servers()),
        line_check=load_line_check(),
        local_proxy_mode=_local_proxy_mode(),
        local_proxy_server=_local_proxy_server(),
    )


def _local_proxy_mode() -> str:
    try:
        from dns import local_proxy

        return local_proxy.active_mode()
    except Exception as exc:
        log(f"DNS: не удалось узнать режим шифрованного DNS: {exc}", "DEBUG")
        return ""


def load_custom_servers() -> list[dict]:
    """Свои DNS-серверы пользователя из настроек; при сбое чтения — пустой список."""
    try:
        from settings.store import get_custom_dns_servers

        return list(get_custom_dns_servers())
    except Exception as exc:
        log(f"DNS: не удалось прочитать свои DNS-серверы: {exc}", "WARNING")
        return []


def write_doh_templates() -> dict[str, str] | None:
    """{адрес: шаблон DoH} для записи в адаптер или None, если Windows DoH не умеет.

    Шаблоны серверов программы и своих серверов пользователя; при совпадении
    адреса главнее сервер программы.
    """
    if not winapi.is_doh_supported():
        return None
    return {**custom_doh_templates(load_custom_servers()), **doh_templates()}


def _local_proxy_server() -> str:
    try:
        from dns import local_proxy

        return local_proxy.active_server()
    except Exception as exc:
        log(f"DNS: не удалось узнать сервер шифрованного DNS: {exc}", "DEBUG")
        return ""


def warm_state() -> DnsState:
    """Загружает состояние заранее (после запуска), чтобы страница открылась сразу."""
    global _warmed_state
    state = load_state()
    with _warmed_lock:
        _warmed_state = state
    return state


def consume_warmed_state() -> DnsState | None:
    """Отдаёт заранее загруженное состояние один раз."""
    global _warmed_state
    with _warmed_lock:
        state, _warmed_state = _warmed_state, None
    return state


# ── действия ──────────────────────────────────────────────────────────────


def apply_dns(guids: list[str], ipv4: list[str], ipv6: list[str]) -> DnsCommandResult:
    """Прописывает DNS отмеченным адаптерам; пустые списки — вернуть автоматические.

    Обе версии протокола пишутся всегда: если у сервера нет IPv6-адресов,
    IPv6 возвращается в автоматический режим, чтобы на адаптере не осталось
    IPv6-адресов прежнего сервера.

    Пишем только адаптерам, которые сейчас есть на странице: Windows молча
    принимает любой GUID и заводит под него ветку реестра, поэтому
    исчезнувший адаптер надо отсечь до записи.
    """
    guids = list(dict.fromkeys(str(item or "").strip() for item in guids if str(item or "").strip()))
    adapters = load_state().adapters
    names = {adapter.guid: adapter.name for adapter in adapters}
    if _points_at_local_proxy(ipv4, ipv6):
        _remember_dns_before_local_proxy(adapters, guids)
    templates = write_doh_templates()
    reach = check_servers(list(ipv4 or []), list(ipv6 or []), templates) if any(guid in names for guid in guids) else None
    if reach is not None and reach.blocked:
        return DnsCommandResult(success=False, message=reach.blocked, total_count=len(guids))
    errors: list[str] = []
    for guid in guids:
        if guid not in names:
            errors.append(f"адаптер {guid} не найден — он отключён или удалён")
            continue
        try:
            winapi.write_dns(guid, ipv4, ipv6=False, doh_templates=templates)
            winapi.write_dns(guid, ipv6, ipv6=True, doh_templates=templates)
        except (winapi.DnsWinApiError, ValueError) as exc:
            errors.append(f"«{names[guid]}»: {exc}")
    if len(errors) < len(guids):
        winapi.flush_resolver_cache()
    message = "; ".join(errors)
    if message:
        log(f"DNS: {message}", "WARNING")
    return DnsCommandResult(
        success=not errors,
        message=message,
        affected_count=len(guids) - len(errors),
        total_count=len(guids),
        warning="Сервер отвечает обычным DNS, но проверка DoH не получила ответа. Windows может использовать DNS без шифрования." if reach is not None and reach.doh_closed else "",
    )


def _points_at_local_proxy(ipv4, ipv6) -> bool:
    from dns.local_proxy import LOCAL_ADDRESSES

    return any(str(item or "").strip() in LOCAL_ADDRESSES for item in (*(ipv4 or ()), *(ipv6 or ())))


def _remember_dns_before_local_proxy(adapters, guids: list[str]) -> None:
    """Записывает, какой DNS стоял на адаптерах до 127.0.0.1 (dns.local_proxy.remember_previous_dns).

    По этой записи сборка и удаление программы возвращают адаптеру его DNS:
    сбрасывать на автоматический нельзя — у адаптера со статическим адресом
    автоматического DNS нет, и он остался бы без интернета.
    """
    from dns import local_proxy

    wanted = set(guids)
    try:
        local_proxy.remember_previous_dns(
            [
                {
                    "guid": adapter.guid,
                    "name": adapter.name,
                    "ipv4": list(adapter.static_ipv4),
                    "ipv6": list(adapter.static_ipv6),
                    "dhcp": bool(adapter.dhcp),
                }
                for adapter in adapters
                if adapter.guid in wanted
            ]
        )
    except Exception as exc:
        log(f"DNS: прежний DNS адаптеров не записан: {exc}", "WARNING")


def reset_to_auto(guids: list[str]) -> DnsCommandResult:
    return apply_dns(guids, [], [])


def flush_dns_cache() -> DnsCommandResult:
    if winapi.flush_resolver_cache():
        return DnsCommandResult(success=True)
    return DnsCommandResult(success=False, message="Windows не смогла очистить кэш DNS")


# ── шифрованный DNS (встроенный dnscrypt-proxy) ───────────────────────────


def _static_addresses() -> list[str]:
    """Все адреса DNS, прописанные вручную на адаптерах страницы."""
    return [
        address
        for adapter in load_state().adapters
        for address in (*adapter.static_ipv4, *adapter.static_ipv6)
    ]


def start_local_proxy(mode: str, *, upstreams=(), server_name: str = "") -> DnsCommandResult:
    """Запускает шифрованный DNS; адаптеры не трогает — их пишет apply_dns после успеха.

    upstreams и server_name — серверы и название плитки для режима DoH.
    """
    from dns import local_proxy

    result = local_proxy.start(mode, upstreams=tuple(upstreams), server_name=server_name)
    if not result.success:
        log(f"DNS: шифрованный DNS ({mode}) не запущен: {result.message}", "WARNING")
    return DnsCommandResult(success=result.success, message=result.message, listen_ipv6=result.listen_ipv6)


def stop_local_proxy_if_unused() -> bool:
    """После смены DNS: движок убирается, если на 127.0.0.1 больше никто не смотрит."""
    from dns import local_proxy

    return local_proxy.stop_if_unused(_static_addresses())


def repair_local_proxy() -> str:
    """Проверка шифрованного DNS при запуске программы (см. local_proxy.repair)."""
    from dns import local_proxy

    summary = local_proxy.repair(_static_addresses())
    if summary:
        log(f"DNS: {summary}", "INFO")
        winapi.flush_resolver_cache()
    return summary


def adapters_with_static_dns() -> tuple[DnsAdapter, ...]:
    return tuple(adapter for adapter in load_state().adapters if not adapter.is_automatic)


__all__ = [
    "adapters_with_static_dns",
    "apply_dns",
    "consume_warmed_state",
    "flush_dns_cache",
    "load_custom_servers",
    "load_state",
    "repair_local_proxy",
    "reset_to_auto",
    "start_local_proxy",
    "stop_local_proxy_if_unused",
    "warm_state",
    "write_doh_templates",
]
