"""Helper-слой выбора профилей и direct-toggle для Hosts page."""

from __future__ import annotations

from collections.abc import Callable


def _set_toggle_state_silently(
    control,
    *,
    checked: bool | None = None,
    enabled: bool | None = None,
    get_building_state: Callable[[], bool],
    set_building_state: Callable[[bool], None],
) -> None:
    was_building = get_building_state()
    set_building_state(True)
    try:
        if checked is not None:
            control.setChecked(checked)
        if enabled is not None:
            control.setEnabled(enabled)
    finally:
        set_building_state(was_building)


def apply_bulk_profile_selection_ui(
    *,
    plan,
    profile_name: str | None,
    service_names: list[str],
    service_combos: dict,
    is_fluent_combo: Callable[[object], bool],
    toggle_cls,
    get_building_state: Callable[[], bool],
    set_building_state: Callable[[bool], None],
    update_profile_visual: Callable[[str], None],
    log_debug: Callable[[str], None],
) -> dict[str, str] | None:
    if not plan.changed:
        if plan.skipped_services:
            log_debug(
                "Hosts: профиль недоступен для: "
                + ", ".join(plan.skipped_services[:8])
                + ("…" if len(plan.skipped_services) > 8 else "")
            )
        return None

    target_profile = (profile_name or "").strip()
    for service_name in service_names:
        control = service_combos.get(service_name)
        if not control:
            continue

        if is_fluent_combo(control):
            target_idx = control.findData(target_profile) if target_profile else 0
            if target_idx >= 0 and control.currentIndex() != target_idx:
                control.blockSignals(True)
                control.setCurrentIndex(target_idx)
                control.blockSignals(False)
        elif isinstance(control, toggle_cls):
            desired = bool(target_profile)
            if control.isChecked() != desired:
                _set_toggle_state_silently(
                    control,
                    checked=desired,
                    get_building_state=get_building_state,
                    set_building_state=set_building_state,
                )

        update_profile_visual(service_name)

    return dict(plan.new_selection)


def apply_direct_toggle_ui(
    *,
    plan,
    service_name: str,
    service_combos: dict,
    toggle_cls,
    get_building_state: Callable[[], bool],
    set_building_state: Callable[[bool], None],
    update_profile_visual: Callable[[str], None],
) -> tuple[dict[str, str], bool]:
    if plan.force_checked is not None or plan.force_enabled is not None:
        control = service_combos.get(service_name)
        if isinstance(control, toggle_cls):
            _set_toggle_state_silently(
                control,
                checked=plan.force_checked,
                enabled=plan.force_enabled,
                get_building_state=get_building_state,
                set_building_state=set_building_state,
            )
        return dict(plan.new_selection), False

    update_profile_visual(service_name)
    return dict(plan.new_selection), bool(plan.apply_now)


def apply_profile_selection_ui(
    *,
    plan,
    service_name: str,
    update_profile_visual: Callable[[str], None],
) -> tuple[dict[str, str], bool]:
    update_profile_visual(service_name)
    return dict(plan.new_selection), bool(plan.apply_now)
