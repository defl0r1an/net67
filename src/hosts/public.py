from __future__ import annotations

from hosts.commands import (
    add_adobe_domains,
    apply_domain_ip_entries,
    apply_service_profiles,
    clear_hosts,
    create_hosts_runtime,
    execute_hosts_operation,
    get_catalog_signature,
    get_hosts_path_str,
    get_hosts_state,
    build_services_catalog_plan,
    invalidate_catalog_cache,
    load_user_selection,
    refresh_applied_selection,
    open_hosts_file,
    read_hosts_file,
    read_active_domains_map,
    remove_adobe_domains,
    restore_hosts_permissions,
    save_user_selection,
    write_hosts_file,
)
from hosts.geo_sites import GeoSites, load_geo_sites
from hosts.state import HostsCommandResult, HostsState

__all__ = [
    "GeoSites",
    "load_geo_sites",
    "HostsCommandResult",
    "HostsState",
    "add_adobe_domains",
    "apply_domain_ip_entries",
    "apply_service_profiles",
    "clear_hosts",
    "create_hosts_runtime",
    "execute_hosts_operation",
    "get_catalog_signature",
    "get_hosts_path_str",
    "get_hosts_state",
    "build_services_catalog_plan",
    "invalidate_catalog_cache",
    "load_user_selection",
    "refresh_applied_selection",
    "open_hosts_file",
    "read_hosts_file",
    "read_active_domains_map",
    "remove_adobe_domains",
    "restore_hosts_permissions",
    "save_user_selection",
    "write_hosts_file",
]

# Страница Hosts: снимок, черновик и весь файл (перенесено из zapret).
from hosts.commands import apply_hosts_draft, load_hosts_text, load_page_snapshot, save_hosts_text  # noqa: E402
from hosts.state import HostsApplyResult, HostsFileText  # noqa: E402
__all__ = [*__all__, 'apply_hosts_draft', 'load_hosts_text', 'load_page_snapshot', 'save_hosts_text', 'HostsApplyResult', 'HostsFileText']

# Главный сайт сервиса из каталога — для проверки профилей (фасад hosts).
from hosts.proxy_domains import get_service_main_domains  # noqa: E402
__all__ = [*__all__, 'get_service_main_domains']
