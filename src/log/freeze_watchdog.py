"""Сторож зависаний главного потока.

Зачем он нужен. Приложение переставало отвечать при запуске BlockCheck,
подбора стратегии и диагностики, и в журнале об этом не оставалось
ничего: последняя запись, потом двадцать шесть минут тишины, потом
выход. Пустой журнал — худший вид отчёта об ошибке: видно, что беда
случилась, и не видно, где.

Обычный обработчик крашей здесь бесполезен. Он ловит падение, а
зависание падением не является: процесс жив, потоки на месте, просто
главный поток стоит в вызове, который не возвращается. Ни исключения,
ни сигнала — ловить нечего.

Устройство простое. В главном потоке тикает таймер и отмечает время
последнего удара. Отдельный поток-наблюдатель просыпается раз в секунду
и смотрит, давно ли был удар. Если дольше порога — значит главный поток
занят и очередь событий не обрабатывается: наблюдатель пишет стеки всех
потоков в файл. В стеке главного потока и будет та самая строка, на
которой всё встало.

Наблюдатель намеренно живёт в обычном потоке Python, а не в потоке Qt:
поток Qt со своей очередью событий встанет ровно там же, где и главный,
и промолчит вместе с ним.

Стоимость сторожа — один таймер на секунду и один спящий поток. Ложные
срабатывания отсекаются порогом: короткие задержки на тяжёлой отрисовке
в него не попадают, а повторные записи о том же зависании прижаты
паузой, иначе журнал заполнится одним и тем же стеком.
"""

from __future__ import annotations

import datetime
import faulthandler
import threading
import time
from pathlib import Path

#: Через сколько молчания главного потока считаем, что он завис.
#:
#: Десять секунд — с запасом. Отрисовка страницы укладывается в
#: доли секунды, самые тяжёлые шаги запуска — в две-три; порог ниже
#: давал бы записи о занятости, которая пройдёт сама.
FREEZE_THRESHOLD_SECONDS = 10.0

#: Как часто наблюдатель просыпается.
WATCH_INTERVAL_SECONDS = 1.0

#: Сколько ждать, прежде чем записать следующий стек того же зависания.
#:
#: Без паузы наблюдатель писал бы стек каждую секунду, пока длится
#: зависание, и файл превращался бы в тысячу одинаковых копий.
REPEAT_DUMP_SECONDS = 30.0

#: Как часто главный поток отмечается живым.
HEARTBEAT_INTERVAL_MS = 1000

_state_lock = threading.Lock()
_last_heartbeat = 0.0
_installed = False
_dump_file = None


def _touch_heartbeat() -> None:
    global _last_heartbeat
    with _state_lock:
        _last_heartbeat = time.monotonic()


def _seconds_since_heartbeat() -> float:
    with _state_lock:
        last = _last_heartbeat
    if not last:
        return 0.0
    return time.monotonic() - last


def _dump_stacks(stalled_for: float) -> None:
    """Пишет стеки всех потоков в файл сторожа."""
    if _dump_file is None:
        return
    try:
        _dump_file.write(f"\n{'=' * 60}\n")
        _dump_file.write(f"Главный поток не отвечает {stalled_for:.0f} с\n")
        _dump_file.write(f"Время: {datetime.datetime.now()}\n")
        _dump_file.write(f"{'=' * 60}\n")
        _dump_file.flush()
        # dump_traceback безопасно звать из чужого потока: он читает
        # состояние интерпретатора, а не ждёт главный поток.
        faulthandler.dump_traceback(file=_dump_file, all_threads=True)
        _dump_file.write("\n")
        _dump_file.flush()
    except Exception:
        # Сторож не имеет права уронить приложение, которое стережёт.
        pass


def _watch_loop() -> None:
    last_dump = 0.0
    reported = False

    while True:
        time.sleep(WATCH_INTERVAL_SECONDS)

        stalled_for = _seconds_since_heartbeat()

        if stalled_for < FREEZE_THRESHOLD_SECONDS:
            if reported:
                _log("Главный поток снова отвечает")
                reported = False
            continue

        now = time.monotonic()
        if last_dump and (now - last_dump) < REPEAT_DUMP_SECONDS:
            continue

        last_dump = now
        reported = True
        _dump_stacks(stalled_for)
        _log(
            f"Главный поток не отвечает {stalled_for:.0f} с — стеки записаны в freeze.log",
            level="WARNING",
        )


def _log(message: str, *, level: str = "INFO") -> None:
    try:
        from log.log import log

        log(message, level)
    except Exception:
        pass


def install_freeze_watchdog(app, *, crash_folder: Path | str | None = None) -> bool:
    """Заводит сторож. Возвращает, удалось ли.

    `app` нужен как хозяин таймера: таймер живёт в главном потоке и
    гибнет вместе с приложением.
    """
    global _installed, _dump_file

    if _installed:
        return True

    try:
        from PyQt6.QtCore import QTimer
    except Exception:
        return False

    try:
        if crash_folder is None:
            from log.crash_handler import _get_crash_logs_folder

            crash_folder = _get_crash_logs_folder()

        folder = Path(crash_folder)
        folder.mkdir(parents=True, exist_ok=True)
        _dump_file = open(folder / "freeze.log", "a", encoding="utf-8")
    except Exception:
        _dump_file = None

    _touch_heartbeat()

    timer = QTimer(app)
    timer.setInterval(HEARTBEAT_INTERVAL_MS)
    timer.timeout.connect(_touch_heartbeat)
    timer.start()
    # Ссылка на таймер живёт в приложении — хозяин задан явно, поэтому
    # сборщик мусора его не унесёт.
    app._freeze_watchdog_timer = timer

    watcher = threading.Thread(
        target=_watch_loop,
        name="freeze-watchdog",
        daemon=True,
    )
    watcher.start()

    _installed = True
    return True


__all__ = [
    "FREEZE_THRESHOLD_SECONDS",
    "install_freeze_watchdog",
]
