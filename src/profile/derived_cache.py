"""Контентно-производные данные профиля и их кэш.

Ядро (`ProfileDerivedCore`) считается только из текста профиля и каталогов стратегий,
поэтому ключуется по (engine, подпись каталогов, сырой текст профиля) и переживает
смену пресета/ревизии: неизменённый профиль не пересчитывается. Контекстные поля
(порядок, папка, enabled, rating) сюда не входят — их накладывает сборка списка.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any

from settings.mode import ENGINE_WINWS2

from .editable_settings import EditableProfileSettings, read_editable_profile_settings
from .filter_switch import resolve_filter_kind_switch
from .list_interpreter import build_profile_list_sources
from .match_filters import (
    ports_label_from_match_lines,
    protocol_label_from_match_lines,
    strategy_catalog_from_match_lines,
)
from .models import Preset, Profile
from .setup_match_text import build_profile_setup_match_tab_text
from .state import ProfileStrategyBranch
from .strategy_catalog import StrategyEntry


PROFILE_DERIVED_CACHE_LIMIT = 512


@dataclass(slots=True, frozen=True)
class ProfileDerivedCore:
    strategy_entries: dict[str, StrategyEntry]
    strategy_branches: tuple[ProfileStrategyBranch, ...]
    strategy_branches_with_match: tuple[ProfileStrategyBranch, ...]
    strategy_id: str
    strategy_name: str
    list_type: str
    match_summary: str
    raw_profile_text: str
    editable: EditableProfileSettings
    editable_filter_kinds: tuple[str, ...]


def build_profile_derived_core(
    profile: Profile,
    *,
    catalogs: dict[str, dict[str, StrategyEntry]],
    app_paths,
    raw_profile_text: str | None = None,
) -> ProfileDerivedCore:
    raw_text = profile_raw_text(profile) if raw_profile_text is None else raw_profile_text
    strategy_entries = basic_strategy_entries(profile, catalogs)
    strategy_branches = strategy_branches_for_profile(profile, strategy_entries)
    strategy_id, strategy_name = profile_strategy_summary(profile, strategy_entries, strategy_branches)
    editable = read_editable_profile_settings(profile)
    # Проверки файлов hostlist/ipset — единственный диск в ядре; считаем один раз
    # и переиспользуем для list_type и editable_filter_kinds.
    filter_kinds = available_filter_kinds(editable, app_paths)
    list_type = _visible_list_type_for_kinds(profile, filter_kinds)
    match_summary = profile_match_summary(profile, list_type=list_type)
    return ProfileDerivedCore(
        strategy_entries=strategy_entries,
        strategy_branches=strategy_branches,
        strategy_branches_with_match=strategy_branches_with_match_text(
            strategy_branches,
            match_summary=match_summary,
        ),
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        list_type=list_type,
        match_summary=match_summary,
        raw_profile_text=raw_text,
        editable=editable,
        editable_filter_kinds=filter_kinds,
    )


class ProfileDerivedCache:
    """LRU контентных ядер. Не потокобезопасен: вызывающий держит лок сервиса."""

    def __init__(self, limit: int = PROFILE_DERIVED_CACHE_LIMIT) -> None:
        self._entries: OrderedDict[tuple[object, ...], ProfileDerivedCore] = OrderedDict()
        self._limit = max(1, int(limit))

    def core_for(
        self,
        profile: Profile,
        *,
        catalogs: dict[str, dict[str, StrategyEntry]],
        catalogs_signature: tuple[object, ...],
        app_paths,
    ) -> ProfileDerivedCore:
        raw_text = profile_raw_text(profile)
        cache_key = (profile.engine, catalogs_signature, raw_text)
        cached = self._entries.get(cache_key)
        if cached is not None:
            self._entries.move_to_end(cache_key)
            return cached
        core = build_profile_derived_core(
            profile,
            catalogs=catalogs,
            app_paths=app_paths,
            raw_profile_text=raw_text,
        )
        self._entries[cache_key] = core
        while len(self._entries) > self._limit:
            self._entries.popitem(last=False)
        return core


class PresetSourcesCache:
    """Sources пресета, посчитанные один раз на (ревизию, объект пресета, объект шаблонов).

    Идентичность объекта пресета в ключе покрывает нормализацию: она заменяет
    снапшот пресета при неизменной ревизии файла. Идентичность словаря шаблонов
    покрывает пользовательские профили: кэш шаблонов ключуется ревизией
    user_profiles, поэтому любая их запись даёт новый объект словаря.
    """

    def __init__(self) -> None:
        self._entry: tuple[tuple[object, ...], Preset, dict[str, Profile], tuple[Any, ...]] | None = None

    def sources_for(
        self,
        preset_revision: tuple[object, ...],
        preset: Preset,
        templates: dict[str, Profile],
    ) -> tuple[Any, ...]:
        entry = self._entry
        if entry is not None and entry[0] == preset_revision and entry[1] is preset and entry[2] is templates:
            return entry[3]
        sources = tuple(build_profile_list_sources(tuple(preset.profiles), templates))
        self._entry = (preset_revision, preset, templates, sources)
        return sources

    def clear(self) -> None:
        self._entry = None


def basic_strategy_entries(profile: Profile, catalogs: dict[str, dict[str, StrategyEntry]]) -> dict[str, StrategyEntry]:
    if profile_list_type(profile) == "custom":
        return {}
    return dict(catalogs.get(catalog_name_for_profile(profile)) or {})


def profile_strategy_summary(
    profile: Profile,
    entries: dict[str, StrategyEntry],
    branches: tuple[ProfileStrategyBranch, ...],
) -> tuple[str, str]:
    if len(branches) <= 1:
        return resolve_strategy(profile, entries)
    names = [str(branch.strategy_name or "").strip() for branch in branches if str(branch.strategy_name or "").strip()]
    visible = names[:2]
    suffix = f" +{len(names) - len(visible)}" if len(names) > len(visible) else ""
    label = ", ".join(visible)
    if label:
        return "custom", f"{len(branches)} стратегии: {label}{suffix}"
    return "custom", f"{len(branches)} стратегии"


def resolve_strategy(profile: Profile, entries: dict[str, StrategyEntry]) -> tuple[str, str]:
    return resolve_strategy_lines(profile, entries, getattr(profile.strategy, "strategy_lines", ()) or ())


@lru_cache(maxsize=4096)
def _entry_identity_lines(engine: str, args: str) -> tuple[str, ...]:
    """Identity-строки записи каталога.

    Зависят только от (engine, текст args) и без кэша пересчитывались бы для
    каждой пары «профиль × запись каталога» — O(профили × каталог) splitlines
    на каждую сборку списка.
    """
    normalized = normalize_lines(args.splitlines())
    if engine != ENGINE_WINWS2:
        return normalized
    return tuple(line for line in normalized if line.lower().startswith("--lua-desync="))


def resolve_strategy_lines(profile: Profile, entries: dict[str, StrategyEntry], lines) -> tuple[str, str]:
    current = strategy_identity_lines(profile, lines)
    if not current:
        return "none", "Стратегия не выбрана"
    matches = [
        entry
        for entry in entries.values()
        if _entry_identity_lines(profile.engine, entry.args) == current
    ]
    if len(matches) == 1:
        return matches[0].strategy_id, matches[0].name
    return "custom", "custom"


def strategy_branches_for_profile(profile: Profile, entries: dict[str, StrategyEntry]) -> tuple[ProfileStrategyBranch, ...]:
    if profile.engine != ENGINE_WINWS2:
        return ()

    payload = "all"
    in_range = "x"
    out_range = "a"
    raw_lines: list[str] = []
    branches: list[ProfileStrategyBranch] = []

    def flush() -> None:
        nonlocal raw_lines
        if not raw_lines:
            return
        strategy_id, strategy_name = resolve_strategy_lines(profile, entries, raw_lines)
        scope_lines = strategy_branch_scope_lines(payload=payload, in_range=in_range, out_range=out_range)
        branches.append(
            ProfileStrategyBranch(
                branch_id=f"branch:{len(branches)}",
                payload=payload,
                in_range=in_range,
                out_range=out_range,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                raw_strategy_text="\n".join((*scope_lines, *raw_lines)).strip(),
            )
        )
        raw_lines = []

    for segment in tuple(getattr(profile, "segments", ()) or ()):
        name = str(getattr(segment, "name", "") or "").strip().lower()
        text = str(getattr(segment, "text", "") or "").strip()
        if segment.kind == "strategy_filter":
            flush()
            value = str(getattr(segment, "value", "") or "").strip()
            if name == "--payload":
                payload = value or "all"
            elif name == "--in-range":
                in_range = value or "x"
            elif name == "--out-range":
                out_range = value or "a"
            continue
        if segment.kind == "strategy" and text:
            raw_lines.append(text)

    flush()
    return tuple(branches)


def strategy_branches_with_match_text(
    branches: tuple[ProfileStrategyBranch, ...],
    *,
    match_summary: str,
) -> tuple[ProfileStrategyBranch, ...]:
    return tuple(
        replace(
            branch,
            match_tab_text=build_profile_setup_match_tab_text(
                match_summary=match_summary,
                strategy_id=branch.strategy_id,
                strategy_name=branch.strategy_name,
                raw_strategy_text=branch.raw_strategy_text,
            ),
        )
        for branch in branches
    )


def strategy_branch_scope_lines(*, payload: str, in_range: str, out_range: str) -> tuple[str, ...]:
    lines: list[str] = []
    if str(in_range or "x").strip() != "x":
        lines.append(f"--in-range={str(in_range).strip()}")
    if str(out_range or "a").strip() != "a":
        lines.append(f"--out-range={str(out_range).strip()}")
    if str(payload or "all").strip() != "all":
        lines.append(f"--payload={str(payload).strip()}")
    return tuple(lines)


def normalize_lines(lines) -> tuple[str, ...]:
    return tuple(str(line or "").strip() for line in lines if str(line or "").strip())


def strategy_identity_lines(profile: Profile, lines) -> tuple[str, ...]:
    normalized = normalize_lines(lines)
    if profile.engine != ENGINE_WINWS2:
        return normalized
    return tuple(line for line in normalized if line.lower().startswith("--lua-desync="))


def catalog_name_for_profile(profile: Profile) -> str:
    return strategy_catalog_from_match_lines(tuple(profile.match.all_lines()))


def profile_list_type(profile: Profile) -> str:
    catalog_name = catalog_name_for_profile(profile)
    if catalog_name == "voice":
        return "voice"
    has_hostlist = bool(profile.match.hostlist_lines or profile.match.hostlist_domains_lines)
    has_ipset = bool(profile.match.ipset_lines or profile.match.inline_ipset_lines)
    has_excludes = bool(profile.match.hostlist_exclude_lines or profile.match.ipset_exclude_lines)
    if has_excludes:
        settings = read_editable_profile_settings(profile)
        if settings.filter_role == "exclude" and not (has_hostlist or has_ipset):
            if settings.filter_kind in {"hostlist", "ipset"}:
                return settings.filter_kind
        return "custom"
    if has_hostlist and has_ipset:
        return "custom"
    if has_hostlist:
        return "hostlist"
    if has_ipset:
        return "ipset"
    return catalog_name


def visible_list_type(profile: Profile, app_paths) -> str:
    settings = read_editable_profile_settings(profile)
    return _visible_list_type_for_kinds(profile, available_filter_kinds(settings, app_paths))


def _visible_list_type_for_kinds(profile: Profile, filter_kinds: tuple[str, ...]) -> str:
    list_type = profile_list_type(profile)
    if list_type not in {"hostlist", "ipset"}:
        return ""
    available = {kind for kind in filter_kinds if kind in {"hostlist", "ipset"}}
    if len(available) <= 1:
        return ""
    return list_type


def profile_has_filter_choice(profile: Profile, app_paths) -> bool:
    settings = read_editable_profile_settings(profile)
    if not settings.filter_editable:
        return False
    available = {
        kind
        for kind in available_filter_kinds(settings, app_paths)
        if kind in {"hostlist", "ipset"}
    }
    return len(available) > 1


def profile_match_summary(profile: Profile, *, list_type: str | None = None) -> str:
    match_lines = tuple(profile.match.all_lines())
    visible = profile_list_type(profile) if list_type is None else str(list_type or "")
    parts = [
        part
        for part in (protocol_label_from_match_lines(match_lines), ports_label_from_match_lines(match_lines), visible)
        if part
    ]
    return " • ".join(parts) or "без явных условий"


def available_filter_kinds(settings: EditableProfileSettings, app_paths) -> tuple[str, ...]:
    current_kind = str(settings.filter_kind or "hostlist").strip().lower()
    if not settings.filter_editable or current_kind not in {"hostlist", "ipset"}:
        return (current_kind,)

    result: list[str] = []
    for candidate in ("hostlist", "ipset"):
        if resolve_filter_kind_switch(settings, candidate, app_paths).allowed:
            result.append(candidate)
    return tuple(result) or (current_kind,)


def profile_raw_text(profile: Profile) -> str:
    return "\n".join(segment.text for segment in profile.segments if str(segment.text or "").strip()).strip()


__all__ = [
    "PROFILE_DERIVED_CACHE_LIMIT",
    "PresetSourcesCache",
    "ProfileDerivedCache",
    "ProfileDerivedCore",
    "available_filter_kinds",
    "basic_strategy_entries",
    "build_profile_derived_core",
    "catalog_name_for_profile",
    "normalize_lines",
    "profile_has_filter_choice",
    "profile_list_type",
    "profile_match_summary",
    "profile_raw_text",
    "profile_strategy_summary",
    "resolve_strategy",
    "resolve_strategy_lines",
    "strategy_branch_scope_lines",
    "strategy_branches_for_profile",
    "strategy_branches_with_match_text",
    "strategy_identity_lines",
    "visible_list_type",
]
