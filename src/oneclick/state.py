"""Состояния и типы оркестратора «одной кнопки».

Модуль намеренно без зависимостей от Qt и от рантайма приложения:
его можно импортировать и тестировать отдельно.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OneClickState(Enum):
    """Состояние главной кнопки.

    Это машина состояний, а не тумблер: «Проверка» и «Ошибка» —
    самостоятельные состояния, в которых интерфейс показывает разное.
    """

    OFF = "off"
    PREPARING = "preparing"
    CHECKING = "checking"
    RUNNING = "running"
    ERROR = "error"


#: Состояния, в которых повторное нажатие означает «выключить».
ACTIVE_STATES = frozenset({OneClickState.RUNNING, OneClickState.CHECKING})

#: Состояния, в которых кнопка занята и нажатие игнорируется.
BUSY_STATES = frozenset({OneClickState.PREPARING})


class StepKey(str, Enum):
    """Идентификаторы шагов включения."""

    CONFLICTS = "conflicts"
    DPI = "dpi"
    TELEGRAM_PROXY = "telegram_proxy"
    HOSTS = "hosts"
    DNS = "dns"
    SELFCHECK = "selfcheck"


@dataclass(frozen=True, slots=True)
class OneClickStep:
    """Один шаг включения.

    persistent=True означает, что последствия шага переживают закрытие и
    даже удаление приложения (правка hosts, смена DNS). Такие шаги
    выполняются последними и откатываются первыми.
    """

    key: StepKey
    title: str
    persistent: bool = False
    #: Шаг только читает состояние системы и ничего не меняет.
    read_only: bool = False


@dataclass(frozen=True, slots=True)
class StepResult:
    key: StepKey
    ok: bool
    message: str = ""
    #: Шаг не выполнялся, потому что не потребовался.
    skipped: bool = False
    #: Что из этого шага стоит сказать человеку.
    #:
    #: Отдельно от message намеренно. message — для лога и разбора: там
    #: и «Подмена DNS не обнаружена», и прочая диагностика, которую на
    #: экране показывать нечего. В note попадает только то, ради чего
    #: человек мог нажать кнопку и чего не произошло.
    note: str = ""


@dataclass(slots=True)
class OneClickOutcome:
    """Итог попытки включения."""

    state: OneClickState
    results: list[StepResult] = field(default_factory=list)
    message: str = ""
    #: Домены, которые не открылись при самопроверке.
    failed_domains: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.state is OneClickState.RUNNING


__all__ = [
    "ACTIVE_STATES",
    "BUSY_STATES",
    "OneClickOutcome",
    "OneClickState",
    "OneClickStep",
    "StepKey",
    "StepResult",
]
