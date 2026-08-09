from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AboutTabSwitchPlan:
    current_index: int
    route_key: str
    init_help: bool
    init_kvn: bool


#: Вкладка «kvn» удалена вместе с разделом о стороннем проекте автора.
#: build_tab_switch_plan зажимает индекс по длине кортежа, поэтому старый
#: сохранённый индекс 2 безопасно схлопнется в «help».
TAB_KEYS = ("about", "help")

def build_tab_switch_plan(
    *,
    index: int,
    help_initialized: bool,
    kvn_initialized: bool,
) -> AboutTabSwitchPlan:
    safe_index = max(0, min(int(index), len(TAB_KEYS) - 1))
    route_key = TAB_KEYS[safe_index]
    return AboutTabSwitchPlan(
        current_index=safe_index,
        route_key=route_key,
        init_help=(safe_index == 1 and not help_initialized),
        # Вкладки KVN больше нет, инициализировать нечего.
        init_kvn=False,
    )

def resolve_tab_index(key: str) -> int | None:
    normalized = str(key or "").strip().lower()
    if normalized == "support":
        return 0
    if normalized in TAB_KEYS:
        return TAB_KEYS.index(normalized)
    return None

