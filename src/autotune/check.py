"""Проверка доступности целей. Сеть есть, Qt нет.

Проверяем не TCP-коннектом, а полным TLS с проверкой имени в
сертификате. Причина известна на опыте: запись в hosts уводит домен на
чужой адрес, тот адрес охотно принимает TCP — и проверка рапортует
«открывается», пока в браузере не открывается ничего.
"""

from __future__ import annotations

from autotune.plans import CheckResult
from autotune.targets import TARGETS, Target
from log.log import log


#: Сколько ждать один сайт. Больше нет смысла: живой сайт отвечает
#: быстро, а мёртвый всё равно не ответит.
CHECK_TIMEOUT_SECONDS = 6.0


def check_target(target: Target, *, timeout: float = CHECK_TIMEOUT_SECONDS) -> CheckResult:
    from oneclick.deps import probe_domain_over_https

    try:
        ok = probe_domain_over_https(target.url, timeout=timeout)
    except Exception as exc:
        return CheckResult(target.key, False, f"проверка не выполнилась: {exc}")

    return CheckResult(target.key, bool(ok), "" if ok else "не открывается")


def check_all(*, timeout: float = CHECK_TIMEOUT_SECONDS) -> list[CheckResult]:
    results = [check_target(target, timeout=timeout) for target in TARGETS]
    broken = [item.key for item in results if not item.available]
    log(
        "Автопроверка сайтов: "
        + (f"не открылось — {', '.join(broken)}" if broken else "всё открывается"),
        "INFO",
    )
    return results


__all__ = ["CHECK_TIMEOUT_SECONDS", "check_all", "check_target"]
