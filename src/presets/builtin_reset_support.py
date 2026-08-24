from __future__ import annotations

from pathlib import Path

from log.log import log
from settings.mode import ALL_ENGINES

from .builtin_catalog import list_builtin_presets


def reset_all_builtin_overrides(engine: str, app_paths) -> tuple[int, int, list[str]]:
    engine_key = str(engine or "").strip().lower()
    if engine_key not in ALL_ENGINES:
        raise ValueError(f"Unsupported preset engine: {engine}")

    engine_paths = app_paths.engine_paths(engine_key).ensure_directories()
    builtin_paths = list_builtin_presets(engine_paths.builtin_presets_dir)
    removed = 0
    failed: list[str] = []

    for builtin_path in builtin_paths:
        user_path = engine_paths.user_presets_dir / builtin_path.name
        if not user_path.exists():
            continue
        try:
            user_path.unlink()
            removed += 1
        except Exception as exc:
            failed.append(_display_name_for_failed_preset(builtin_path))
            log(f"Failed to remove {engine_key} user preset override '{user_path.name}': {exc}", "DEBUG")

    return (removed, len(builtin_paths), failed)


def _display_name_for_failed_preset(path: Path) -> str:
    return Path(path).stem
