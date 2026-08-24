from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from settings.mode import DEFAULT_LAUNCH_METHOD, ZAPRET2_MODE
from app.page_names import PageName


@dataclass(frozen=True, slots=True)
class PageRouteSpec:
    page_name: PageName
    module_name: str
    class_name: str
    route_key: str
    is_top_level: bool
    is_hidden: bool
    launch_modes: tuple[str, ...]
    breadcrumb_parent: PageName | None
    sidebar_group: str | None
    cleanup_priority: int = 10_000
    #: Страница видна только в расширенном режиме. В простом интерфейсе
    #: остаются главная и оформление, остальное открывается кнопкой
    #: «Расширенные настройки».
    is_advanced: bool = True


#: Страницы простого режима. Всё, чего здесь нет, считается расширенным.
#: Держим список явным, а не «по группам»: так добавление новой страницы
#: не протекает в простой интерфейс само собой.
SIMPLE_MODE_PAGES: frozenset[PageName] = frozenset(
    {
        PageName.ZAPRET2_MODE_CONTROL,
    }
)


_COMMON = ()
_WINWS2_MODE = (ZAPRET2_MODE,)


PAGE_ROUTE_SPECS: dict[PageName, PageRouteSpec] = {
    PageName.ZAPRET2_MODE_CONTROL: PageRouteSpec(
        page_name=PageName.ZAPRET2_MODE_CONTROL,
        module_name="presets.ui.control.zapret2.page",
        class_name="Zapret2ModeControlPage",
        route_key="Zapret2ModeControlPage",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_WINWS2_MODE,
        breadcrumb_parent=None,
        sidebar_group="root",
    ),
    PageName.ZAPRET2_USER_PRESETS: PageRouteSpec(
        page_name=PageName.ZAPRET2_USER_PRESETS,
        module_name="presets.ui.zapret2.user_presets_page",
        class_name="Zapret2UserPresetsPage",
        route_key="Zapret2UserPresetsPage_Mode",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_WINWS2_MODE,
        breadcrumb_parent=PageName.ZAPRET2_MODE_CONTROL,
        sidebar_group="settings",
    ),
    PageName.ZAPRET2_PRESET_SETUP: PageRouteSpec(
        page_name=PageName.ZAPRET2_PRESET_SETUP,
        module_name="profile.ui.preset_setup_page",
        class_name="Zapret2PresetSetupPage",
        route_key="Zapret2PresetSetupPage",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_WINWS2_MODE,
        breadcrumb_parent=PageName.ZAPRET2_MODE_CONTROL,
        sidebar_group="settings",
    ),
    PageName.ZAPRET2_PROFILE_SETUP: PageRouteSpec(
        page_name=PageName.ZAPRET2_PROFILE_SETUP,
        module_name="profile.ui.profile_setup_page",
        class_name="Zapret2ProfileSetupPage",
        route_key="Zapret2ProfileSetupPage",
        is_top_level=False,
        is_hidden=True,
        launch_modes=_WINWS2_MODE,
        breadcrumb_parent=PageName.ZAPRET2_PRESET_SETUP,
        sidebar_group=None,
    ),
    PageName.ZAPRET2_PROFILE_ORDER: PageRouteSpec(
        page_name=PageName.ZAPRET2_PROFILE_ORDER,
        module_name="profile.ui.profile_order_page",
        class_name="Zapret2ProfileOrderPage",
        route_key="Zapret2ProfileOrderPage",
        is_top_level=False,
        is_hidden=True,
        launch_modes=_WINWS2_MODE,
        breadcrumb_parent=PageName.ZAPRET2_PRESET_SETUP,
        sidebar_group=None,
    ),
    PageName.ZAPRET2_PRESET_RAW_EDITOR: PageRouteSpec(
        page_name=PageName.ZAPRET2_PRESET_RAW_EDITOR,
        module_name="presets.ui.common.preset_subpage_base",
        class_name="PresetRawEditorPage",
        route_key="Zapret2PresetRawEditor",
        is_top_level=False,
        is_hidden=True,
        launch_modes=_WINWS2_MODE,
        breadcrumb_parent=PageName.ZAPRET2_USER_PRESETS,
        sidebar_group=None,
    ),
    PageName.NETWORK: PageRouteSpec(
        page_name=PageName.NETWORK,
        module_name="dns.ui.page",
        class_name="NetworkPage",
        route_key="NetworkPage",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_COMMON,
        breadcrumb_parent=None,
        sidebar_group="system",
    ),
    PageName.HOSTS: PageRouteSpec(
        page_name=PageName.HOSTS,
        module_name="hosts.ui.page",
        class_name="HostsPage",
        route_key="HostsPage",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_COMMON,
        breadcrumb_parent=None,
        sidebar_group="system",
    ),
    PageName.BLOCKCHECK: PageRouteSpec(
        page_name=PageName.BLOCKCHECK,
        module_name="blockcheck.ui.page",
        class_name="BlockcheckPage",
        route_key="BlockcheckPage",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_COMMON,
        breadcrumb_parent=None,
        sidebar_group="diagnostics",
    ),
    PageName.WINWS_LOG_ANALYZER: PageRouteSpec(
        page_name=PageName.WINWS_LOG_ANALYZER,
        module_name="winws_log_analyzer.ui.page",
        class_name="WinwsLogAnalyzerPage",
        route_key="WinwsLogAnalyzerPage",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_WINWS2_MODE,
        breadcrumb_parent=None,
        sidebar_group="diagnostics",
    ),
    PageName.LOGS: PageRouteSpec(
        page_name=PageName.LOGS,
        module_name="log.ui.page",
        class_name="LogsPage",
        route_key="LogsPage",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_COMMON,
        breadcrumb_parent=None,
        sidebar_group="appearance",
    ),
    PageName.SERVERS: PageRouteSpec(
        page_name=PageName.SERVERS,
        module_name="updater.ui.page",
        class_name="ServersPage",
        route_key="ServersPage",
        is_top_level=False,
        is_hidden=True,
        launch_modes=_COMMON,
        breadcrumb_parent=PageName.ABOUT,
        sidebar_group=None,
    ),
    # «О программе» убрана из интерфейса: версия видна в заголовке окна,
    # а ссылки на ресурсы автора исходного проекта оттуда вычищены.
    # Ключ оставлен — на него ссылаются page_registry, search_index и
    # page_deps, удаление уронило бы get_page_spec с KeyError.
    PageName.ABOUT: PageRouteSpec(
        page_name=PageName.ABOUT,
        module_name="ui.pages.about_page",
        class_name="AboutPage",
        route_key="AboutPage",
        is_top_level=False,
        is_hidden=True,
        launch_modes=_COMMON,
        breadcrumb_parent=None,
        sidebar_group="appearance",
    ),
    PageName.SUPPORT: PageRouteSpec(
        page_name=PageName.SUPPORT,
        module_name="ui.pages.support_page",
        class_name="SupportPage",
        route_key="SupportPage",
        is_top_level=False,
        is_hidden=True,
        launch_modes=_COMMON,
        breadcrumb_parent=PageName.ABOUT,
        sidebar_group=None,
    ),
    PageName.TELEGRAM_PROXY: PageRouteSpec(
        page_name=PageName.TELEGRAM_PROXY,
        module_name="telegram_proxy.ui.page",
        class_name="TelegramProxyPage",
        route_key="TelegramProxyPage",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_COMMON,
        breadcrumb_parent=None,
        sidebar_group="system",
    ),
    # Страница не входит в SIMPLE_MODE_PAGES, поэтому видна только при
    # включённых расширенных настройках.
    PageName.CONFIGS: PageRouteSpec(
        page_name=PageName.CONFIGS,
        module_name="configsets.ui.page",
        class_name="ConfigsPage",
        route_key="ConfigsPage",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_COMMON,
        breadcrumb_parent=None,
        sidebar_group="appearance",
    ),
    PageName.VPN: PageRouteSpec(
        page_name=PageName.VPN,
        module_name="vpn.ui.page",
        class_name="VpnPage",
        route_key="VpnPage",
        is_top_level=True,
        is_hidden=False,
        launch_modes=_COMMON,
        breadcrumb_parent=None,
        sidebar_group="system",
    ),
}

PAGE_CLEANUP_ORDER: tuple[PageName, ...] = (
    PageName.ZAPRET2_MODE_CONTROL,
    PageName.ZAPRET2_PRESET_SETUP,
    PageName.ZAPRET2_PROFILE_SETUP,
    PageName.ZAPRET2_PROFILE_ORDER,
    PageName.ZAPRET2_PRESET_RAW_EDITOR,
    PageName.ZAPRET2_USER_PRESETS,
    PageName.LOGS,
    PageName.SERVERS,
    PageName.ABOUT,
    PageName.BLOCKCHECK,
    PageName.WINWS_LOG_ANALYZER,
    PageName.HOSTS,
    PageName.NETWORK,
    PageName.TELEGRAM_PROXY,
    PageName.VPN,
    PageName.CONFIGS,
)

_PAGE_CLEANUP_PRIORITY_OVERRIDES: dict[PageName, int] = {
    page_name: index
    for index, page_name in enumerate(PAGE_CLEANUP_ORDER)
}

_DEFAULT_CLEANUP_PRIORITY_BASE = 10_000

PAGE_ROUTE_SPECS = {
    page_name: replace(
        spec,
        cleanup_priority=_PAGE_CLEANUP_PRIORITY_OVERRIDES.get(
            page_name,
            _DEFAULT_CLEANUP_PRIORITY_BASE + index,
        ),
        # Считается здесь, а не проставляется руками в каждой из 24 записей:
        # источник правды один — SIMPLE_MODE_PAGES.
        is_advanced=page_name not in SIMPLE_MODE_PAGES,
    )
    for index, (page_name, spec) in enumerate(PAGE_ROUTE_SPECS.items())
}


SIDEBAR_GROUP_ORDER: tuple[str, ...] = ("root", "settings", "system", "diagnostics", "appearance")

INNER_PAGE_NAMES: frozenset[PageName] = frozenset(
    {
        PageName.ZAPRET2_PROFILE_SETUP,
        PageName.ZAPRET2_PROFILE_ORDER,
        PageName.ZAPRET2_PRESET_RAW_EDITOR,
    }
)

MODE_ENTRY_PAGES: dict[str, PageName] = {
    ZAPRET2_MODE: PageName.ZAPRET2_MODE_CONTROL,
}


def get_page_spec(page_name: PageName) -> PageRouteSpec:
    return PAGE_ROUTE_SPECS[page_name]


def iter_page_specs() -> Iterable[PageRouteSpec]:
    return PAGE_ROUTE_SPECS.values()


def get_page_cleanup_priority(page_name: PageName) -> int:
    spec = PAGE_ROUTE_SPECS.get(page_name)
    if spec is None:
        return _DEFAULT_CLEANUP_PRIORITY_BASE * 2
    return int(spec.cleanup_priority)


def iter_page_names_for_cleanup(page_names: Iterable[PageName]) -> tuple[PageName, ...]:
    indexed_page_names = list(enumerate(page_names))
    indexed_page_names.sort(
        key=lambda item: (get_page_cleanup_priority(item[1]), item[0])
    )
    return tuple(page_name for _index, page_name in indexed_page_names)


def normalize_launch_method_for_ui(method: str | None) -> str:
    normalized = (method or "").strip().lower()
    return normalized or DEFAULT_LAUNCH_METHOD


def _matches_method(spec: PageRouteSpec, method: str | None) -> bool:
    if not spec.launch_modes:
        return True
    normalized_method = normalize_launch_method_for_ui(method)
    return normalized_method in spec.launch_modes


def is_advanced_mode_enabled() -> bool:
    """Читает сохранённый режим интерфейса.

    Вынесено в функцию, чтобы вызывающие могли не тащить settings.store
    и чтобы отказ чтения настроек не ронял навигацию — в этом случае
    показываем простой режим.
    """
    try:
        from settings.store import get_advanced_mode

        return bool(get_advanced_mode())
    except Exception:
        return False


def _is_visible_in_ui_mode(
    spec: PageRouteSpec,
    advanced: bool | None,
    method: str | None = None,
) -> bool:
    if advanced is None:
        advanced = is_advanced_mode_enabled()
    if advanced:
        return True
    if not spec.is_advanced:
        return True
    # Главная страница текущего режима видна всегда. Без этого простой
    # интерфейс на запуске в v1 или Оркестре остался бы вообще без главной:
    # в SIMPLE_MODE_PAGES лежит только точка входа v2.
    entry_page = MODE_ENTRY_PAGES.get(normalize_launch_method_for_ui(method))
    return spec.page_name is entry_page


def _is_sidebar_visible_in_method(
    spec: PageRouteSpec,
    method: str | None,
    *,
    advanced: bool | None = None,
) -> bool:
    normalized_method = normalize_launch_method_for_ui(method)

    return _matches_method(spec, normalized_method) and _is_visible_in_ui_mode(
        spec, advanced, normalized_method
    )


def is_page_allowed_for_method(page_name: PageName, method: str | None) -> bool:
    spec = PAGE_ROUTE_SPECS.get(page_name)
    if spec is None:
        return False
    return _matches_method(spec, method)


def is_page_mode_open_allowed(page_name: PageName) -> bool:
    return page_name not in INNER_PAGE_NAMES


def is_page_search_visible(page_name: PageName) -> bool:
    return page_name not in INNER_PAGE_NAMES


def get_page_route_key(page_name: PageName) -> str:
    return str(get_page_spec(page_name).route_key)


def get_mode_entry_page(method: str | None) -> PageName:
    normalized = normalize_launch_method_for_ui(method)
    return MODE_ENTRY_PAGES.get(normalized, MODE_ENTRY_PAGES[DEFAULT_LAUNCH_METHOD])


def get_eager_page_names_for_method(method: str | None) -> tuple[PageName, ...]:
    return (get_mode_entry_page(method),)


def get_sidebar_pages_for_method(
    method: str | None,
    *,
    sidebar_group: str | None = None,
    advanced: bool | None = None,
) -> tuple[PageName, ...]:
    pages: list[PageName] = []
    for spec in iter_page_specs():
        if not spec.is_top_level or spec.is_hidden:
            continue
        if sidebar_group is not None and spec.sidebar_group != sidebar_group:
            continue
        if not _is_sidebar_visible_in_method(spec, method, advanced=advanced):
            continue
        pages.append(spec.page_name)
    return tuple(pages)


def get_sidebar_layout_pages_for_method(
    method: str | None,
    *,
    sidebar_group: str | None = None,
    advanced: bool | None = None,
) -> tuple[PageName, ...]:
    visible_pages: list[PageName] = []
    hidden_mode_pages: list[PageName] = []
    for spec in iter_page_specs():
        if not spec.is_top_level or spec.is_hidden:
            continue
        if sidebar_group is not None and spec.sidebar_group != sidebar_group:
            continue

        if _is_sidebar_visible_in_method(spec, method, advanced=advanced):
            visible_pages.append(spec.page_name)
        else:
            hidden_mode_pages.append(spec.page_name)

    return tuple(visible_pages + hidden_mode_pages)


def get_hidden_pages_for_method(method: str | None) -> tuple[PageName, ...]:
    pages: list[PageName] = []
    for spec in iter_page_specs():
        if not spec.is_hidden:
            continue
        if not _matches_method(spec, method):
            continue
        pages.append(spec.page_name)
    return tuple(pages)


def get_breadcrumb_chain(page_name: PageName) -> tuple[PageName, ...]:
    chain: list[PageName] = []
    seen: set[PageName] = set()
    current: PageName | None = page_name
    while current is not None and current not in seen:
        seen.add(current)
        chain.append(current)
        current = get_page_spec(current).breadcrumb_parent
    chain.reverse()
    return tuple(chain)


def get_mode_gated_nav_pages() -> frozenset[PageName]:
    return frozenset(
        spec.page_name
        for spec in iter_page_specs()
        if spec.is_top_level and bool(spec.launch_modes)
    )


def get_nav_visibility(method: str | None, *, advanced: bool | None = None) -> dict[PageName, bool]:
    visibility: dict[PageName, bool] = {}
    if advanced is None:
        advanced = is_advanced_mode_enabled()
    for spec in iter_page_specs():
        if not spec.is_top_level or spec.is_hidden:
            continue
        visibility[spec.page_name] = _is_sidebar_visible_in_method(spec, method, advanced=advanced)
    return visibility


def get_sidebar_search_pages_for_method(
    method: str | None,
    all_pages: set[PageName],
    *,
    advanced: bool | None = None,
) -> set[PageName]:
    allowed_pages: set[PageName] = set()
    if advanced is None:
        advanced = is_advanced_mode_enabled()
    for page_name in all_pages:
        spec = PAGE_ROUTE_SPECS.get(page_name)
        if spec is None:
            continue
        # Поиск не должен показывать расширенные страницы в простом режиме,
        # иначе скрытый интерфейс всё равно протекает наружу.
        if not _is_visible_in_ui_mode(spec, advanced, method):
            continue
        if _matches_method(spec, method) and is_page_search_visible(page_name):
            allowed_pages.add(page_name)
    return allowed_pages


__all__ = [
    "MODE_ENTRY_PAGES",
    "PAGE_CLEANUP_ORDER",
    "PAGE_ROUTE_SPECS",
    "SIDEBAR_GROUP_ORDER",
    "SIMPLE_MODE_PAGES",
    "PageRouteSpec",
    "is_advanced_mode_enabled",
    "get_breadcrumb_chain",
    "get_page_cleanup_priority",
    "get_eager_page_names_for_method",
    "get_hidden_pages_for_method",
    "get_mode_entry_page",
    "get_mode_gated_nav_pages",
    "get_nav_visibility",
    "get_page_route_key",
    "get_page_spec",
    "is_page_allowed_for_method",
    "is_page_mode_open_allowed",
    "is_page_search_visible",
    "iter_page_names_for_cleanup",
    "get_sidebar_layout_pages_for_method",
    "get_sidebar_pages_for_method",
    "get_sidebar_search_pages_for_method",
    "iter_page_specs",
    "normalize_launch_method_for_ui",
]
