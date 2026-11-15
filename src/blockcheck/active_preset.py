"""Сопоставление HTTPS-пробы с правилами запущенного пресета."""

from __future__ import annotations

import os

from blockcheck.preset_match import https_profile_matches
from diagnostics.verdict import ReachState
from settings.mode import ENGINE_WINWS2, ZAPRET2_MODE


def current():
    from winws_runtime.runners.runner_factory import get_current_runner

    runner = get_current_runner()
    if runner is not None:
        return runner.get_running_preset()
    return None


def _file(state) -> str:
    return os.path.basename(state.preset_path)


def _identity(state) -> dict:
    return {"file": _file(state), "pid": state.pid, "generation": state.generation}


def _strategy_name(profile, catalogs) -> str:
    from profile.derived_cache import basic_strategy_entries, resolve_strategy

    return resolve_strategy(profile, basic_strategy_entries(profile, catalogs))[1]


def annotate(snapshot, probes) -> None:
    """Добавляет факты только если движок не переключился во время проб."""
    if snapshot is None or current() != snapshot:
        return
    eligible = [
        probe for probe in probes
        if probe.reach_state in {ReachState.DPI, ReachState.FREEZE, ReachState.IP_BLOCK}
        and probe.reach is not None and probe.reach.ip
    ]
    if not eligible:
        return
    from config.runtime_layout import APPLICATION_PATHS
    from lists.core.paths import get_lists_dir
    from profile.parser import parse_preset_text
    from profile.strategy_catalog import load_strategy_catalogs

    state, artifact = snapshot
    file_name = _file(state)
    preset = parse_preset_text(artifact.normalized_text, engine=ENGINE_WINWS2, source_name=file_name)
    name = state.strategy_name.removeprefix("Пресет: ").strip() or file_name
    catalogs = None
    strategies: dict[str, str] = {}
    matches = https_profile_matches(
        preset, [(probe.host, probe.reach.ip) for probe in eligible], lists_dir=get_lists_dir(),
    )
    for probe, match in zip(eligible, matches):
        if match is None:
            continue
        profile, reason = match
        if profile is None:
            probe.preset_profile = {"text": f"В пресете «{name}» не найден профиль для этого HTTPS-запроса."}
            continue
        if profile.key not in strategies:
            if catalogs is None:
                catalogs = load_strategy_catalogs(APPLICATION_PATHS, ENGINE_WINWS2)
            strategies[profile.key] = _strategy_name(profile, catalogs)
        strategy = strategies[profile.key]
        probe.preset_profile = {
            "text": f"Пресет «{name}», профиль «{profile.display_name}»: {reason}. Стратегия: {strategy}.",
            "action": {**_identity(state), "profile_key": profile.key},
            "label": profile.display_name,
        }
    if current() != snapshot:
        for probe in eligible:
            probe.preset_profile = None


def open_profile(action: dict, *, selected_path, navigate) -> bool:
    """Не переходим к чужой строке, если поменялся процесс, пресет или его файл."""
    snapshot = current()
    if snapshot is None:
        return False
    state, artifact = snapshot
    if any(action.get(key) != value for key, value in _identity(state).items()):
        return False
    source_key = artifact.source_key or artifact.cache_key
    profile_key = str(action.get("profile_key") or "")
    if not source_key or not profile_key:
        return False
    try:
        path = selected_path(ZAPRET2_MODE)
        if not path or os.path.normcase(os.fspath(path)) != source_key[0]:
            return False
        stat = os.stat(path)
    except (OSError, RuntimeError):
        return False
    if (stat.st_mtime_ns, stat.st_size) != source_key[1:3] or current() != snapshot:
        return False
    return bool(navigate(ZAPRET2_MODE, profile_key))
