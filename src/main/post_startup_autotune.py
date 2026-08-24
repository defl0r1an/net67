"""Запуск автоподбора после старта приложения.

Проверяет YouTube, Discord и Rutracker, и если какой-то не открывается
даже с включённым обходом — ищет рабочую стратегию перебором и кладёт её
в профиль сайта и в общий профиль по адресам.

Задержка не косметическая. Проверять доступность до того, как поднялся
движок, — значит объявить недоступным всё и запустить перебор впустую на
каждой машине. Автозапуск DPI отрабатывает в первые секунды, поэтому
ждём заметно дольше него.

Перебор идёт минутами и на время проверки каждой стратегии останавливает
работающий winws — это цена метода, а не недосмотр. Поэтому шаг не
включён по умолчанию: его включают осознанно.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer

from log.log import log
from main.post_startup_gate import is_startup_host_alive


#: Когда начинать. Движку нужно успеть подняться, иначе проверка
#: измерит состояние «обхода нет» и подбор запустится всегда.
AUTOTUNE_DELAY_MS = 25_000


def is_autotune_enabled() -> bool:
    """Включён ли автоподбор.

    По умолчанию выключен: подбор занимает минуты и прерывает обход на
    время проверки каждой стратегии. Такое нельзя включать за человека.
    """
    try:
        from settings.store import get_autotune_enabled

        return bool(get_autotune_enabled())
    except Exception:
        return False


def install_autotune(
    startup_host,
    *,
    features,
    set_status=None,
    delay_ms: int = AUTOTUNE_DELAY_MS,
) -> None:
    def _start() -> None:
        if not is_startup_host_alive(startup_host):
            return
        if not is_autotune_enabled():
            return

        try:
            from autotune.runtime import run_in_background
            from autotune.scan import run_strategy_scan

            presets_feature = features.presets
            shutdown_sync = features.runtime.shutdown_sync

            def _scan(target: str, protocol: str) -> list[str]:
                return run_strategy_scan(target, protocol, shutdown_sync=shutdown_sync)

            def _report(text: str) -> None:
                if callable(set_status):
                    try:
                        set_status(f"Автоподбор: {text}")
                    except Exception:
                        pass

            run_in_background(
                presets_feature=presets_feature,
                scan_runner=_scan,
                report=_report,
            )
        except Exception as exc:
            # Автоподбор — удобство, а не обязательная часть запуска.
            log(f"Автоподбор не запустился: {exc}", "⚠ WARNING")

    QTimer.singleShot(int(delay_ms), _start)


__all__ = ["AUTOTUNE_DELAY_MS", "install_autotune", "is_autotune_enabled"]
