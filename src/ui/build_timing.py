"""Пошаговый замер сборки интерфейса.

Зачем отдельный модуль. Метрики страниц показывают, что конструктор
главной страницы идёт 9,7 секунды при бюджете 200 мс, и почти всё это —
один вызов сборки секций настроек. Но тот же вызов на другой машине
занимает 91 мс. Значит дело не в коде, а в окружении, и угадывать, какой
именно виджет блокирует, бессмысленно: надо мерить там, где медленно.

Замер намеренно молчаливый. Логируется только шаг, который вышел за
порог, и итог, если превышен он. Иначе каждый запуск писал бы два
десятка строк «0 мс», и в следующий раз этот лог никто не стал бы читать.

Модуль не тянет ни Qt, ни настройки — его можно звать из любого места
сборки интерфейса и из тестов.
"""

from __future__ import annotations

import time
from contextlib import contextmanager


#: Порог, выше которого шаг попадает в лог.
#:
#: 120 мс — заметная глазу задержка и при этом заведомо выше обычного
#: разброса на построении десятка виджетов.
DEFAULT_STEP_THRESHOLD_MS = 120.0


def _default_log(message: str, level: str = "INFO") -> None:
    try:
        from log.log import log as _log

        _log(message, level)
    except Exception:
        print(f"[{level}] {message}")


class BuildStepTimer:
    """Считает время шагов сборки и сообщает о самых долгих."""

    __slots__ = ("_scope", "_threshold_ms", "_log", "_steps", "_started_at")

    def __init__(
        self,
        scope: str,
        *,
        threshold_ms: float = DEFAULT_STEP_THRESHOLD_MS,
        log_fn=None,
    ) -> None:
        self._scope = str(scope or "build")
        self._threshold_ms = float(threshold_ms)
        self._log = log_fn if callable(log_fn) else _default_log
        self._steps: list[tuple[str, float]] = []
        self._started_at = time.perf_counter()

    @contextmanager
    def step(self, name: str):
        """Мерит один шаг. Исключение внутри шага не проглатывается."""
        started_at = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            self._steps.append((str(name), elapsed_ms))
            if elapsed_ms >= self._threshold_ms:
                self._log(
                    f"⏱ {self._scope}: шаг «{name}» {elapsed_ms:.0f} мс",
                    "⚠ WARNING",
                )

    @property
    def steps(self) -> tuple[tuple[str, float], ...]:
        return tuple(self._steps)

    def slowest(self, limit: int = 3) -> tuple[tuple[str, float], ...]:
        return tuple(sorted(self._steps, key=lambda item: item[1], reverse=True)[: max(0, limit)])

    def finish(self) -> float:
        """Пишет итог, если сборка целиком вышла за порог. Возвращает мс."""
        total_ms = (time.perf_counter() - self._started_at) * 1000.0
        if total_ms >= self._threshold_ms and self._steps:
            worst = "; ".join(f"{name} {value:.0f} мс" for name, value in self.slowest(3))
            self._log(
                f"⏱ {self._scope}: всего {total_ms:.0f} мс, дольше всего — {worst}",
                "⚠ WARNING",
            )
        return total_ms


__all__ = ["DEFAULT_STEP_THRESHOLD_MS", "BuildStepTimer"]
