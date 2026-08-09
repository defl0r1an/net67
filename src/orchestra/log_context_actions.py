"""Действия контекстного меню лога Orchestra."""

from __future__ import annotations

import orchestra.page_runtime as orchestra_page_runtime
from orchestra.ignored_targets import is_orchestra_ignored_target


def is_strategy_blocked(*, runner, domain: str, strategy: int) -> bool:
    """Проверяет, заблокирована ли стратегия для домена."""
    if runner is None:
        return False
    return bool(runner.blocked_manager.is_blocked(domain, strategy))


def lock_strategy_from_log(*, runner, domain: str, strategy: int, protocol: str):
    """Залочить стратегию из строки лога."""
    return orchestra_page_runtime.lock_strategy(
        runner,
        domain=domain,
        strategy=strategy,
        protocol=protocol,
        ignored_target=is_orchestra_ignored_target(domain),
    )


def block_strategy_from_log(*, runner, domain: str, strategy: int, protocol: str):
    """Заблокировать стратегию из строки лога."""
    return orchestra_page_runtime.block_strategy(
        runner,
        domain=domain,
        strategy=strategy,
        protocol=protocol,
        ignored_target=is_orchestra_ignored_target(domain),
    )


def unblock_strategy_from_log(*, runner, domain: str, strategy: int, protocol: str):
    """Разблокировать стратегию из строки лога."""
    return orchestra_page_runtime.unblock_strategy(
        runner,
        domain=domain,
        strategy=strategy,
        protocol=protocol,
    )


def add_to_whitelist_from_log(*, runner, domain: str):
    """Добавить домен из строки лога в белый список."""
    return orchestra_page_runtime.add_to_whitelist(runner, domain=domain)
