"""Связка автоподбора: проверить, найти, применить.

Порядок здесь не косметический:

1. Убедиться, что движок работает. Проверять доступность раньше — значит
   объявить недоступным всё и запустить перебор впустую.
2. Проверить цели. TLS до конца, с проверкой имени в сертификате.
3. Для каждой недоступной — перебор стратегий существующим сканером.
4. Найденное положить в профиль сайта И в общий профиль по адресам.
5. Перепроверить: подобранное могло и не помочь.

Перебор идёт минутами на каждую цель, поэтому всё выполняется в фоне и
никогда не роняет запуск. Не получилось — строка в логе, приложение
работает дальше.
"""

from __future__ import annotations

import threading

from autotune.plans import Decision, build_plan, describe_outcome, profiles_to_update
from log.log import log


#: Режим перебора. quick вместо full осознанно: full на трёх целях —
#: это десятки минут на машине человека, который просто открыл программу.
SCAN_MODE = "quick"

#: Сколько ждать один перебор. Дальше считаем, что не сложилось.
SCAN_TIMEOUT_SECONDS = 600.0


def is_engine_running() -> bool:
    try:
        from winws_runtime.runtime.system_ops import get_all_winws_process_pids

        return bool(get_all_winws_process_pids())
    except Exception as exc:
        log(f"Автоподбор: состояние движка не определить: {exc}", "DEBUG")
        return False


def run_autotune(
    *,
    presets_feature,
    scan_runner,
    already_scanned=(),
    report=None,
) -> dict[str, tuple[str, ...]]:
    """Проверяет цели и чинит недоступные. Возвращает применённое.

    scan_runner — вызываемое (target, protocol) -> список строк стратегии
    или пустой список. Вынесено параметром: перебор тянет за собой Qt и
    сеть, а решения должны проверяться без них.
    """
    from autotune.check import check_all

    def _say(text: str) -> None:
        log(f"Автоподбор: {text}", "INFO")
        if callable(report):
            try:
                report(text)
            except Exception:
                pass

    results = check_all()
    plan = build_plan(
        results,
        engine_running=is_engine_running(),
        already_scanned=already_scanned,
    )
    _say(plan.message)

    if plan.decision is not Decision.SCAN:
        return {}

    applied: dict[str, tuple[str, ...]] = {}
    for key in plan.targets:
        from autotune.targets import get_target

        target = get_target(key)
        if target is None:
            continue

        _say(f"подбираю стратегию для {target.title} — это надолго")
        try:
            lines = scan_runner(target.scan_target, target.protocol)
        except Exception as exc:
            log(f"Автоподбор: перебор для {target.title} не удался: {exc}", "⚠ WARNING")
            continue

        if not lines:
            _say(f"для {target.title} рабочая стратегия не нашлась")
            continue

        try:
            from autotune.apply import apply_strategy_to_named_profiles

            updated = apply_strategy_to_named_profiles(
                presets_feature=presets_feature,
                strategy_lines=lines,
                profile_names=profiles_to_update(key),
            )
        except Exception as exc:
            log(f"Автоподбор: применение для {target.title} не удалось: {exc}", "⚠ WARNING")
            continue

        if updated:
            applied[key] = updated

    _say(describe_outcome(applied))
    return applied


def run_in_background(**kwargs) -> threading.Thread:
    """Запускает автоподбор отдельным потоком.

    Отдельный поток обязателен: перебор идёт минутами, и в UI-потоке это
    было бы намертво замёрзшее окно.
    """

    def _run() -> None:
        try:
            run_autotune(**kwargs)
        except Exception as exc:
            log(f"Автоподбор не выполнился: {exc}", "⚠ WARNING")

    thread = threading.Thread(target=_run, name="autotune", daemon=True)
    thread.start()
    return thread


__all__ = [
    "SCAN_MODE",
    "SCAN_TIMEOUT_SECONDS",
    "is_engine_running",
    "run_autotune",
    "run_in_background",
]
