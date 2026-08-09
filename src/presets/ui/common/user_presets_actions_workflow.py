"""Общий workflow действий для страницы пользовательских preset-ов."""

from __future__ import annotations

from qfluentwidgets import FluentIcon


def _tr_key(tr_prefix: str, suffix: str) -> str:
    return f"{tr_prefix}.{suffix}"


def _set_button_text_if_changed(button, text: str) -> bool:
    value = str(text or "")
    try:
        current = getattr(button, "text", None)
        current_value = str(current()) if callable(current) else str(current)
        if current_value == value:
            return False
    except Exception:
        pass
    button.setText(value)
    return True


def _set_button_icon_if_changed(button, icon) -> bool:
    if getattr(button, "_last_user_preset_action_icon", None) == icon:
        return False
    setattr(button, "_last_user_preset_action_icon", icon)
    button.setIcon(icon)
    return True


def show_reset_all_result(
    *,
    cleanup_in_progress: bool,
    success_count: int,
    total_count: int,
    failed_count: int = 0,
    reset_all_btn,
    single_shot_fn,
    restore_label_fn,
) -> None:
    if cleanup_in_progress:
        return
    _ = total_count
    ok = int(success_count or 0)
    failed = int(failed_count or 0)
    try:
        if failed > 0:
            text = f"Ошибки: {failed}"
            icon = FluentIcon.INFO
        elif ok > 0:
            text = f"Сброшено: {ok}"
            icon = FluentIcon.ACCEPT
        else:
            text = "Нечего менять"
            icon = FluentIcon.ACCEPT
        _set_button_text_if_changed(reset_all_btn, text)
        _set_button_icon_if_changed(reset_all_btn, icon)
    except Exception:
        pass
    single_shot_fn(3000, restore_label_fn)


def restore_reset_all_button_label(
    *,
    cleanup_in_progress: bool,
    reset_all_btn,
    tr_fn,
    tr_prefix: str,
) -> None:
    if cleanup_in_progress:
        return
    try:
        _set_button_text_if_changed(
            reset_all_btn,
            tr_fn(_tr_key(tr_prefix, "button.reset_all"), "Вернуть встроенные"),
        )
        _set_button_icon_if_changed(reset_all_btn, FluentIcon.RETURN)
    except Exception:
        pass
