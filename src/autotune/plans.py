"""Решения автоподбора: что проверять, когда искать, куда применять.

Чистая логика без сети, файлов и Qt. Побочные эффекты живут в runtime.py.

Правила здесь не про удобство, а про то, чтобы не сделать хуже:

* Подбор запускается только когда движок УЖЕ работает. Иначе недоступным
  окажется всё, и на каждой машине сгорят минуты впустую.
* Подбор не запускается второй раз для той же цели в том же сеансе:
  перебор идёт минутами, и повторять его по кругу нельзя.
* Найденное кладётся и в профиль сайта, и в общий профиль по адресам.
  Только свой профиль чинит один домен, а не доступ вообще.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Decision(Enum):
    """Что делать после проверки."""

    #: Всё открывается — подбор не нужен.
    NOTHING = "nothing"
    #: Движок не работает: проверять и подбирать бессмысленно.
    ENGINE_DOWN = "engine_down"
    #: Есть недоступные цели — запускаем перебор.
    SCAN = "scan"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Итог проверки одной цели."""

    key: str
    available: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class TunePlan:
    """Что делать дальше."""

    decision: Decision
    targets: tuple[str, ...] = field(default_factory=tuple)
    message: str = ""


def build_plan(
    results,
    *,
    engine_running: bool,
    already_scanned=(),
) -> TunePlan:
    """Решает, нужен ли подбор и для каких целей.

    already_scanned — цели, для которых перебор в этом сеансе уже был.
    Повторять его нельзя: это минуты работы на каждую цель.
    """
    if not engine_running:
        return TunePlan(
            Decision.ENGINE_DOWN,
            message="Обход не запущен — проверять доступность нечем",
        )

    done = {str(key or "").strip().lower() for key in already_scanned or ()}
    broken = [
        str(item.key)
        for item in results or ()
        if not item.available and str(item.key).lower() not in done
    ]

    if not broken:
        return TunePlan(Decision.NOTHING, message="Проверенные сайты открываются")

    return TunePlan(
        Decision.SCAN,
        targets=tuple(broken),
        message="Не открылось: " + ", ".join(broken),
    )


def profiles_to_update(target_key: str) -> tuple[str, ...]:
    """Куда класть найденную стратегию.

    Всегда несколько: профиль самого сайта и общий профиль по адресам.
    Правка одного лишь профиля сайта чинит этот сайт, а не доступ.
    """
    from autotune.targets import get_target

    target = get_target(target_key)
    return tuple(target.profiles) if target is not None else ()


def describe_outcome(applied: dict[str, tuple[str, ...]]) -> str:
    """Человеческий итог. Пусто — значит ничего не нашли и не применили."""
    if not applied:
        return "Подходящая стратегия не нашлась. Попробуйте подбор вручную в разделе диагностики."

    parts = []
    for key, profiles in applied.items():
        if profiles:
            parts.append(f"{key}: обновлено профилей — {len(profiles)}")
    if not parts:
        return "Стратегия найдена, но применить её не удалось"
    return "Подобрано и применено. " + "; ".join(parts)


__all__ = [
    "CheckResult",
    "Decision",
    "TunePlan",
    "build_plan",
    "describe_outcome",
    "profiles_to_update",
]
