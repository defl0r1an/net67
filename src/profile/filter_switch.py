from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Sequence

from .editable_settings import EditableProfileSettings, normalize_filter_value, with_editable_profile
from .list_file_editor import profile_list_file_exists


@dataclass(frozen=True, slots=True)
class FilterKindSwitchCandidate:
    filter_kind: str
    filter_value: str
    reason: str = ""


@dataclass(frozen=True, slots=True)
class FilterKindSwitchResolution:
    allowed: bool
    filter_kind: str
    filter_value: str
    reason: str = ""


def build_filter_kind_candidate(settings: EditableProfileSettings, filter_kind: str) -> FilterKindSwitchCandidate:
    current_kind = str(settings.filter_kind or "hostlist").strip().lower()
    target_kind = str(filter_kind or "").strip().lower()
    if not settings.filter_editable:
        return FilterKindSwitchCandidate(target_kind, "", "not_editable")
    if current_kind not in {"hostlist", "ipset"} or target_kind not in {"hostlist", "ipset"}:
        return FilterKindSwitchCandidate(target_kind, "", "unsupported_kind")

    target_value = _filter_value_for_kind_switch(settings, target_kind)
    if not target_value:
        return FilterKindSwitchCandidate(target_kind, "", "missing_pair")
    return FilterKindSwitchCandidate(target_kind, target_value)


def resolve_filter_kind_switch(
    settings: EditableProfileSettings,
    filter_kind: str,
    app_paths: Any,
) -> FilterKindSwitchResolution:
    current_kind = str(settings.filter_kind or "hostlist").strip().lower()
    candidate = build_filter_kind_candidate(settings, filter_kind)
    if candidate.reason:
        return FilterKindSwitchResolution(False, candidate.filter_kind, candidate.filter_value, candidate.reason)

    if candidate.filter_kind != current_kind and not _filter_files_available(app_paths, candidate.filter_value):
        return FilterKindSwitchResolution(False, candidate.filter_kind, candidate.filter_value, "missing_file")
    return FilterKindSwitchResolution(True, candidate.filter_kind, candidate.filter_value)


def _filter_value_for_kind_switch(settings: EditableProfileSettings, filter_kind: str) -> str:
    current_kind = str(settings.filter_kind or "hostlist").strip().lower()
    target_kind = str(filter_kind or "").strip().lower()
    current_value = str(settings.filter_value or "").strip()
    if target_kind == current_kind:
        return normalize_filter_value(current_value, target_kind, filter_role=settings.filter_role)
    if str(settings.filter_role or "").strip().lower() == "exclude":
        # Exclude-фильтры не переключаются между типами: у пары catch-all
        # профилей («Все сайты (хостлисты)» с netrogat.txt и «Все сайты
        # (айпи)» со служебными ipset-*) разные роли в пресете, и связка
        # netrogat ↔ ipset-ru/dns/exclude только путала (убрана по решению
        # пользователя 2026-07-06). Пустая пара → switch недоступен, комбо
        # типа на таких профилях скрывается.
        return ""
    if "," in current_value:
        return ""
    return _paired_primary_filter_value(current_value, current_kind, target_kind)


def _paired_primary_filter_value(value: str, current_kind: str, target_kind: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    path = PureWindowsPath(raw)
    name = path.name
    if not name:
        return raw

    lower_name = name.lower()
    if target_kind == "ipset" and lower_name == "other.txt":
        return _replace_filter_path_name(raw, path, "ipset-all.txt")
    if target_kind == "hostlist" and lower_name == "ipset-all.txt":
        return _replace_filter_path_name(raw, path, "other.txt")

    suffix = "".join(path.suffixes)
    stem = name[: -len(suffix)] if suffix else name
    normalized_stem = stem.lower()
    if current_kind == "hostlist" and target_kind == "ipset":
        if normalized_stem.startswith(("ipset-", "ipset_")):
            return raw
        return _replace_filter_path_name(raw, path, f"ipset-{stem}{suffix}")
    if current_kind == "ipset" and target_kind == "hostlist":
        if normalized_stem.startswith(("ipset-", "ipset_")):
            return _replace_filter_path_name(raw, path, f"{stem[6:]}{suffix}")
        return ""
    return normalize_filter_value(raw, target_kind)


def _replace_filter_path_name(raw: str, path: PureWindowsPath, new_name: str) -> str:
    parent = str(path.parent)
    if not parent or parent == ".":
        return new_name
    separator = "\\" if "\\" in raw else "/"
    return f"{parent}{separator}{new_name}"


def _filter_files_available(app_paths: Any, filter_value: str) -> bool:
    lists_root = Path(getattr(app_paths, "user_root", "")) / "lists"
    if not lists_root.exists():
        return False
    for value in _filter_reference_values(filter_value):
        if not _looks_like_list_file_reference(value):
            continue
        if not profile_list_file_exists(lists_root, value):
            return False
    return True


def _filter_reference_values(filter_value: str) -> tuple[str, ...]:
    values: list[str] = []
    for part in str(filter_value or "").split(","):
        value = part.strip().strip('"').strip("'").lstrip("@")
        if value:
            values.append(value)
    return tuple(values)


def _looks_like_list_file_reference(value: str) -> bool:
    normalized = str(value or "").strip().replace("\\", "/")
    return normalized.startswith("lists/") or "/" in normalized or normalized.lower().endswith((".txt", ".lst", ".list"))


def filter_kind_switch_creates_preset_duplicate(
    profile: Any,
    preset_profiles: Sequence[Any],
    settings: EditableProfileSettings,
    resolution: FilterKindSwitchResolution,
) -> bool:
    """Проверяет, не превратит ли переключение типа фильтра профиль в дубликат.

    Пресеты несут ПАРЫ catch-all профилей («Все сайты (хостлисты)» с
    hostlist-exclude и «Все сайты (айпи)» с ipset-exclude) — это разные роли:
    первый ловит соединения с известным hostname, второй — остальные по IP.
    Переключение типа на одном из них дало бы второй профиль с той же
    match-сигнатурой: winws2 отдаст трафик первому по порядку, а пара
    развалится. Такое переключение запрещаем; для пресетов с единственным
    catch-all профилем переключение остаётся доступным.
    """
    try:
        switched = with_editable_profile(
            profile,
            EditableProfileSettings(
                filter_kind=resolution.filter_kind,
                filter_value=resolution.filter_value,
                filter_role=settings.filter_role,
                in_range=settings.in_range,
                out_range=settings.out_range,
            ),
        )
        target_signature = str(switched.match_signature or "")
    except Exception:
        return False
    if not target_signature:
        return False
    profile_persistent_key = str(getattr(profile, "persistent_key", "") or "")
    for other in preset_profiles or ():
        if other is profile:
            continue
        if profile_persistent_key and str(getattr(other, "persistent_key", "") or "") == profile_persistent_key:
            continue
        if str(getattr(other, "match_signature", "") or "") == target_signature:
            return True
    return False


def filter_kinds_without_preset_duplicates(
    settings: EditableProfileSettings,
    profile: Any,
    preset_profiles: Sequence[Any],
    kinds: Sequence[str],
    app_paths: Any,
) -> tuple[str, ...]:
    """Убирает из доступных типов фильтра те, что создали бы дубликат в пресете."""
    current_kind = str(settings.filter_kind or "hostlist").strip().lower()
    result: list[str] = []
    for kind in kinds or ():
        normalized = str(kind or "").strip().lower()
        if normalized == current_kind:
            result.append(normalized)
            continue
        resolution = resolve_filter_kind_switch(settings, normalized, app_paths)
        if not resolution.allowed:
            continue
        if filter_kind_switch_creates_preset_duplicate(profile, preset_profiles, settings, resolution):
            continue
        result.append(normalized)
    return tuple(result) or (current_kind,)
