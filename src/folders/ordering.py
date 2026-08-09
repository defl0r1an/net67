from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .defaults import COMMON_FOLDER_KEY, PINNED_FOLDER_KEY
from .store import normalize_folder_state


@dataclass(frozen=True)
class FolderOrderView:
    """Канонический отображаемый порядок папок и элементов.

    Единственный источник истины: и рендеринг, и планирование перемещений
    обязаны исходить из одного и того же представления.
    """

    folder_keys: tuple[str, ...]
    folder_names: dict[str, str] = field(default_factory=dict)
    collapsed: dict[str, bool] = field(default_factory=dict)
    items_by_folder: dict[str, tuple[str, ...]] = field(default_factory=dict)
    folder_by_item: dict[str, str] = field(default_factory=dict)
    position_by_item: dict[str, int] = field(default_factory=dict)


def resolve_folder_order(state: dict[str, Any], live_items: list[dict[str, Any]]) -> FolderOrderView:
    """Строит канонический порядок: папки — по сохранённому order (имя/ключ как
    tie-break), элементы — сохранённый order первым, затем доменный auto_rank.

    live_items: [{key, name, folder_key?, rating?, manual_tie?, auto_rank?}, ...]
    Ранги (`manual_tie`, `auto_rank`) задаёт домен; если их нет, используется
    rating-семантика страницы пресетов (см. `_entry_sort_key`).
    """
    folders = _folders_of(state)
    item_meta = _items_of(state)

    grouped: dict[str, list[tuple[tuple[Any, ...], str]]] = {key: [] for key in folders}
    folder_by_item: dict[str, str] = {}
    for live_item in live_items or []:
        key = str(live_item.get("key") or "").strip()
        if not key:
            continue
        meta = item_meta.get(key)
        meta = meta if isinstance(meta, dict) else {}
        folder_key = _resolve_item_folder(meta, live_item, folders)
        order = _as_nullable_int(meta.get("order"))
        grouped.setdefault(folder_key, []).append((_entry_sort_key(order, meta, live_item), key))
        folder_by_item[key] = folder_key

    items_by_folder: dict[str, tuple[str, ...]] = {}
    position_by_item: dict[str, int] = {}
    for folder_key, entries in grouped.items():
        ordered = tuple(key for _sort_key, key in sorted(entries))
        items_by_folder[folder_key] = ordered
        for position, key in enumerate(ordered):
            position_by_item[key] = position

    return FolderOrderView(
        folder_keys=tuple(key for key, _folder in _sort_folders(folders) if key != PINNED_FOLDER_KEY),
        folder_names={key: str(folder.get("name") or key) for key, folder in folders.items()},
        collapsed={key: bool(folder.get("collapsed", False)) for key, folder in folders.items()},
        items_by_folder=items_by_folder,
        folder_by_item=folder_by_item,
        position_by_item=position_by_item,
    )


def plan_view_move(
    view: FolderOrderView,
    *,
    action: str,
    source_key: str,
    destination_key: str = "",
    destination_folder_key: str = "",
) -> tuple[str, tuple[str, ...]] | None:
    """Чистая «математика» перемещения над каноническим представлением.

    Возвращает (целевая папка, новая последовательность её элементов) либо
    None, если перемещение невозможно или не меняет отображаемый порядок.
    Единственная реализация move-семантики: и оптимистичный UI, и персист
    обязаны вызывать её.
    """
    source = str(source_key or "").strip()
    destination = str(destination_key or "").strip()
    kind = str(action or "").strip()
    if not source or source not in view.folder_by_item:
        return None

    if kind in {"before", "after"}:
        if not destination or destination == source or destination not in view.folder_by_item:
            return None
        target_folder = str(destination_folder_key or "").strip() or view.folder_by_item[destination]
    elif kind == "end":
        target_folder = str(destination_folder_key or "").strip() or view.folder_by_item[source]
    elif kind == "folder":
        target_folder = str(destination_folder_key or "").strip()
    else:
        return None
    if not target_folder:
        return None

    sequence = [key for key in view.items_by_folder.get(target_folder, ()) if key != source]
    if kind in {"before", "after"}:
        if destination not in sequence:
            # UI авторитетен: если цель видна в явно указанной папке, а
            # состояние ещё не знает об этом — цель тоже переезжает туда.
            if not str(destination_folder_key or "").strip():
                return None
            sequence.append(destination)
        insert_index = sequence.index(destination) + (1 if kind == "after" else 0)
        sequence.insert(insert_index, source)
    else:
        sequence.append(source)

    if view.folder_by_item[source] == target_folder and tuple(sequence) == view.items_by_folder.get(target_folder, ()):
        return None
    return target_folder, tuple(sequence)


def plan_item_move(
    state: dict[str, Any],
    live_items: list[dict[str, Any]],
    *,
    action: str,
    source_key: str,
    destination_key: str = "",
    destination_folder_key: str = "",
) -> dict[str, Any] | None:
    """Чистый планировщик перемещения. База — отображаемый порядок
    (`resolve_folder_order`), поэтому сохранённый результат всегда совпадает
    с тем, что видит пользователь. Возвращает НОВОЕ состояние или None (no-op).

    Гарантии: изменяется только целевая папка (перенумерация 0..N по
    отображаемой базе) и meta источника; meta других папок и их folder_key
    не затрагиваются.
    """
    view = resolve_folder_order(state, live_items)
    planned = plan_view_move(
        view,
        action=action,
        source_key=source_key,
        destination_key=destination_key,
        destination_folder_key=destination_folder_key,
    )
    if planned is None:
        return None
    target_folder, sequence = planned
    if target_folder not in _folders_of(state):
        return None
    source = str(source_key or "").strip()

    next_state = deepcopy(state)
    items = next_state.setdefault("items", {})
    live_by_key = {str(item.get("key") or "").strip(): item for item in live_items or []}
    for index, key in enumerate(sequence):
        meta = items.get(key)
        if not isinstance(meta, dict):
            # Элемент отображался в целевой папке по классификации — материализуем
            # именно её; folder_key элементов других папок не переписывается.
            meta = _new_item_meta(target_folder, live_by_key.get(key))
            items[key] = meta
        if view.folder_by_item.get(key) != target_folder:
            # Папка меняется только у переезжающих элементов (источник и,
            # при явном destination_folder_key, цель).
            meta["folder_key"] = target_folder
        meta["order"] = index
    return next_state


def _new_item_meta(folder_key: str, live_item: dict[str, Any] | None) -> dict[str, Any]:
    meta: dict[str, Any] = {"folder_key": folder_key, "order": None, "rating": 0}
    if isinstance(live_item, dict):
        meta["rating"] = _item_rating({}, live_item)
        if bool(live_item.get("pinned", False)):
            meta["pinned"] = True
    return meta


def _resolve_item_folder(meta: dict[str, Any], live_item: dict[str, Any], folders: dict[str, Any]) -> str:
    default_folder = str(live_item.get("folder_key") or COMMON_FOLDER_KEY).strip() or COMMON_FOLDER_KEY
    folder_key = str(meta.get("folder_key") or default_folder).strip() or COMMON_FOLDER_KEY
    if folder_key not in folders:
        folder_key = COMMON_FOLDER_KEY
    return folder_key


def _entry_sort_key(order: int | None, meta: dict[str, Any], live_item: dict[str, Any]) -> tuple[Any, ...]:
    name = str(live_item.get("name") or live_item.get("key") or "").lower()
    key = str(live_item.get("key") or "")
    if order is not None:
        manual_tie = live_item.get("manual_tie")
        if manual_tie is None:
            manual_tie = (-_item_rating(meta, live_item),)
        return (0, (int(order), *tuple(manual_tie)), name, key)
    auto_rank = live_item.get("auto_rank")
    if auto_rank is None:
        auto_rank = (0, -_item_rating(meta, live_item))
    return (1, tuple(auto_rank), name, key)


def _folders_of(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    folders = state.get("folders") if isinstance(state, dict) else None
    if not isinstance(folders, dict):
        return {}
    return {str(key): folder for key, folder in folders.items() if isinstance(folder, dict)}


def _items_of(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = state.get("items") if isinstance(state, dict) else None
    if not isinstance(items, dict):
        return {}
    return {str(key): meta for key, meta in items.items() if isinstance(meta, dict)}


def _as_nullable_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def build_folder_rows(
    state: dict[str, Any],
    *,
    live_items: list[dict[str, Any]],
    include_pinned_folder: bool = False,
    query: str = "",
) -> list[dict[str, Any]]:
    normalized = normalize_folder_state(state, state)
    folders = normalized["folders"]
    item_meta = normalized["items"]
    normalized_query = str(query or "").strip().lower()

    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in folders}
    pinned_rows: list[dict[str, Any]] = []

    for live_item in live_items:
        key = str(live_item.get("key") or "").strip()
        name = str(live_item.get("name") or key).strip() or key
        if not key:
            continue
        if normalized_query and normalized_query not in name.lower() and normalized_query not in key.lower():
            continue
        meta = dict(item_meta.get(key) or {})
        default_folder_key = str(live_item.get("folder_key") or COMMON_FOLDER_KEY).strip() or COMMON_FOLDER_KEY
        folder_key = str(meta.get("folder_key") or default_folder_key).strip() or COMMON_FOLDER_KEY
        if folder_key not in folders:
            folder_key = COMMON_FOLDER_KEY
        row = {
            "kind": "item",
            "key": key,
            "name": name,
            "folder_key": folder_key,
            "order": meta.get("order"),
            "rating": _item_rating(meta, live_item),
            "pinned": bool(meta.get("pinned", False) or live_item.get("pinned", False)),
            "payload": live_item,
        }
        if include_pinned_folder and row["pinned"]:
            pinned_rows.append(row)
            continue
        grouped.setdefault(folder_key, []).append(row)

    rows: list[dict[str, Any]] = []
    if pinned_rows:
        pinned_meta = folders.get(PINNED_FOLDER_KEY, {})
        pinned_collapsed = bool(pinned_meta.get("collapsed", False)) if isinstance(pinned_meta, dict) else False
        rows.append(
            {
                "kind": "folder",
                "key": PINNED_FOLDER_KEY,
                "name": "Закрепленные",
                "collapsed": pinned_collapsed,
                "system": True,
                "service": True,
                "count": len(pinned_rows),
            }
        )
        if not pinned_collapsed or normalized_query:
            rows.extend(_sort_items(pinned_rows))

    for folder_key, folder in _sort_folders(folders):
        if folder_key == PINNED_FOLDER_KEY:
            continue
        items = _sort_items(grouped.get(folder_key, []))
        if normalized_query and not items:
            continue
        rows.append(
            {
                "kind": "folder",
                "key": folder_key,
                "name": str(folder.get("name") or folder_key),
                "collapsed": bool(folder.get("collapsed", False)),
                "system": bool(folder.get("system", False)),
                "service": False,
                "count": len(items),
            }
        )
        if not bool(folder.get("collapsed", False)) or normalized_query:
            rows.extend(items)

    return rows


def _sort_folders(folders: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return sorted(
        folders.items(),
        key=lambda pair: (
            int(pair[1].get("order", 0) or 0),
            str(pair[1].get("name") or pair[0]).lower(),
            pair[0],
        ),
    )


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: _entry_sort_key(_as_nullable_int(item.get("order")), item, item),
    )


def _item_rating(meta: dict[str, Any], live_item: dict[str, Any]) -> int:
    for source in (meta, live_item):
        try:
            return max(0, min(10, int(source.get("rating", 0) or 0)))
        except Exception:
            continue
    return 0


__all__ = ["FolderOrderView", "build_folder_rows", "plan_item_move", "plan_view_move", "resolve_folder_order"]
