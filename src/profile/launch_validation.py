from __future__ import annotations

from settings.mode import ZAPRET1_MODE, engine_for_launch_method, normalize_launch_method

from .parser import parse_preset_text


def preset_filter_flags_for_launch_method(launch_method: str) -> tuple[str, ...]:
    method = normalize_launch_method(launch_method, default="")
    if method == ZAPRET1_MODE:
        return ("--wf-tcp=", "--wf-udp=")
    return ("--wf-tcp-out", "--wf-udp-out", "--wf-raw-part")


def preset_has_required_filter_flags(launch_method: str, text: str) -> bool:
    content = str(text or "")
    return any(flag in content for flag in preset_filter_flags_for_launch_method(launch_method))


def preset_has_enabled_profiles(launch_method: str, text: str) -> bool:
    try:
        engine = engine_for_launch_method(normalize_launch_method(launch_method, default=""))
        preset = parse_preset_text(str(text or ""), engine=engine)
    except Exception:
        return False
    return any(bool(getattr(profile, "enabled", False)) for profile in tuple(preset.profiles or ()))


def preset_has_enabled_profiles_for_launch(launch_method: str, text: str) -> bool:
    return preset_has_required_filter_flags(launch_method, text) and preset_has_enabled_profiles(launch_method, text)
