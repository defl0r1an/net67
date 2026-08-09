from __future__ import annotations

from pathlib import Path

from presets.list_metadata import build_preset_stat_metadata, read_preset_list_metadata, read_preset_stat_metadata


def build_lightweight_preset_metadata(
    path: Path,
    *,
    display_name: str,
    kind: str,
    is_builtin: bool,
    can_reset_to_builtin: bool = False,
    read_headers: bool = True,
    stat_result=None,
) -> dict[str, object]:
    normalized_display_name = str(display_name or path.name).strip()
    normalized_kind = str(kind or "").strip() or "user"
    normalized_is_builtin = bool(is_builtin)
    normalized_can_reset_to_builtin = bool(can_reset_to_builtin)

    try:
        if read_headers:
            list_metadata = read_preset_list_metadata(path)
        elif stat_result is not None:
            list_metadata = build_preset_stat_metadata(stat_result)
        else:
            list_metadata = read_preset_stat_metadata(path)
        return {
            **list_metadata,
            "display_name": normalized_display_name,
            "kind": normalized_kind,
            "is_builtin": normalized_is_builtin,
            "can_reset_to_builtin": normalized_can_reset_to_builtin,
        }
    except Exception:
        return {
            "description": "",
            "modified_display": "",
            "icon_color": "",
            "display_name": normalized_display_name,
            "kind": normalized_kind,
            "is_builtin": normalized_is_builtin,
            "can_reset_to_builtin": normalized_can_reset_to_builtin,
        }
