"""Настоящий перебор стратегий для автоподбора.

Берём синхронный StrategyScanner, а не его Qt-обёртку: автоподбор идёт в
обычном потоке, без цикла событий, и сигналы там доставлять некому.

Из отчёта берём самую быструю из рабочих. Порядок в списке — это порядок
проверки, а не качество; сортировать по времени честнее.
"""

from __future__ import annotations

from log.log import log


def run_strategy_scan(
    target: str,
    protocol: str,
    *,
    shutdown_sync,
    mode: str = "quick",
) -> list[str]:
    """Ищет рабочую стратегию. Пустой список — не нашлось.

    shutdown_sync приходит из runtime-функции приложения и передаётся
    насквозь. Сканеру он нужен по существу: чтобы проверить стратегию, он
    останавливает работающий winws и запускает свой. Значит на время
    подбора защита прерывается — это цена перебора, а не недосмотр.
    """
    try:
        from blockcheck.strategy_scanner import StrategyScanner
    except Exception as exc:
        log(f"Автоподбор: сканер недоступен: {exc}", "⚠ WARNING")
        return []

    try:
        scanner = StrategyScanner(
            target=str(target or ""),
            mode=str(mode or "quick"),
            scan_protocol=str(protocol or "tcp_https"),
            shutdown_sync=shutdown_sync,
        )
        report = scanner.run()
    except Exception as exc:
        log(f"Автоподбор: перебор для {target} упал: {exc}", "⚠ WARNING")
        return []

    working = list(getattr(report, "working_strategies", ()) or ())
    if not working:
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
