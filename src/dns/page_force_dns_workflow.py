"""Force DNS workflow/helper'ы для канонической DNS страницы."""

from __future__ import annotations


def apply_force_dns_status_state(
    *,
    has_status_label: bool,
    enabled: bool,
    details_key: str | None,
    details_kwargs: dict | None,
    details_fallback: str,
    set_enabled_state_fn,
    set_details_key_fn,
    set_details_kwargs_fn,
    set_details_fallback_fn,
    update_force_dns_status_label_fn,
) -> None:
    if not has_status_label:
        return

    set_enabled_state_fn(bool(enabled))
    set_details_key_fn(details_key)
    set_details_kwargs_fn(dict(details_kwargs or {}))
    set_details_fallback_fn(details_fallback or "")
    update_force_dns_status_label_fn(
        enabled=enabled,
        details_key=details_key,
        details_kwargs=details_kwargs,
        details_fallback=details_fallback,
    )
