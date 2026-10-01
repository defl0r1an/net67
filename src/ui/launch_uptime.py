"""Сколько обход уже работает — одни часы на всю программу.

Время работы показывал только большой круг на главной, и считал он его
сам, с момента, когда сам стал «включён». Метка в заголовке теперь пишет
то же время, и два счётчика с разным началом разошлись бы на секунды:
круг улетает в метку, и «0:35» по дороге превращается в «0:41».

Поэтому начало отсчёта одно — момент, когда обход перешёл в «работает».
Ставит его тот, кто слушает состояние с самого запуска окна
(shell/launch_badge.py); круг и метка только читают. Страница с кругом
строится лениво, и круг, появившийся через пять минут после автозапуска,
покажет пять минут, а не ноль.
"""

from __future__ import annotations

import time

__all__ = ["clear", "ensure", "format_uptime", "since", "track_phase"]

_since: float | None = None


def since() -> float | None:
    """Момент (time.monotonic), с которого обход работает; None — не работает."""
    return _since


def ensure() -> float:
    """Начало отсчёта; ставит его сейчас, если часы ещё не идут."""
    global _since
    if _since is None:
        _since = time.monotonic()
    return _since


def clear() -> None:
    global _since
    _since = None


def track_phase(phase: str) -> None:
    """Часы идут ровно пока фаза — «работает».

    Перезапуск (остановка и новый пуск) — новый отсчёт: человеку важно,
    сколько работает нынешний обход, а не программа.
    """
    if str(phase or "").strip().lower() == "running":
        ensure()
    else:
        clear()


def format_uptime(seconds: float) -> str:
    """Время работы: «0:07», «12:40», «3:05:09».

    Секунды показываем всегда: без них первые минуты выглядят
    застывшими, и человек не понимает, идёт ли отсчёт.
    """
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
