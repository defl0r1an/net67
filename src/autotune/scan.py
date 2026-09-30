"""Настоящий перебор стратегий для автоподбора.

Раньше здесь стоял синхронный StrategyScanner. Исходный проект удалил его,
когда переписал подбор с нуля (blockcheck.strategy_search): старый давал
ложные «работает» и «не работает». Автоподбор перешёл на тот же движок,
что и вкладка «Подбор стратегии», — иначе он импортом падал бы на первом
же запуске и молча не делал ничего.

Движок блокирующий и событий Qt не требует: автоподбор идёт в обычном
потоке, события ему отдаёт тихий приёмник ниже.

Из отчёта берём самую быструю из рабочих. Порядок в списке — это порядок
проверки, а не качество; сортировать по времени честнее.
"""

from __future__ import annotations

from log.log import log


class _QuietEvents:
    """Приёмник событий движка без интерфейса: всё — в журнал."""

    def log(self, message: str) -> None:
        log(f"Автоподбор: {message}", "DEBUG")

    def phase(self, text: str) -> None:
        log(f"Автоподбор: {text}", "DEBUG")

    def strategy_started(self, name: str, index: int, total: int, args: str = "") -> None:
        _ = (args,)
        log(f"Автоподбор: стратегия {index}/{total} — {name}", "DEBUG")

    def stage(self, step: str, status: str, text: str = "") -> None:
        _ = (step, status, text)

    def strategy_result(self, result) -> None:
        _ = (result,)

    def ask_continue(self, reason: str) -> bool:
        # Движок спрашивает, когда сайт открывается и без обхода. Автоподбору
        # в этом случае подбирать нечего: человек ничего не заметит, а
        # перебор на полчаса оставил бы его без защиты.
        log(f"Автоподбор: перебор не нужен — {reason}", "INFO")
        return False

    def is_cancelled(self) -> bool:
        return False


def _load_fakes_catalog():
    from fakes.public import load_fakes_catalog

    return load_fakes_catalog()


def run_strategy_scan(
    target: str,
    protocol: str,
    *,
    shutdown_sync,
    mode: str = "quick",
) -> list[str]:
    """Ищет рабочую стратегию. Пустой список — не нашлось.

    shutdown_sync приходит из runtime-функции приложения и передаётся
    насквозь. Движку он нужен по существу: чтобы проверить стратегию, он
    останавливает работающий winws и запускает свой. Значит на время
    подбора защита прерывается — это цена перебора, а не недосмотр.
    """
    try:
        from blockcheck.strategy_search.engine import SearchRequest, run_strategy_search
        from blockcheck.strategy_search.environment import RealEnvironment
    except Exception as exc:
        log(f"Автоподбор: движок подбора недоступен: {exc}", "⚠ WARNING")
        return []

    try:
        env = RealEnvironment(
            shutdown_sync=shutdown_sync,
            load_fakes_catalog=_load_fakes_catalog,
            log=lambda message: log(f"Автоподбор: {message}", "DEBUG"),
        )
        request = SearchRequest(
            target=str(target or ""),
            scan_protocol=str(protocol or "tcp_https"),
            mode=str(mode or "quick"),
        )
        report = run_strategy_search(request, env=env, events=_QuietEvents())
    except Exception as exc:
        log(f"Автоподбор: перебор для {target} упал: {exc}", "⚠ WARNING")
        return []

    working = list(getattr(report, "working_strategies", ()) or ())
    if not working:
        fatal = str(getattr(report, "fatal_error", "") or "")
        if fatal:
            log(f"Автоподбор: для {target} перебор остановлен: {fatal}", "⚠ WARNING")
        return []

    best = min(working, key=lambda item: float(getattr(item, "time_ms", 0) or 0) or 1e9)
    args = str(getattr(best, "strategy_args", "") or "").strip()
    if not args:
        return []

    log(
        f"Автоподбор: для {target} подошла «{getattr(best, 'strategy_name', '')}»"
        f" ({getattr(best, 'time_ms', 0):.0f} мс)",
        "INFO",
    )
    return [line for line in args.splitlines() if line.strip()] or [args]


__all__ = ["run_strategy_scan"]
