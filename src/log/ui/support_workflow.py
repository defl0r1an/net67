"""Support workflow helper'ы для страницы логов."""

from __future__ import annotations


def update_orchestra_indicator(*, container, is_orchestra_mode: bool) -> None:
    if container is None:
        return
    container.setVisible(bool(is_orchestra_mode))


def apply_support_feedback(
    *,
    result,
    build_feedback_fn,
    build_error_feedback_fn,
    info_bar,
    parent,
    log_fn,
    render_status_fn,
    status_state_setter,
) -> None:
    try:
        archive_paths = list(getattr(result, "archive_paths", None) or ([result.zip_path] if getattr(result, "zip_path", None) else []))
        if archive_paths:
            log_fn(f"Подготовлены архивы поддержки: {', '.join(archive_paths)}", "INFO")
        feedback = build_feedback_fn(result)
        status_state_setter(feedback.status_text, feedback.status_tone)
        render_status_fn()

        if info_bar:
            info_bar.success(
                title=feedback.infobar_title,
                content=feedback.infobar_content,
                parent=parent,
                duration=5000,
            )
    except Exception as e:
        log_fn(f"Ошибка подготовки обращения из логов: {e}", "ERROR")
        feedback = build_error_feedback_fn(str(e))
        status_state_setter(feedback.status_text, feedback.status_tone)
        render_status_fn()
        if info_bar:
            info_bar.warning(
                title=feedback.infobar_title,
                content=feedback.infobar_content,
                parent=parent,
            )
