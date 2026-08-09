"""Подъём и остановка туннеля AmneziaWG.

Здесь живут побочные эффекты: запись .conf, ограничение прав на файл,
запуск клиента и опрос службы. Логика имён и состояний — в vpn/tunnel.py.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from log.log import log
from vpn.parser import VpnProfile, to_conf_text
from vpn.tunnel import (
    TunnelState,
    TunnelStatus,
    build_failure_hint,
    build_install_command,
    build_uninstall_command,
    conf_file_name,
    map_service_state,
    normalize_tunnel_name,
    service_name_candidates,
    validate_profile_for_tunnel,
)

#: Имя клиента. Подтверждено по Makefile исходников amneziawg-windows-client:
#: сборка выдаёт именно amneziawg.exe.
CLIENT_EXE_NAME = "amneziawg.exe"

#: Клиент работает через Wintun в пользовательском пространстве, а не через
#: драйвер ядра. Makefile кладёт wintun.dll рядом с exe, и без неё туннель
#: не поднимется — проверяем обе части.
WINTUN_DLL_NAME = "wintun.dll"


def client_path() -> Path:
    """Путь к клиенту рядом с winws, в exe_dir."""
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.exe_dir / CLIENT_EXE_NAME


def wintun_path() -> Path:
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.exe_dir / WINTUN_DLL_NAME


def check_client_files() -> tuple[bool, str]:
    """Проверяет наличие обеих частей клиента."""
    try:
        has_exe = client_path().is_file()
        has_dll = wintun_path().is_file()
    except Exception as exc:
        return (False, f"Не удалось проверить файлы клиента: {exc}")

    missing = []
    if not has_exe:
        missing.append(CLIENT_EXE_NAME)
    if not has_dll:
        missing.append(WINTUN_DLL_NAME)

    if missing:
        return (
            False,
            f"Не хватает файлов клиента AmneziaWG: {', '.join(missing)}. "
            f"Положите их в папку exe рядом с winws.",
        )
    return (True, "")


def is_client_available() -> bool:
    return check_client_files()[0]


def conf_dir() -> Path:
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.settings_dir


def conf_path(tunnel_name: str) -> Path:
    return conf_dir() / conf_file_name(tunnel_name)


def _restrict_file_access(path: Path) -> None:
    """Оставляет доступ к .conf только SYSTEM и администраторам.

    В файле лежит приватный ключ. Служба работает от SYSTEM, поэтому
    читать его обычным пользователям незачем. Так же поступает
    официальный клиент.
    """
    try:
        subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                "*S-1-5-18:F",   # SYSTEM
                "/grant:r",
                "*S-1-5-32-544:F",  # Администраторы
            ],
            check=False,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        log(f"Не удалось ограничить права на конфигурацию VPN: {exc}", "⚠ WARNING")


def write_conf(profile: VpnProfile, *, tunnel_name: str) -> tuple[bool, str, Path | None]:
    path = conf_path(tunnel_name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_conf_text(profile), encoding="utf-8")
    except Exception as exc:
        return (False, f"Не удалось записать конфигурацию: {exc}", None)

    _restrict_file_access(path)
    return (True, "", path)


def _find_service(tunnel_name: str = "") -> str:
    """Ищет реально существующую службу туннеля среди известных имён."""
    try:
        from autostart.service_api import service_exists
    except Exception:
        return ""

    for candidate in service_name_candidates(tunnel_name):
        try:
            if service_exists(candidate):
                return candidate
        except Exception:
            continue
    return ""


def get_status(tunnel_name: str = "") -> TunnelStatus:
    """Текущее состояние туннеля."""
    try:
        from autostart.service_api import get_service_state, service_exists
    except Exception:
        return TunnelStatus(TunnelState.DISCONNECTED, message="Управление службами недоступно")

    for candidate in service_name_candidates(tunnel_name or normalize_tunnel_name("")):
        try:
            if not service_exists(candidate):
                continue
            state = map_service_state(get_service_state(candidate))
            return TunnelStatus(state, service_name=candidate)
        except Exception as exc:
            log(f"Опрос службы туннеля: {exc}", "DEBUG")

    return TunnelStatus(TunnelState.DISCONNECTED)


def connect(profile: VpnProfile, *, tunnel_name: str = "") -> TunnelStatus:
    """Поднимает туннель по профилю."""
    ok, message = validate_profile_for_tunnel(profile)
    if not ok:
        return TunnelStatus(TunnelState.ERROR, message=message)

    available, files_message = check_client_files()
    if not available:
        return TunnelStatus(TunnelState.ERROR, message=files_message)

    name = normalize_tunnel_name(tunnel_name or profile.name or "")
    written, write_message, path = write_conf(profile, tunnel_name=name)
    if not written or path is None:
        return TunnelStatus(TunnelState.ERROR, message=write_message)

    # Существующий туннель снимаем, иначе служба не пересоздастся.
    disconnect(tunnel_name=name)

    try:
        result = subprocess.run(
            build_install_command(str(client_path()), str(path)),
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return TunnelStatus(TunnelState.ERROR, message="Клиент не ответил за 30 секунд")
    except Exception as exc:
        return TunnelStatus(TunnelState.ERROR, message=f"Не удалось запустить клиент: {exc}")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        hint = build_failure_hint(winws_running=_is_winws_running())
        return TunnelStatus(
            TunnelState.ERROR,
            message=f"{hint}\n\nОтвет клиента: {detail}" if detail else hint,
        )

    _set_tunnel_service_manual_start(name)

    status = _wait_for_tunnel(name)
    if status.state is not TunnelState.CONNECTED:
        hint = build_failure_hint(winws_running=_is_winws_running())
        return TunnelStatus(
            TunnelState.ERROR,
            message=f"{hint}\n\n{_describe_service_failure(name)}",
        )
    return status


def _wait_for_tunnel(name: str, *, timeout: float = 15.0) -> TunnelStatus:
    """Ждёт, пока служба туннеля выйдет в рабочее состояние.

    Сразу после /installtunnelservice служба ещё в START_PENDING, и
    мгновенная проверка возвращала DISCONNECTED — подключение считалось
    неудачным, хотя туннель поднимался секундой позже.
    """
    import time

    deadline = time.monotonic() + float(timeout)
    status = get_status(name)
    while time.monotonic() < deadline:
        status = get_status(name)
        if status.state is TunnelState.CONNECTED:
            return status
        if status.state is TunnelState.ERROR:
            return status
        time.sleep(0.3)
    return status


def _set_tunnel_service_manual_start(name: str) -> None:
    """Снимает службу туннеля с автозапуска.

    Клиент AmneziaWG регистрирует её как автозапускаемую, из-за чего
    туннель поднимался бы при каждом входе в Windows, а сторожа
    автозагрузки показывали новую запись. Пользователь просил VPN, а не
    постоянное подключение.
    """
    service = _find_service(name)
    if not service:
        return
    try:
        subprocess.run(
            ["sc.exe", "config", service, "start=", "demand"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        log(f"Не удалось снять службу туннеля с автозапуска: {exc}", "DEBUG")


def _describe_service_failure(name: str) -> str:
    """Собирает то, что известно о неудачном запуске службы."""
    service = _find_service(name)
    if not service:
        return "Служба туннеля не создана."

    parts = [f"Служба: {service}"]
    try:
        result = subprocess.run(
            ["sc.exe", "query", service],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        detail = (result.stdout or "").strip()
        if detail:
            parts.append(detail)
    except Exception as exc:
        log(f"Опрос службы туннеля: {exc}", "DEBUG")

    parts.append(
        "Точную причину пишет сам клиент AmneziaWG в журнал Windows: "
        "Просмотр событий - Журналы Windows - Система, источник Service Control Manager."
    )
    return "\n".join(parts)


def disconnect(*, tunnel_name: str = "") -> TunnelStatus:
    """Снимает туннель."""
    name = normalize_tunnel_name(tunnel_name)

    if is_client_available():
        try:
            subprocess.run(
                build_uninstall_command(str(client_path()), name),
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            log(f"Остановка туннеля через клиент: {exc}", "DEBUG")

    # Подстраховка: если клиент не справился, снимаем службу напрямую.
    service = _find_service(name)
    if service:
        try:
            from autostart.service_api import delete_service, stop_service

            stop_service(service)
            delete_service(service)
        except Exception as exc:
            log(f"Принудительное снятие службы туннеля: {exc}", "DEBUG")

    return TunnelStatus(TunnelState.DISCONNECTED)


def _is_winws_running() -> bool:
    try:
        from winws_runtime.runtime.process_probe import is_any_canonical_winws_running

        return bool(is_any_canonical_winws_running())
    except Exception:
        return False


#: Утилита состояния из amneziawg-tools, форк wg.
TOOLS_EXE_NAME = "awg.exe"


def tools_path() -> Path:
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.exe_dir / TOOLS_EXE_NAME


def get_stats(tunnel_name: str = ""):
    """Статистика туннеля: рукопожатие и объём трафика.

    Возвращает None, если утилиты нет или туннель не поднят. Отсутствие
    статистики не ошибка: адаптер может существовать до первого обмена.
    """
    from vpn.status import parse_dump

    exe = tools_path()
    try:
        if not exe.is_file():
            return None
    except Exception:
        return None

    name = normalize_tunnel_name(tunnel_name)
    try:
        result = subprocess.run(
            [str(exe), "show", name, "dump"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        log(f"Чтение состояния туннеля: {exc}", "DEBUG")
        return None

    if result.returncode != 0:
        return None
    return parse_dump(result.stdout or "")


def forget_conf(tunnel_name: str = "") -> None:
    """Удаляет файл конфигурации с приватным ключом."""
    try:
        path = conf_path(tunnel_name)
        if path.exists():
            os.remove(path)
    except Exception as exc:
        log(f"Удаление конфигурации туннеля: {exc}", "DEBUG")


__all__ = [
    "CLIENT_EXE_NAME",
    "WINTUN_DLL_NAME",
    "TOOLS_EXE_NAME",
    "check_client_files",
    "client_path",
    "get_stats",
    "tools_path",
    "wintun_path",
    "conf_path",
    "connect",
    "disconnect",
    "forget_conf",
    "get_status",
    "is_client_available",
    "write_conf",
]
