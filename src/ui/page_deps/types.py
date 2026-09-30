from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class DnsPageDeps:
    dns_feature: object


@dataclass(frozen=True, slots=True)
class HostsPageDeps:
    hosts_feature: object
    open_file_page: Callable[[], object]


@dataclass(frozen=True, slots=True)
class HostsFilePageDeps:
    hosts_feature: object
    open_hosts_page: Callable[[], object]


@dataclass(frozen=True, slots=True)
class DpiRuntimeActions:
    handle_launch_method_changed: Callable[..., object]


@dataclass(frozen=True, slots=True)
class UpdateRuntimeActions:
    is_any_running: Callable[..., bool]
    shutdown_sync: Callable[..., object]
    is_available: Callable[..., bool]
    restart: Callable[..., object]
    mark_stopped: Callable[..., object]
    request_exit: Callable[..., object]


__all__ = [
    "DpiRuntimeActions",
    "DnsPageDeps",
    "HostsFilePageDeps",
    "HostsPageDeps",
    "UpdateRuntimeActions",
]
