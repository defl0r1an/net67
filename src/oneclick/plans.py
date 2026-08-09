"""Чистая логика оркестратора «одной кнопки».

Здесь нет ни Qt, ни обращений к системе — только решения о том, что и в
каком порядке делать. Побочные эффекты живут в oneclick/runner.py.

Главный принцип порядка шагов — обратимость, а не логика.
Сначала выполняется то, что откатывается мгновенно (запуск winws — просто
снять процесс), затем состояние (Telegram-прокси), и только в самом конце
то, что переживает удаление приложения (hosts, DNS).

Смысл в том, что при падении на любом шаге система остаётся нетронутой в
персистентной части. Обратный порядок дал бы худший исход: правку hosts
сделали, winws не поднялся, а откатывать уже нечем.
"""

from __future__ import annotations

from dataclasses import dataclass

from oneclick.state import (
    OneClickOutcome,
    OneClickState,
    OneClickStep,
    StepKey,
    StepResult,
)


@dataclass(frozen=True, slots=True)
class OneClickRequest:
    """Что пользователь хочет включить.

    Формируется из ответов мастера первого запуска и настроек.
    """

    #: Сервисы, отмеченные пользователем: youtube, discord, telegram, games...
    services: frozenset[str] = frozenset()
    #: Готовые пары «домен -> адрес» для файла hosts. Пусто — не трогаем.
    #:
    #: Раньше поле называлось hosts_profiles, и из-за имени его передавали
    #: в apply_service_profiles, которая ждёт «сервис -> профиль DNS».
    #: Домены принимались за имена сервисов, и включение падало с
    #: «Не найдено записей hosts для выбранных сервисов».
    hosts_entries: dict[str, str] | None = None
    #: Разрешено ли менять DNS, если обнаружена подмена.
    allow_dns_fix: bool = True
    #: Делать ли самопроверку после запуска.
    run_selfcheck: bool = True
    #: Нужен ли локальный прокси для Telegram. Раньше здесь проверялось
    #: `"telegram" in services`, из-за чего оркестратор знал конкретные
    #: ключи мастера и ломался при их переименовании.
    needs_telegram_proxy: bool = False


_STEP_TITLES: dict[StepKey, str] = {
    StepKey.CONFLICTS: "Проверка конфликтующих программ",
    StepKey.DPI: "Запуск обхода",
    StepKey.TELEGRAM_PROXY: "Прокси для Telegram",
    StepKey.HOSTS: "Разблокировка сервисов",
    StepKey.DNS: "Проверка DNS",
    StepKey.SELFCHECK: "Проверка доступности",
}


def _step(key: StepKey, *, persistent: bool = False, read_only: bool = False) -> OneClickStep:
    return OneClickStep(
        key=key,
        title=_STEP_TITLES[key],
        persistent=persistent,
        read_only=read_only,
    )


def build_enable_plan(request: OneClickRequest) -> tuple[OneClickStep, ...]:
    """Собирает список шагов включения под конкретный запрос."""
    steps: list[OneClickStep] = [
        # Обратимые шаги.
        _step(StepKey.CONFLICTS, read_only=True),
        _step(StepKey.DPI),
    ]

    if request.needs_telegram_proxy:
        steps.append(_step(StepKey.TELEGRAM_PROXY))

    # Персистентные шаги — в самом конце.
    if request.hosts_entries:
        steps.append(_step(StepKey.HOSTS, persistent=True))

    if request.allow_dns_fix:
        # Сам шаг сначала только проверяет целостность DNS и меняет его
        # лишь при обнаруженной подмене — поэтому persistent «условно».
        steps.append(_step(StepKey.DNS, persistent=True))

    if request.run_selfcheck:
        steps.append(_step(StepKey.SELFCHECK, read_only=True))

    return tuple(steps)


#: Шаги, которые ничего не меняют в системе и потому не откатываются.
_READ_ONLY_STEPS = frozenset({StepKey.CONFLICTS, StepKey.SELFCHECK})


def build_rollback_plan(results: list[StepResult]) -> tuple[StepKey, ...]:
    """Что откатывать после неудачного включения.

    Откатываем каждый шаг, который пытались выполнить, в порядке, обратном
    выполнению.

    Важно, что упавшие шаги тоже откатываются. Соблазнительно откатывать
    только успешные, но это ошибка: шаг может упасть уже после того, как
    начал менять систему. Например, apply_hosts успел переписать часть
    файла и споткнулся на правах — вернуть исходник всё равно нужно.

    Пропущенные шаги не трогаем: они гарантированно ничего не изменили.
    Повторный откат того, что не менялось, безвреден — остановить
    незапущенный процесс или вернуть неизменённый файл ничего не ломает.
    """
    rollback: list[StepKey] = []
    for result in reversed(results):
        if result.skipped or result.key in _READ_ONLY_STEPS:
            continue
        rollback.append(result.key)
    return tuple(rollback)


def build_disable_plan() -> tuple[StepKey, ...]:
    """Что делает повторное нажатие.

    Останавливаем только обратимое. hosts и DNS намеренно не трогаем:
    разблокировка сервисов — отдельная настройка пользователя, и терять
    её при каждом выключении неправильно. Для отката есть отдельная
    кнопка в расширенных настройках.
    """
    return (StepKey.TELEGRAM_PROXY, StepKey.DPI)


def summarize(results: list[StepResult]) -> OneClickOutcome:
    """Превращает результаты шагов в итоговое состояние кнопки."""
    failed = [r for r in results if not r.ok and not r.skipped]

    if failed:
        first = failed[0]
        return OneClickOutcome(
            state=OneClickState.ERROR,
            results=list(results),
            message=first.message or f"Не удалось выполнить: {_STEP_TITLES.get(first.key, first.key)}",
        )

    selfcheck = next((r for r in results if r.key is StepKey.SELFCHECK), None)
    if selfcheck is not None and selfcheck.skipped:
        selfcheck = None

    message = selfcheck.message if selfcheck else "Работает"

    # Пропущенные шаги с объяснением. Пропуск не ошибка, но молчать о
    # нём нельзя: человек нажал «Включить» ради Telegram, шаг тихо не
    # выполнился, и на экране написано «Работает».
    notes = [
        str(result.note).strip()
        for result in results
        if str(getattr(result, "note", "") or "").strip()
    ]
    if notes:
        message = ". ".join([message.rstrip(". ")] + notes)

    return OneClickOutcome(
        state=OneClickState.RUNNING,
        results=list(results),
        message=message,
    )


def build_selfcheck_message(*, total: int, failed_domains: tuple[str, ...]) -> str:
    """Текст результата самопроверки.

    Пользователю важно не «проверка выполнена», а открылись сайты или нет.
    """
    total = max(0, int(total))
    if total == 0:
        return "Работает"
    if not failed_domains:
        return "Работает, проверенные сайты открываются"

    shown = ", ".join(failed_domains[:3])
    if len(failed_domains) > 3:
        shown += f" и ещё {len(failed_domains) - 3}"
    if len(failed_domains) >= total:
        return f"Запущено, но сайты не открываются: {shown}"
    return f"Работает частично, не открываются: {shown}"


def should_change_dns(integrity_results: list) -> tuple[bool, str]:
    """Решает, менять ли DNS, по результатам проверки целостности.

    Меняем только при реально обнаруженной подмене: несовпадение ответов
    UDP и DoH либо заглушка провайдера. Если подмены нет — не трогаем
    сеть вообще. Это главная защита от «после вашей программы отвалились
    внутренние адреса и VPN».
    """
    if not integrity_results:
        return (False, "Проверка DNS не дала результата")

    comparable = [r for r in integrity_results if getattr(r, "is_comparable", False)]
    if not comparable:
        return (False, "DNS не удалось проверить, оставляем как есть")

    spoofed = [
        r
        for r in comparable
        if not getattr(r, "is_consistent", True) or getattr(r, "is_stub", False)
    ]
    if not spoofed:
        return (False, "DNS провайдера корректен, менять не нужно")

    domains = ", ".join(str(getattr(r, "domain", "")) for r in spoofed[:3] if getattr(r, "domain", ""))
    return (True, f"Обнаружена подмена DNS ({domains}), назначаем свой")


__all__ = [
    "OneClickRequest",
    "build_disable_plan",
    "build_enable_plan",
    "build_rollback_plan",
    "build_selfcheck_message",
    "should_change_dns",
    "summarize",
]
