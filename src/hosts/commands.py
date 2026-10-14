from __future__ import annotations

import threading
from hosts.address_words import describe_address_check

from hosts.state import HostsApplyResult, HostsCommandResult, HostsFileText, HostsState


def read_hosts_file():
    from hosts.hosts import safe_read_hosts_file

    return safe_read_hosts_file()


def write_hosts_file(content):
    from hosts.hosts import safe_write_hosts_file

    return safe_write_hosts_file(content)


def restore_hosts_permissions() -> HostsCommandResult:
    from hosts.hosts import restore_hosts_permissions as _restore_hosts_permissions

    success, message = _restore_hosts_permissions()
    return HostsCommandResult(success=bool(success), message=str(message or ""))


def create_hosts_manager(status_callback=None):
    from hosts.hosts import HostsManager

    return HostsManager(status_callback=status_callback)


def create_hosts_runtime(status_callback=None):
    return create_hosts_manager(status_callback=status_callback)


def get_hosts_state(hosts_manager=None) -> HostsState:
    manager = hosts_manager or create_hosts_manager()
    error = ""
    accessible = False
    active_domains: set[str] = set()
    adobe_active = False

    try:
        read_check = getattr(manager, "is_hosts_file_readable", None)
        if callable(read_check):
            accessible = bool(read_check())
        else:
            accessible = bool(manager.is_hosts_file_accessible())
    except Exception as exc:
        error = str(exc)

    if not error:
        try:
            active_domains = set((manager.get_active_domains_map() or {}).keys())
        except Exception as exc:
            error = str(exc)
            active_domains = set()

    try:
        adobe_active = bool(manager.is_adobe_domains_active())
    except Exception:
        adobe_active = False

    return HostsState(
        accessible=accessible,
        active_domains=frozenset(active_domains),
        adobe_active=adobe_active,
        error=error,
    )


def apply_service_profiles(hosts_manager, service_dns: dict[str, str]) -> HostsCommandResult:
    success = bool(hosts_manager.apply_service_dns_selections(service_dns or {}))
    message = "Применено" if success else getattr(hosts_manager, "last_status", None) or "Ошибка"
    return HostsCommandResult(success=success, message=message)


def apply_domain_ip_entries(hosts_manager, domain_ip: dict[str, str]) -> HostsCommandResult:
    """Пишет в hosts готовые пары «домен -> адрес».

    Не путать с apply_service_profiles: та принимает «имя сервиса ->
    профиль DNS» и сама достаёт адреса из каталога. Оркестратор «одной
    кнопки» уже держит готовые пары, и передача их в apply_service_profiles
    заканчивалась сообщением «Не найдено записей hosts для выбранных
    сервисов»: домены принимались за имена сервисов, а адреса — за
    названия профилей.
    """
    success = bool(hosts_manager.apply_domain_ip_map(domain_ip or {}))
    message = "Применено" if success else getattr(hosts_manager, "last_status", None) or "Ошибка"
    return HostsCommandResult(success=success, message=message)


def add_domain_ip_entry(hosts_manager, domain: str, ip: str) -> HostsCommandResult:
    manager = hosts_manager or create_hosts_manager()
    success = bool(manager.add_domain_ip_entry(domain, ip))
    message = f"Запись {domain} -> {ip} добавлена" if success else getattr(manager, "last_status", None) or "Ошибка"
    return HostsCommandResult(success=success, message=message)



def clear_hosts(hosts_manager) -> HostsCommandResult:
    success = bool(hosts_manager.clear_hosts_file())
    message = "Записи net67 очищены" if success else getattr(hosts_manager, "last_status", None) or "Ошибка"
    return HostsCommandResult(success=success, message=message)


def add_adobe_domains(hosts_manager) -> HostsCommandResult:
    success = bool(hosts_manager.add_adobe_domains())
    message = "Adobe заблокирован" if success else getattr(hosts_manager, "last_status", None) or "Ошибка"
    return HostsCommandResult(success=success, message=message)


def remove_adobe_domains(hosts_manager) -> HostsCommandResult:
    success = bool(hosts_manager.remove_adobe_domains())
    message = "Adobe разблокирован" if success else getattr(hosts_manager, "last_status", None) or "Ошибка"
    return HostsCommandResult(success=success, message=message)


def execute_hosts_operation(hosts_manager, operation: str, payload=None) -> HostsCommandResult:
    if operation == "apply_selection":
        return apply_service_profiles(hosts_manager, payload or {})
    if operation == "clear_all":
        return clear_hosts(hosts_manager)
    if operation == "adobe_add":
        return add_adobe_domains(hosts_manager)
    if operation == "adobe_remove":
        return remove_adobe_domains(hosts_manager)
    return HostsCommandResult(success=False, message="Неизвестная операция")


def refresh_applied_selection(hosts_manager=None) -> HostsCommandResult:
    """При запуске переписывает уже применённый блок hosts, если каталог сменил адреса."""
    from log.log import log

    manager = hosts_manager or create_hosts_manager(
        status_callback=lambda message: log(f"Hosts при запуске: {message}", "DEBUG")
    )
    from hosts.hosts import HOSTS_EDIT_LOCK

    # Выбор читаем под тем же замком, что и файл. Прочитай его раньше — и
    # человек, успевший между чтением и записью применить на странице
    # hosts другой профиль, получил бы обратно прежние адреса.
    with HOSTS_EDIT_LOCK:
        selection = _hand_telegram_to_proxy_page(load_user_selection())
        changed, reason = manager.refresh_applied_service_selection(
            selection,
            has_saved_selection=bool(selection),
        )
    write_failed = not changed and reason not in ("", "адреса в hosts уже актуальны", "блока net67 в hosts нет", "выбор сервисов не сохранён", "IPv6 сейчас недоступен, а в блоке есть IPv6-записи")
    _settle_overlay_after_refresh(write_failed=write_failed)
    return HostsCommandResult(success=not write_failed, message=reason, changed=bool(changed))


def _hand_telegram_to_proxy_page(selection: dict[str, str]) -> dict[str, str]:
    """Переносит включённую плитку Telegram на страницу Telegram Proxy.

    Плитки Telegram в редакторе больше нет (см. ``TELEGRAM_HOSTS_SERVICE``
    в ``hosts/proxy_domains.py``). Без переноса сверка ниже переписала бы
    блок net67 без доменов Telegram, и у того, кто плитку включал, веб-
    версия перестала бы открываться после обновления — молча.

    Сначала пишем блок прокси, потом убираем Telegram из выбора. Запись
    не удалась — выбор не трогаем, и следующий запуск попробует снова.
    Файл тот же, что у блока net67, так что сверка ниже в этом случае
    тоже ничего не запишет.
    """
    from log.log import log
    from telegram_proxy.telegram_hosts import (
        TelegramHostsError,
        add_telegram_hosts,
        split_hosts_editor_selection,
    )

    kept, found, enabled = split_hosts_editor_selection(selection)
    if not found:
        return selection
    if enabled:
        try:
            add_telegram_hosts()
        except TelegramHostsError as exc:
            log(f"Hosts при запуске: Telegram не перенесён на страницу прокси: {exc}", "WARNING")
            return selection
        log("Hosts при запуске: записи Telegram перенесены на страницу Telegram Proxy", "INFO")
    if not save_user_selection(kept):
        log("Hosts при запуске: выбор без Telegram не сохранён", "WARNING")
    return kept


def load_user_selection() -> dict[str, str]:
    from hosts.proxy_domains import load_user_hosts_selection

    try:
        return dict(load_user_hosts_selection() or {})
    except Exception:
        return {}


def save_user_selection(selection: dict[str, str]) -> bool:
    from hosts.proxy_domains import save_user_hosts_selection

    try:
        return bool(save_user_hosts_selection(dict(selection)))
    except Exception:
        return False


def get_catalog_signature():
    from hosts.proxy_domains import get_hosts_catalog_signature

    try:
        return get_hosts_catalog_signature()
    except Exception:
        return None


def invalidate_catalog_cache() -> None:
    from hosts.proxy_domains import invalidate_hosts_catalog_cache

    try:
        invalidate_hosts_catalog_cache()
    except Exception:
        pass


def read_active_domains_map(hosts_manager) -> dict[str, str]:
    if hosts_manager is None:
        return {}
    try:
        return dict(hosts_manager.get_active_domains_map() or {})
    except Exception:
        return {}


def read_active_domain_ip_map(hosts_manager) -> dict[str, list[str]]:
    if hosts_manager is None:
        return {}
    try:
        get_active_domain_ip_map = getattr(hosts_manager, "get_active_domain_ip_map", None)
        if callable(get_active_domain_ip_map):
            active_ip_map = get_active_domain_ip_map() or {}
            return {
                str(domain or "").strip().casefold(): [
                    str(ip or "").strip()
                    for ip in (ips if isinstance(ips, (list, tuple, set, frozenset)) else [ips])
                    if str(ip or "").strip()
                ]
                for domain, ips in active_ip_map.items()
                if str(domain or "").strip()
            }
    except Exception:
        pass

    return {
        domain: [ip]
        for domain, ip in read_active_domains_map(hosts_manager).items()
        if domain and ip
    }


def build_services_catalog_plan(
    *,
    hosts_runtime,
    current_selection: dict[str, str],
    direct_title: str,
    ai_title: str,
    other_title: str,
):
    import hosts.page_plans as hosts_page_plans

    active_domains_map = read_active_domain_ip_map(hosts_runtime)
    return hosts_page_plans.build_services_catalog_plan(
        current_selection=current_selection,
        active_domains_map=active_domains_map,
        direct_title=direct_title,
        ai_title=ai_title,
        other_title=other_title,
    )


def get_hosts_path_str() -> str:
    import os

    from utils.subproc import get_system32_path

    try:
        if os.name == "nt":
            sys_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
            if sys_root:
                return os.path.join(sys_root, "System32", "drivers", "etc", "hosts")
        return os.path.join(get_system32_path(), "drivers", "etc", "hosts")
    except Exception:
        return os.path.join(get_system32_path(), "drivers", "etc", "hosts")


def open_hosts_file() -> HostsCommandResult:
    import ctypes
    import os

    hosts_path = get_hosts_path_str()
    if not os.path.exists(hosts_path):
        return HostsCommandResult(False, f"Файл не найден: {hosts_path}")

    try:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", "notepad.exe", hosts_path, None, 1)
        return HostsCommandResult(True, hosts_path)
    except Exception as exc:
        return HostsCommandResult(False, str(exc))


# ── страница Hosts: снимок, черновик, весь файл ─────────────────────


def load_page_snapshot():
    """Снимок страницы Hosts: каталог, текст hosts и доступ. Только чтение."""
    from hosts.page_snapshot import load_page_snapshot as _load_page_snapshot

    return _load_page_snapshot()


def apply_hosts_draft(selection: dict[str, str], adobe: bool | None = None) -> HostsApplyResult:
    """Записывает черновик страницы одной операцией и возвращает свежий снимок.

    selection — полный выбор «сервис → профиль»; adobe — None, если блок
    Adobe не меняли. Запись идёт теми же методами HostsManager, что и у
    «одной кнопки», — под общим замком hosts.
    """
    from log.log import log

    manager = create_hosts_manager(
        status_callback=lambda message: log(f"Hosts: {message}", "DEBUG")
    )
    selection = dict(selection or {})
    success = bool(manager.apply_service_dns_selections(selection))
    message = str(manager.last_status or "")
    if success:
        save_user_selection(selection)
    if success and adobe is not None:
        success = bool(manager.add_adobe_domains() if adobe else manager.remove_adobe_domains())
        message = str(manager.last_status or message)

    # Причину смотрим тем же способом, каким её проверяет сама запись:
    # открыть файл на дозапись. По тексту сообщения угадывать нельзя —
    # у отказа антивируса и у ошибки каталога слова разные, а путь один.
    access_denied = False
    if not success:
        try:
            access_denied = not manager.is_hosts_file_accessible()
        except Exception:
            access_denied = False

    snapshot = None
    try:
        snapshot = load_page_snapshot()
    except Exception as exc:
        log(f"Hosts: не удалось перечитать состояние после записи: {exc}", "WARNING")
    return HostsApplyResult(success=success, message=message, snapshot=snapshot, access_denied=access_denied)


def enable_hosts_services(service_names: tuple[str, ...]) -> HostsApplyResult:
    """Добавляет явно запрошенные сервисы, сохраняя весь текущий выбор."""
    from hosts.defaults import choose_profile
    from hosts.hosts import HOSTS_EDIT_LOCK

    # Снимок и запись под одним замком: другая страница не должна потерять
    # своё переключение между чтением и добавлением трёх сервисов.
    with HOSTS_EDIT_LOCK:
        snapshot = load_page_snapshot()
        if not snapshot.readable:
            return HostsApplyResult(False, "Не удалось прочитать текущий hosts. Включение отменено", snapshot)
        selection = {entry.name: entry.current for entry in snapshot.services if entry.current}
        for name in service_names:
            entry = snapshot.service(name)
            if entry is None or entry.unavailable_reason or not entry.profiles:
                return HostsApplyResult(False, f"Для {name} нет доступного профиля hosts", snapshot)
            if not entry.current:
                selection[name] = choose_profile(entry.profiles)
        if all(snapshot.service(name).current for name in service_names):
            return HostsApplyResult(True, "Профили ИИ уже включены", snapshot)
        return apply_hosts_draft(selection, None)


def disable_hosts_services(service_names: tuple[str, ...]) -> HostsApplyResult:
    """Выключает запрошенные сервисы, сохраняя остальные записи и профили."""
    from hosts.hosts import HOSTS_EDIT_LOCK

    with HOSTS_EDIT_LOCK:
        snapshot = load_page_snapshot()
        if not snapshot.readable:
            return HostsApplyResult(False, "Не удалось прочитать текущий hosts. Выключение профилей отменено", snapshot)
        selection = {entry.name: entry.current for entry in snapshot.services
                     if entry.current and entry.name not in service_names}
        if not any(entry.current for entry in snapshot.services if entry.name in service_names):
            return HostsApplyResult(True, "Профили ИИ уже выключены", snapshot)
        return apply_hosts_draft(selection, None)


def load_hosts_text() -> HostsFileText:
    """Весь текст hosts для редактора. Только чтение: файл не создаётся."""
    from hosts.hosts import HOSTS_PATH, is_file_readonly, safe_read_hosts_file

    exists = HOSTS_PATH.exists()
    text = safe_read_hosts_file() if exists else ""
    return HostsFileText(
        text=text or "",
        path=str(HOSTS_PATH),
        exists=exists,
        readable=text is not None,
        read_only=bool(exists and is_file_readonly(HOSTS_PATH)),
    )


def save_hosts_text(text: str) -> HostsCommandResult:
    """Записывает весь текст hosts из редактора как есть.

    Защиту «только чтение» не снимает: это делает только кнопка
    «Восстановить права». Пишет под общим замком hosts — редактор файла
    ещё один писатель, и без замка его сохранение и запись «одной кнопки»
    затирали бы друг друга.
    """
    from hosts.hosts import HOSTS_EDIT_LOCK, HOSTS_PATH, is_file_readonly, safe_write_hosts_file

    if HOSTS_PATH.exists() and is_file_readonly(HOSTS_PATH):
        return HostsCommandResult(
            False,
            "Файл hosts защищён от записи (стоит «только чтение»). Снимите защиту в меню страницы Hosts.",
        )
    content = str(text or "")
    if content and not content.endswith("\n"):
        content += "\n"
    with HOSTS_EDIT_LOCK:
        written = safe_write_hosts_file(content)
    if not written:
        return HostsCommandResult(False, "Не удалось записать файл hosts: нет прав или файл занят.")
    return HostsCommandResult(True, str(HOSTS_PATH), changed=True)


def _fresh_addresses(host: str, want_ipv6: bool) -> list[str]:
    """Адреса имени по шифрованному DNS: обычному ответу для таких имён в России верить нельзя."""
    from utils.dns_reference import reference_ask
    from utils.dns_wire import TYPE_A, TYPE_AAAA
    from utils.socket_cancel import SocketCancel

    ask = reference_ask(SocketCancel(), timeout_s=3.0)
    found: list[str] = []
    for rtype in (TYPE_A, TYPE_AAAA) if want_ipv6 else (TYPE_A,):
        answer = ask(host, rtype)
        if answer is not None:
            found.extend(answer.values(rtype))
    return found


def check_addresses(selection: dict[str, str] | None = None, *, strict: bool = False, recheck=None, should_stop=None, fresh: bool = False, commit: bool = True):
    """Умный движок: проверяет адреса включённых сервисов и запоминает рабочие (hosts.address_engine).

    ``selection`` — выбор «сервис → профиль»; None — сохранённый выбор. ``strict`` — человек
    только что переключил сервис: мёртвый адрес убирается сразу, без второй проверки.
    ``recheck`` — названия сервисов, которые проверить сейчас (None — все включённые).
    Сам файл hosts здесь не меняется: его переписывает refresh_applied_selection, если
    проверенные адреса отличаются от записанных.
    """
    with _CHECK_LOCK:
        if fresh:
            _PROBE_CACHE.clear()
        return _check_addresses(selection, strict=strict, recheck=recheck, should_stop=should_stop, commit=commit)


def _check_addresses(selection: dict[str, str] | None, *, strict: bool, recheck, should_stop=None, commit: bool = True):
    global _OVERLAY_BEFORE_REFRESH
    import time

    from hosts import address_engine, proxy_domains
    from hosts.address_probe import ALIVE, check_address, sweep
    from hosts.ipv6_detection import is_ipv6_available
    from hosts.relay_check import internet_reachable
    from log.log import log

    chosen = load_user_selection() if selection is None else dict(selection or {})
    active = {
        name: profile.strip()
        for name, profile in chosen.items()
        if isinstance(name, str) and isinstance(profile, str) and profile.strip().lower() not in _OFF_PROFILES
    }
    cancelled = should_stop or (lambda: False)
    if cancelled():
        return None

    def _probe(address: str, host: str, front: str):
        if cancelled():
            from hosts.address_probe import Probe, UNKNOWN
            return Probe(UNKNOWN)
        # Адрес, который ответил несколько минут назад, заново не проверяется: иначе каждое
        # переключение любого тумблера перепроверяло бы все включённые сервисы.
        key = (address, host, front)
        cached = _PROBE_CACHE.get(key)
        if cached is not None and time.monotonic() - cached[0] < _ALIVE_CACHE_S:
            return cached[1]
        result = check_address(address, host, front=front)
        if result.verdict == ALIVE:
            _PROBE_CACHE[key] = (time.monotonic(), result)
        else:
            _PROBE_CACHE.pop(key, None)
        return result

    previous = proxy_domains.get_engine_overlay()
    catalog = proxy_domains.load_shipped_catalog()
    overlay, report = address_engine.check_selection(
        active,
        catalog=catalog,
        previous=previous,
        relays=proxy_domains.relay_addresses_of(catalog),
        probe=_probe,
        resolve=lambda host, ipv6: [] if cancelled() else _fresh_addresses(host, ipv6),
        network_ok=internet_reachable,
        ipv6=bool(is_ipv6_available()),
        strict=strict,
        recheck=recheck,
        sweep=lambda addresses: {} if cancelled() else sweep(addresses),
    )
    if cancelled():
        return None
    if not commit:
        return overlay, report
    if overlay is not None:
        if selection is None and report.changed:
            _OVERLAY_BEFORE_REFRESH = previous
        proxy_domains.set_engine_overlay(overlay)
    text = describe_address_check(report)
    log(f"Hosts, проверка адресов: проверено {report.checked}, изменилось: {report.changed}. {text}".strip(), "INFO")
    return report






def _settle_overlay_after_refresh(*, write_failed: bool) -> None:
    """После сверки hosts: если новые адреса записать не удалось, вернуть набор, который записан."""
    global _OVERLAY_BEFORE_REFRESH
    from hosts import proxy_domains
    from log.log import log

    with _CHECK_LOCK:
        before, _OVERLAY_BEFORE_REFRESH = _OVERLAY_BEFORE_REFRESH, None
        if write_failed and before is not None:
            proxy_domains.set_engine_overlay(before)
            log("Hosts: проверенные адреса записать не удалось — оставлены те, что уже в файле", "WARNING")


_OFF_PROFILES = ("", "off", "откл", "откл.", "0", "false")
_ALIVE_CACHE_S = 600.0
_PROBE_CACHE = {}
_CHECK_LOCK = threading.RLock()
_OVERLAY_BEFORE_REFRESH = None
