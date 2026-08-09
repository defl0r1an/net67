"""Workflow истории логов Orchestra."""

from __future__ import annotations

from dataclasses import dataclass

import orchestra.page_runtime as orchestra_page_runtime


@dataclass(frozen=True)
class OrchestraLogViewResult:
    content: str
    message_text: str


@dataclass(frozen=True)
class OrchestraLogDeleteResult:
    deleted: bool
    message_text: str


@dataclass(frozen=True)
class OrchestraLogClearResult:
    deleted_count: int
    message_text: str


def view_log_history_entry(*, runner, log_id: str) -> OrchestraLogViewResult:
    """Возвращает содержимое выбранного лога и сообщение для UI."""
    content = runner.get_log_content(log_id)
    plan = orchestra_page_runtime.build_log_history_view_plan(
        log_id=log_id,
        has_content=bool(content),
    )
    return OrchestraLogViewResult(
        content=content or "",
        message_text=plan.message_text,
    )


def delete_log_history_entry(*, runner, log_id: str) -> OrchestraLogDeleteResult:
    """Удаляет выбранный лог и возвращает результат для UI."""
    deleted = bool(runner.delete_log(log_id))
    plan = orchestra_page_runtime.build_log_history_delete_plan(
        log_id=log_id,
        deleted=deleted,
    )
    return OrchestraLogDeleteResult(
        deleted=deleted,
        message_text=plan.message_text,
    )


def clear_log_history_entries(*, runner) -> OrchestraLogClearResult:
    """Удаляет все сохранённые логи orchestra."""
    deleted_count = runner.clear_all_logs()
    plan = orchestra_page_runtime.build_log_history_clear_all_plan(
        deleted_count=deleted_count,
    )
    return OrchestraLogClearResult(
        deleted_count=deleted_count,
        message_text=plan.message_text,
    )
