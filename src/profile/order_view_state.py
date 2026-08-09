from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ProfileOrderListViewState:
    items: tuple[Any, ...]
    profile_items: dict[str, Any]


def build_profile_order_list_view_state(
    items: tuple[Any, ...],
    *,
    preserve_order: bool = False,
) -> ProfileOrderListViewState:
    rows = [item for item in tuple(items or ()) if bool(getattr(item, "in_preset", False))]
    if not preserve_order:
        rows.sort(key=lambda item: int(getattr(item, "profile_index", 0) or 0))
    next_items = tuple(rows)
    return ProfileOrderListViewState(
        items=next_items,
        profile_items={
            str(getattr(item, "key", "") or ""): item
            for item in next_items
            if str(getattr(item, "key", "") or "")
        },
    )


def move_profile_order_items(
    items: tuple[Any, ...],
    source_profile_key: str,
    action: str,
    destination_profile_key: str = "",
) -> tuple[Any, ...] | None:
    source_key = str(source_profile_key or "").strip()
    move_action = str(action or "").strip()
    destination_key = str(destination_profile_key or "").strip()
    if not source_key:
        return None

    rows = [item for item in tuple(items or ()) if bool(getattr(item, "in_preset", False))]
    source_index = next(
        (index for index, item in enumerate(rows) if str(getattr(item, "key", "") or "") == source_key),
        -1,
    )
    if source_index < 0:
        return None
    source = rows.pop(source_index)

    if move_action == "end":
        insert_index = len(rows)
    else:
        destination_index = next(
            (index for index, item in enumerate(rows) if str(getattr(item, "key", "") or "") == destination_key),
            -1,
        )
        if destination_index < 0:
            return None
        insert_index = destination_index + (1 if move_action == "after" else 0)
    rows.insert(insert_index, source)
    return tuple(rows)


__all__ = [
    "ProfileOrderListViewState",
    "build_profile_order_list_view_state",
    "move_profile_order_items",
]
