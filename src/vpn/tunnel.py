"""Логика управления туннелем AmneziaWG.

Туннель поднимается службой Windows: клиент amneziawg.exe принимает путь
к .conf и регистрирует службу, которая создаёт сетевой адаптер. Так же
работает официальный клиент AmneziaVPN.

Модуль чистый — только имена, команды и разбор состояний. Вызовы WinAPI
и запуск процессов живут в vpn/tunnel_runtime.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class TunnelState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    ERROR = "error"


#: Коды состояний служб Windows (см. autostart/service_api.py).
SERVICE_STOPPED = 0x00000001
SERVICE_START_PENDING = 0x00000002
SERVICE_STOP_PENDING = 0x00000003
SERVICE_RUNNING = 0x00000004

_STATE_BY_CODE = {
    SERVICE_STOPPED: TunnelState.DISCONNECTED,
    SERVICE_START_PENDING: TunnelState.CONNECTING,
    SERVICE_STOP_PENDING: TunnelState.DISCONNECTING,
    SERVICE_RUNNING: TunnelState.CONNECTED,
}

#: Имя туннеля = имя файла .conf. Служба именуется по нему.
DEFAULT_TUNNEL_NAME = "net67"

#: Префиксы имени службы.
#:
#: wireguard-windows регистрирует службу как WireGuardTunnel$<имя>, а
#: форк AmneziaWG использует своё имя. Точный префикс зависит от версии
#: клиента, поэтому не угадываем: проверяем все известные варианты и
#: берём тот, который реально существует в системе.
SERVICE_NAME_PREFIXES: tuple[str, ...] = (
    "AmneziaWGTunnel$",
    "AmneziaWG$",
    "WireGuardTunnel$",
)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")


def normalize_tunnel_name(name: str | None) -> str:
    """Приводит имя к пригодному для имени файла и службы виду."""
    cleaned = _SAFE_NAME_RE.sub("-", str(name or "").strip()).strip("-")
    return cleaned[:32] or DEFAULT_TUNNEL_NAME


def conf_file_name(tunnel_name: str) -> str:
    return f"{normalize_tunnel_name(tunnel_name)}.conf"


def service_name_candidates(tunnel_name: str) -> tuple[str, ...]:
    safe = normalize_tunnel_name(tunnel_name)
    return tuple(f"{prefix}{safe}" for prefix in SERVICE_NAME_PREFIXES)


def build_install_command(exe_path: str, conf_path: str) -> list[str]:
    """Команда регистрации службы туннеля."""
    return [str(exe_path), "/installtunnelservice", str(conf_path)]


def build_uninstall_command(exe_path: str, tunnel_name: str) -> list[str]:
    return [str(exe_path), "/uninstalltunnelservice", normalize_tunnel_name(tunnel_name)]


def map_service_state(code: int | None) -> TunnelState:
    if code is None:
        return TunnelState.DISCONNECTED
    return _STATE_BY_CODE.get(int(code), TunnelState.ERROR)


@dataclass(frozen=True, slots=True)
class TunnelStatus:
    state: TunnelState
    service_name: str = ""
    message: str = ""

    @property
    def is_active(self) -> bool:
        return self.state in (TunnelState.CONNECTED, TunnelState.CONNECTING)


def describe_state(state: TunnelState) -> str:
    return {
        TunnelState.DISCONNECTED: "Отключено",
        TunnelState.CONNECTING: "Подключение...",
        TunnelState.CONNECTED: "Подключено",
        TunnelState.DISCONNECTING: "Отключение...",
        TunnelState.ERROR: "Ошибка",
    }[state]


def build_failure_hint(*, winws_running: bool) -> str:
    """Подсказка, когда туннель не поднялся.

    Обход DPI может как помогать WireGuard-рукопожатию пройти сквозь
    фильтрацию, так и ломать его, перекраивая пакеты. Оба исхода
    встречаются, поэтому при неудаче прямо предлагаем проверить.
    """
    if winws_running:
        return (
            "Туннель не поднялся. Сейчас работает обход DPI — он может "
            "мешать рукопожатию WireGuard. Попробуйте остановить обход "
            "и подключиться снова."
        )
    return (
        "Туннель не поднялся. Проверьте доступность сервера кнопкой "
        "проверки и правильность ключа."
    )


def validate_profile_for_tunnel(profile) -> tuple[bool, str]:
    """Проверяет, что профиля достаточно для поднятия туннеля."""
    if profile is None:
        return (False, "Профиль не выбран")
    if not getattr(profile, "private_key", ""):
        return (False, "В профиле нет приватного ключа")
    if not getattr(profile, "public_key", ""):
        return (False, "В профиле нет публичного ключа сервера")
    if not getattr(profile, "endpoint_host", ""):
        return (False, "В профиле не указан адрес сервера")
    if not getattr(profile, "address", ""):
        return (
            False,
            "В профиле нет адреса в туннеле (Address). Без него адаптер не создать.",
        )
    return (True, "")


__all__ = [
    "DEFAULT_TUNNEL_NAME",
    "SERVICE_NAME_PREFIXES",
    "TunnelState",
    "TunnelStatus",
    "build_failure_hint",
    "build_install_command",
    "build_uninstall_command",
    "conf_file_name",
    "describe_state",
    "map_service_state",
    "normalize_tunnel_name",
    "service_name_candidates",
    "validate_profile_for_tunnel",
]
