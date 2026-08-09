"""Исполнитель шагов «одной кнопки».

Все обращения к системе приходят снаружи в виде функций (OneClickDeps).
Благодаря этому оркестрацию — порядок, пропуски, откат при сбое — можно
полностью протестировать без Windows, Qt и прав администратора.

Реальные зависимости собираются в oneclick/deps.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from oneclick.plans import (
    OneClickRequest,
    build_disable_plan,
    build_enable_plan,
    build_rollback_plan,
    build_selfcheck_message,
    should_change_dns,
    summarize,
)
from oneclick.state import OneClickOutcome, OneClickState, StepKey, StepResult


@dataclass(slots=True)
class OneClickDeps:
    """Внешние операции, которые умеет выполнять оркестратор.

    Каждая возвращает (успех, сообщение), кроме явно описанных.
    """

    # Обратимые операции.
    check_conflicts: Callable[[], tuple[bool, str]]
    start_dpi: Callable[[], tuple[bool, str]]
    stop_dpi: Callable[[], tuple[bool, str]]
    #: Готов ли Telegram принять переадресацию. Второе значение —
    #: объяснение для человека, если не готов.
    check_telegram_ready: Callable[[], tuple[bool, str]]
    start_telegram_proxy: Callable[[], tuple[bool, str]]
    stop_telegram_proxy: Callable[[], tuple[bool, str]]

    # Персистентные операции.
    backup_hosts: Callable[[], tuple[bool, str]]
    apply_hosts: Callable[[dict[str, str]], tuple[bool, str]]
    restore_hosts: Callable[[], tuple[bool, str]]

    check_dns_integrity: Callable[[], list]
    apply_dns: Callable[[], tuple[bool, str]]
    restore_dns: Callable[[], tuple[bool, str]]

    # Проверка доступности: возвращает (сколько проверено, что не открылось).
    probe_domains: Callable[[], tuple[int, tuple[str, ...]]]

    #: Куда сообщать о прогрессе. Необязательно.
    report: Callable[[OneClickState, str], None] | None = None


class OneClickRunner:
    """Выполняет включение и выключение по плану."""

    def __init__(self, deps: OneClickDeps):
        self._deps = deps
        self._state = OneClickState.OFF

    @property
    def state(self) -> OneClickState:
        return self._state

    def _set_state(self, state: OneClickState, message: str = "") -> None:
        self._state = state
        report = self._deps.report
        if report is not None:
            try:
                report(state, message)
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────
    # Включение
    # ──────────────────────────────────────────────────────────────────

    def enable(self, request: OneClickRequest) -> OneClickOutcome:
        self._set_state(OneClickState.PREPARING, "Подготовка")

        results: list[StepResult] = []
        failed_domains: tuple[str, ...] = ()

        for step in build_enable_plan(request):
            if step.key is StepKey.SELFCHECK:
                self._set_state(OneClickState.CHECKING, "Проверка доступности")

            result, extra = self._run_step(step.key, request)
            results.append(result)
            if extra:
                failed_domains = extra

            if not result.ok and not result.skipped:
                # Откатываем всё, что успели изменить, и сообщаем причину.
                self._rollback(results)
                outcome = summarize(results)
                outcome.failed_domains = failed_domains
                self._set_state(OneClickState.ERROR, outcome.message)
                return outcome

        outcome = summarize(results)
        outcome.failed_domains = failed_domains
        self._set_state(outcome.state, outcome.message)
        return outcome

    def _run_step(
        self,
        key: StepKey,
        request: OneClickRequest,
    ) -> tuple[StepResult, tuple[str, ...]]:
        deps = self._deps

        try:
            if key is StepKey.CONFLICTS:
                ok, message = deps.check_conflicts()
                return StepResult(key, ok=ok, message=message), ()

            if key is StepKey.DPI:
                ok, message = deps.start_dpi()
                return StepResult(key, ok=ok, message=message), ()

            if key is StepKey.TELEGRAM_PROXY:
                # Не запущенный Telegram — не повод откатывать всё
                # включение: обход соединения работает и без него.
                # Поэтому шаг пропускается с объяснением, а не падает.
                ready, note = deps.check_telegram_ready()
                if not ready:
                    return (
                        StepResult(key, ok=True, message=note, skipped=True, note=note),
                        (),
                    )

                # Предупреждаем до того, как Telegram выпрыгнет поверх
                # работы со своим вопросом про прокси.
                if note:
                    self._set_state(OneClickState.PREPARING, note)

                ok, message = deps.start_telegram_proxy()
                return StepResult(key, ok=ok, message=message), ()

            if key is StepKey.HOSTS:
                # Бэкап обязателен: без него откат невозможен, а правка
                # hosts переживает удаление приложения.
                ok, message = deps.backup_hosts()
                if not ok:
                    return StepResult(key, ok=False, message=message or "Не удалось сохранить копию hosts"), ()
                ok, message = deps.apply_hosts(dict(request.hosts_entries or {}))
                return StepResult(key, ok=ok, message=message), ()

            if key is StepKey.DNS:
                integrity = deps.check_dns_integrity()
                change, reason = should_change_dns(list(integrity or []))
                if not change:
                    # Подмены нет — сеть не трогаем вообще.
                    return StepResult(key, ok=True, message=reason, skipped=True), ()
                ok, message = deps.apply_dns()
                return StepResult(key, ok=ok, message=message or reason), ()

            if key is StepKey.SELFCHECK:
                total, failed = deps.probe_domains()
                message = build_selfcheck_message(total=total, failed_domains=tuple(failed))
                # Недоступность сайтов — не ошибка запуска: winws работает,
                # просто стратегия не подошла. Состояние остаётся RUNNING,
                # а пользователь видит честный текст.
                return StepResult(key, ok=True, message=message), tuple(failed)

        except Exception as exc:
            return StepResult(key, ok=False, message=f"{type(exc).__name__}: {exc}"), ()

        return StepResult(key, ok=True, message="", skipped=True), ()

    def _rollback(self, results: list[StepResult]) -> None:
        deps = self._deps
        for key in build_rollback_plan(results):
            try:
                if key is StepKey.DPI:
                    deps.stop_dpi()
                elif key is StepKey.TELEGRAM_PROXY:
                    deps.stop_telegram_proxy()
                elif key is StepKey.HOSTS:
                    deps.restore_hosts()
                elif key is StepKey.DNS:
                    deps.restore_dns()
            except Exception:
                # Откат обязан пройти до конца: сбой одного шага не должен
                # оставлять систему в наполовину изменённом состоянии.
                continue

    # ──────────────────────────────────────────────────────────────────
    # Выключение
    # ──────────────────────────────────────────────────────────────────

    def disable(self) -> OneClickOutcome:
        results: list[StepResult] = []
        deps = self._deps

        for key in build_disable_plan():
            try:
                if key is StepKey.TELEGRAM_PROXY:
                    ok, message = deps.stop_telegram_proxy()
                elif key is StepKey.DPI:
                    ok, message = deps.stop_dpi()
                else:
                    continue
            except Exception as exc:
                ok, message = False, f"{type(exc).__name__}: {exc}"
            results.append(StepResult(key, ok=ok, message=message))

        failed = [r for r in results if not r.ok]
        if failed:
            outcome = OneClickOutcome(
                state=OneClickState.ERROR,
                results=results,
                message=failed[0].message or "Не удалось остановить",
            )
        else:
            outcome = OneClickOutcome(
                state=OneClickState.OFF,
                results=results,
                message="Выключено",
            )

        self._set_state(outcome.state, outcome.message)
        return outcome


__all__ = ["OneClickDeps", "OneClickRunner"]
