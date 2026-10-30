"""Общий снимок прогресса для окна обновления и страницы «Серверы».

Часы принадлежат сценарию загрузки, а не видимости окна: скрытие диалога
не обнуляет скорость, и молчание сети не оставляет старый остаток времени.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.ui_texts import tr as tr_catalog

WAITING_SECONDS = 5.0
_SPEED_WINDOW_SECONDS = 4.0


def format_size_mb(value: int) -> str:
    return f"{max(0, int(value)) / (1024 * 1024):.1f}"


def format_speed(bytes_per_second: float) -> str:
    speed = max(0.0, float(bytes_per_second))
    if speed >= 1024 * 1024:
        return f"{speed / (1024 * 1024):.1f} МБ/с"
    if 0 < speed < 10 * 1024:
        return f"{speed / 1024:.1f} КБ/с"
    return f"{speed / 1024:.0f} КБ/с"


def format_eta(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    minutes, rest = divmod(total, 60)
    if minutes:
        return f"{minutes} мин {rest} сек" if rest else f"{minutes} мин"
    return f"{rest} сек"


class DownloadSpeed:
    """Короткое окно замеров не тащит медленный старт до конца загрузки."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._samples: list[tuple[float, int]] = []

    def add(self, done_bytes: int) -> None:
        now = self._clock()
        done = max(0, int(done_bytes))
        if self._samples and done < self._samples[-1][1]:
            self._samples.clear()
        if self._samples and now == self._samples[-1][0]:
            self._samples[-1] = (now, done)
        else:
            self._samples.append((now, done))
        while len(self._samples) > 2 and now - self._samples[0][0] > _SPEED_WINDOW_SECONDS:
            self._samples.pop(0)

    def bytes_per_second(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        (t0, b0), (t1, b1) = self._samples[0], self._samples[-1]
        return (b1 - b0) / (t1 - t0) if t1 > t0 and b1 >= b0 else 0.0

    def eta_seconds(self, done_bytes: int, total_bytes: int) -> float | None:
        speed = self.bytes_per_second()
        return max(0.0, (total_bytes - done_bytes) / speed) if speed > 0 and total_bytes > 0 else None


@dataclass(frozen=True, slots=True)
class DownloadProgressSnapshot:
    percent: int
    done_bytes: int
    total_bytes: int
    status: str
    waiting: bool
    speed: float | None
    eta_seconds: float | None


class DownloadProgress:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._speed = DownloadSpeed(clock)
        self._last_activity = clock()
        self._has_sample = False
        self._stage = ""
        self._status = "Готовим загрузку…"
        self._done = self._total = self._percent = 0

    def set_stage(self, stage: str, message: str) -> None:
        self._stage = stage
        self._status = str(message or "").strip()
        self._last_activity = self._clock()
        self._speed = DownloadSpeed(self._clock)
        self._has_sample = False

    def update(self, percent: int, done_bytes: int, total_bytes: int) -> None:
        done, total = max(int(done_bytes), 0), max(int(total_bytes), 0)
        if done != self._done:
            self._last_activity = self._clock()
            if self._stage == "download":
                self._status = "Скачивание обновления…"
        self._percent = max(0, min(int(percent), 100))
        self._done, self._total = done, total
        self._speed.add(done)
        self._has_sample = True

    def snapshot(self) -> DownloadProgressSnapshot:
        downloading = self._stage == "download" and (self._total <= 0 or self._done < self._total)
        waiting = downloading and self._clock() - self._last_activity >= WAITING_SECONDS
        if self._has_sample:
            self._speed.add(self._done)
        measured = self._speed.bytes_per_second()
        speed = measured if downloading and not waiting and measured > 0 else None
        eta = self._speed.eta_seconds(self._done, self._total) if speed else None
        return DownloadProgressSnapshot(
            percent=self._percent, done_bytes=self._done, total_bytes=self._total,
            status="Ждём ответа сервера…" if waiting else self._status,
            waiting=waiting, speed=speed, eta_seconds=eta,
        )


@dataclass(frozen=True, slots=True)
class DownloadProgressLabels:
    percent: str
    size: str
    speed: str
    eta: str


def progress_labels(snapshot: DownloadProgressSnapshot, *, language="ru") -> DownloadProgressLabels:
    tr = lambda key, default: tr_catalog(key, language=language, default=default)
    size = tr("page.servers.changelog.progress.downloaded_mb_template", "Загружено {done:.1f} / {total:.1f} МБ").format(
        done=snapshot.done_bytes / (1024 * 1024), total=snapshot.total_bytes / (1024 * 1024))
    speed = tr("page.servers.changelog.progress.speed_unknown", "Скорость: —")
    if snapshot.speed is not None:
        value = snapshot.speed / 1024
        if value >= 1024:
            speed = tr("page.servers.changelog.progress.speed_mb_template", "Скорость: {value:.1f} МБ/с").format(value=value / 1024)
        elif value >= 10:
            speed = tr("page.servers.changelog.progress.speed_kb_template", "Скорость: {value:.0f} КБ/с").format(value=value)
        else:
            speed = tr("page.servers.changelog.progress.speed_slow_template", "Скорость: {value:.1f} КБ/с").format(value=value)
    eta = tr("page.servers.changelog.progress.eta_unknown", "Осталось: —")
    if snapshot.eta_seconds is not None:
        if snapshot.eta_seconds < 60:
            eta = tr("page.servers.changelog.progress.eta_sec_template", "Осталось: {seconds} сек").format(seconds=int(snapshot.eta_seconds))
        else:
            eta = tr("page.servers.changelog.progress.eta_min_template", "Осталось: {minutes} мин").format(minutes=int(snapshot.eta_seconds / 60))
    return DownloadProgressLabels(percent=f"{snapshot.percent}%", size=size, speed=speed, eta=eta)
