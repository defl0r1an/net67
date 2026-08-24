from __future__ import annotations

from dataclasses import dataclass

from ui.navigation.schema import (
    SIDEBAR_GROUP_ORDER,
    get_sidebar_layout_pages_for_method,
    normalize_launch_method_for_ui,
)
from app.page_names import PageName


SIDEBAR_GROUP_HEADER_KEYS: dict[str, str] = {
    "settings": "nav.header.settings",
    "system": "nav.header.system",
    "diagnostics": "nav.header.diagnostics",
    "appearance": "nav.header.appearance",
}


@dataclass(frozen=True, slots=True)
class SidebarGroupPlan:
    group_name: str
    header_key: str | None
    page_names: tuple[PageName, ...]


@dataclass(frozen=True, slots=True)
class SidebarLayoutEntry:
    kind: str
    group_name: str
    page_name: PageName | None = None
    header_key: str | None = None


def build_sidebar_group_plans(
    method: str | None,
    *,
    advanced: bool | None = None,
) -> tuple[SidebarGroupPlan, ...]:
    normalized_method = normalize_launch_method_for_ui(method)
    plans: list[SidebarGroupPlan] = []
    for group_name in SIDEBAR_GROUP_ORDER:
        plans.append(
            SidebarGroupPlan(
                group_name=group_name,
                header_key=SIDEBAR_GROUP_HEADER_KEYS.get(group_name),
                page_names=tuple(
                    get_sidebar_layout_pages_for_method(
                        normalized_method,
                        sidebar_group=group_name,
                        advanced=advanced,
                    )
                ),
            )
        )
    return tuple(plans)


def iter_sidebar_layout_entries(
    method: str | None,
    *,
    advanced: bool | None = None,
) -> tuple[SidebarLayoutEntry, ...]:
    entries: list[SidebarLayoutEntry] = []
    # Layout намеренно содержит ВСЕ страницы группы, включая невидимые в
    # текущем режиме: виджеты создаются один раз, а показ/скрытие делает
    # apply_nav_visibility_filter(). Иначе переключение простой/расширенный
    # потребовало бы полной пересборки сайдбара.
    for group_plan in build_sidebar_group_plans(method, advanced=advanced):
        if group_plan.header_key:
            entries.append(
                SidebarLayoutEntry(
                    kind="header",
                    group_name=group_plan.group_name,
                    header_key=group_plan.header_key,
                )
            )
        for page_name in group_plan.page_names:
            entries.append(
                SidebarLayoutEntry(
                    kind="page",
                    group_name=group_plan.group_name,
                    page_name=page_name,
                )
            )
    return tuple(entries)


def iter_sidebar_entries_after_page(
    method: str | None,
    page_name: PageName,
    *,
    advanced: bool | None = None,
) -> tuple[SidebarLayoutEntry, ...]:
    entries = iter_sidebar_layout_entries(method, advanced=advanced)
    for index, entry in enumerate(entries):
        if entry.kind == "page" and entry.page_name == page_name:
            return tuple(entries[index + 1 :])
    return ()


__all__ = [
    "SIDEBAR_GROUP_HEADER_KEYS",
    "SidebarGroupPlan",
    "SidebarLayoutEntry",
    "build_sidebar_group_plans",
    "iter_sidebar_entries_after_page",
    "iter_sidebar_layout_entries",
]
