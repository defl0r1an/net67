"""Загрузка установщика с повторами и сохранением полученных частей.

Частичные файлы принадлежат одному выпуску; каталог и проверку SHA-256
задаёт конвейер. Сетевой слой не знает об окнах и состоянии приложения.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
from urllib3.exceptions import ProtocolError, ReadTimeoutError

from branding import APP_NAME
from log.log import log

from .network_hints import maybe_log_disable_dpi_for_update

NUM_SEGMENTS = 4
CHUNK_SIZE = 1024 * 1024
STREAM_CHUNK_SIZE = 64 * 1024
PROGRESS_INTERVAL_SECONDS = 0.25
CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 12
RETRY_DELAY_SECONDS = 2


class UpdatePipelineError(RuntimeError):
    """Понятная пользователю ошибка одной стадии конвейера."""


class UpdateCancelled(UpdatePipelineError):
    """Конвейер остановлен по запросу приложения."""


class UpdateIntegrityError(UpdatePipelineError):
    """Файл не прошёл проверку размера или SHA-256."""


class _RangeIgnored(UpdatePipelineError):
    pass


@dataclass(frozen=True, slots=True)
class DownloadSource:
    url: str
    verify_ssl: bool


class CancellationToken:
    """Отмена прерывает чтение сокета и ожидание перед повторной попыткой."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._interrupts: set[Callable[[], None]] = set()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            interrupts = tuple(self._interrupts)
        for interrupt in interrupts:
            self._interrupt(interrupt)

    @staticmethod
    def _interrupt(callback) -> None:
        try:
            callback()
        except (OSError, ValueError, RuntimeError):
            # Ответ мог закрыться между снимком списка и отменой.
            pass

    @contextmanager
    def interrupt_on_cancel(self, callback):
        with self._lock:
            self._interrupts.add(callback)
            cancelled = self._event.is_set()
        try:
            if cancelled:
                self._interrupt(callback)
            self.checkpoint()
            yield
        finally:
            with self._lock:
                self._interrupts.discard(callback)

    def checkpoint(self) -> None:
        if self.is_cancelled:
            raise UpdateCancelled("Обновление остановлено")

    def wait(self, seconds: float) -> None:
        self._event.wait(max(0.0, seconds))
        self.checkpoint()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()


class ThrottledProgress:
    """Не пропускает в Qt больше одного события прогресса за интервал."""

    def __init__(self, callback, *, interval_seconds=PROGRESS_INTERVAL_SECONDS, clock=time.monotonic):
        self._callback = callback
        self._interval_seconds = float(interval_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._last_emit_at = 0.0
        self._last_done = -1

    def update(self, done: int, total: int, *, force: bool = False) -> None:
        done, total = max(int(done), 0), max(int(total), 0)
        now = self._clock()
        with self._lock:
            completed = total > 0 and done >= total
            if not force and not completed and self._last_done >= 0 and now - self._last_emit_at < self._interval_seconds:
                return
            if done == self._last_done and not force:
                return
            self._last_emit_at, self._last_done = now, done
        percent = min(done * 100 // total, 100) if total > 0 else 0
        self._callback(percent, done, total)


def _make_session(verify_ssl: bool = True) -> requests.Session:
    import urllib3

    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": None, "https": None}
    session.headers.update({
        "User-Agent": f"{APP_NAME}-Updater/5.0",
        "Accept": "application/octet-stream",
        "Accept-Encoding": "identity",
    })
    if not verify_ssl:
        session.verify = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return session


def _supports_range(source: DownloadSource, token: CancellationToken, expected_size: int) -> tuple[bool, int]:
    token.checkpoint()
    try:
        with _make_session(source.verify_ssl) as session:
            with session.head(source.url, timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                              verify=source.verify_ssl, allow_redirects=True) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", 0) or 0)
                if expected_size > 0 and total > 0 and total != expected_size:
                    raise UpdateIntegrityError("Размер файла на сервере не совпадает с выпуском")
                return response.headers.get("Accept-Ranges", "").lower() == "bytes", total
    except requests.RequestException:
        # Некоторые серверы запрещают HEAD, хотя сам файл отдают по GET.
        token.checkpoint()
        return False, expected_size


def _validate_response(response, *, start: int, end: int, total: int, ranged: bool) -> bool:
    response.raise_for_status()
    encoding = response.headers.get("Content-Encoding", "identity").lower()
    if encoding not in {"", "identity"}:
        raise UpdateIntegrityError("Сервер изменил кодирование файла установщика")
    if ranged and response.status_code == 200:
        return False
    if ranged or response.status_code == 206:
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
        if response.status_code != 206 or not match or tuple(map(int, match.groups())) != (start, end, total):
            raise UpdateIntegrityError("Сервер вернул неверный диапазон файла")
    elif response.status_code != 200:
        raise UpdatePipelineError(f"Сервер вернул HTTP {response.status_code} вместо файла")
    length = int(response.headers.get("Content-Length", 0) or 0)
    if length and total > 0 and length != end - start + 1:
        raise UpdateIntegrityError("Размер ответа сервера не совпадает с запрошенной частью")
    return True


def _receive(response, path: Path, *, offset: int, length: int, token: CancellationToken,
             attempt: CancellationToken, on_bytes) -> None:
    with token.interrupt_on_cancel(response.raw.shutdown), attempt.interrupt_on_cancel(response.raw.shutdown):
        with path.open("ab" if offset else "wb") as output:
            written = offset
            while length <= 0 or written < length:
                token.checkpoint()
                attempt.checkpoint()
                # read1 отдаёт уже пришедшие байты: read/iter_content ждали бы
                # заполнения всего куска и скрывали медленную работающую связь.
                chunk = response.raw.read1(min(STREAM_CHUNK_SIZE, length - written) if length > 0 else STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                written += len(chunk)
                on_bytes(written)
            token.checkpoint()
            attempt.checkpoint()
            if length > 0 and written != length:
                raise UpdatePipelineError("Соединение прервалось до завершения загрузки")


def _existing_size(path: Path, limit: int) -> int:
    size = path.stat().st_size if path.exists() else 0
    if limit > 0 and size > limit:
        path.unlink()
        return 0
    return size


def _download_part(
    source: DownloadSource, path: Path, *, start: int, end: int, total: int,
    token: CancellationToken, attempt: CancellationToken,
    on_bytes: Callable[[int], None], segmented: bool,
) -> None:
    length = end - start + 1 if total > 0 else 0
    offset = _existing_size(path, length)
    if total <= 0:
        offset = 0
    on_bytes(offset)
    if length > 0 and offset == length:
        return
    ranged = segmented or offset > 0
    headers = {"Range": f"bytes={start + offset}-{end}"} if ranged else {}
    try:
        with _make_session(source.verify_ssl) as session:
            with session.get(source.url, stream=True, headers=headers,
                             timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS), verify=source.verify_ssl) as response:
                if ranged and response.status_code == 416:
                    path.unlink(missing_ok=True)
                    on_bytes(0)
                    raise _RangeIgnored("Сервер отклонил докачку файла")
                accepted = _validate_response(response, start=start + offset, end=end, total=total, ranged=ranged)
                if not accepted:
                    if segmented:
                        raise _RangeIgnored("Сервер не поддерживает загрузку частями")
                    # Range проигнорирован: это полный файл, дописывать его к
                    # старому префиксу нельзя. Используем уже открытый ответ.
                    _validate_response(response, start=0, end=end, total=total, ranged=False)
                    offset = 0
                    on_bytes(0)
                _receive(response, path, offset=offset, length=length, token=token, attempt=attempt, on_bytes=on_bytes)
    except UpdateIntegrityError:
        path.unlink(missing_ok=True)
        on_bytes(0)
        raise


def _download_segmented(
    source: DownloadSource, destination: Path, *, total: int,
    token: CancellationToken, progress: ThrottledProgress,
) -> None:
    segment_dir = Path(str(destination) + "_segments")
    segment_dir.mkdir(parents=True, exist_ok=True)
    segment_size = total // NUM_SEGMENTS
    paths = [segment_dir / f"segment_{index}" for index in range(NUM_SEGMENTS)]
    bounds = [(index * segment_size, total - 1 if index == NUM_SEGMENTS - 1 else (index + 1) * segment_size - 1)
              for index in range(NUM_SEGMENTS)]
    sizes = [_existing_size(path, end - start + 1) for path, (start, end) in zip(paths, bounds)]
    lock = threading.Lock()
    progress.update(sum(sizes), total, force=True)
    attempt = CancellationToken()

    def on_bytes(index, written):
        with lock:
            sizes[index] = written
            progress.update(sum(sizes), total)

    error = None
    with ThreadPoolExecutor(max_workers=NUM_SEGMENTS) as pool:
        futures = [pool.submit(_download_part, source, path, start=start, end=end, total=total,
                               token=token, attempt=attempt, segmented=True,
                               on_bytes=lambda written, index=index: on_bytes(index, written))
                   for index, (path, (start, end)) in enumerate(zip(paths, bounds))]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                if error is None:
                    error = exc
                    attempt.cancel()
    token.checkpoint()
    if error is not None:
        raise error
    with destination.open("wb") as output:
        for path in paths:
            token.checkpoint()
            with path.open("rb") as part:
                shutil.copyfileobj(part, output, length=CHUNK_SIZE)


def _error_text(error: Exception) -> str:
    if isinstance(error, (requests.Timeout, ReadTimeoutError)):
        return "Сервер долго не отвечает"
    if isinstance(error, requests.HTTPError):
        return f"Сервер вернул HTTP {error.response.status_code}"
    if isinstance(error, requests.ConnectionError):
        return "Не удалось соединиться с сервером обновлений"
    if isinstance(error, (ProtocolError, requests.exceptions.ChunkedEncodingError)):
        return "Соединение с сервером прервалось"
    if isinstance(error, UpdatePipelineError):
        return str(error)
    if isinstance(error, PermissionError):
        return "Нет доступа к файлу загрузки обновления"
    return "Не удалось скачать или сохранить файл обновления"


def download_source(source: DownloadSource, destination: str, *, token: CancellationToken,
                    progress: ThrottledProgress, max_retries: int = 3, expected_size: int = 0,
                    on_status: Callable[[str], None] | None = None) -> None:
    """Повторяет один источник; сохранённые части не теряются при обрыве."""
    path = Path(destination)
    attempts = max(int(max_retries), 1)
    if expected_size > 0 and path.exists() and path.stat().st_size == expected_size:
        token.checkpoint()
        progress.update(expected_size, expected_size, force=True)
        return
    last_error = None
    supports_range, head_size = _supports_range(source, token, expected_size)
    total = expected_size or head_size
    # Уже сохранённые сегменты подтверждают поддержку Range в прошлом.
    # Временный отказ HEAD не должен заставлять скачивать всё заново;
    # фактический диапазон каждого GET всё равно проверяется.
    saved_segments = Path(str(path) + "_segments").is_dir()
    segmented = (supports_range or saved_segments) and total > NUM_SEGMENTS * CHUNK_SIZE
    for attempt_index in range(attempts):
        token.checkpoint()
        try:
            if segmented:
                try:
                    _download_segmented(source, path, total=total, token=token, progress=progress)
                except _RangeIgnored:
                    segmented = False
            if not segmented:
                _download_part(source, path, start=0, end=total - 1, total=total, token=token,
                               attempt=CancellationToken(), segmented=False,
                               on_bytes=lambda written: progress.update(written, total))
            actual_size = path.stat().st_size
            if total > 0 and actual_size != total:
                raise UpdateIntegrityError("Размер загрузки не совпадает с размером выпуска")
            progress.update(actual_size, total or actual_size, force=True)
            return
        except UpdateCancelled:
            token.checkpoint()
            raise
        except Exception as exc:
            token.checkpoint()
            last_error = exc
            maybe_log_disable_dpi_for_update(exc, scope="download", level="🔄 DOWNLOAD")
            log(f"Попытка загрузки {attempt_index + 1}/{attempts}: {exc}", "WARNING")
            if attempt_index + 1 < attempts:
                if on_status:
                    on_status(f"Соединение прервалось. Повторяем загрузку ({attempt_index + 2} из {attempts})…")
                token.wait(min(RETRY_DELAY_SECONDS * (attempt_index + 1), 4))
                if on_status:
                    on_status("Продолжаем загрузку…")
    raise UpdatePipelineError(f"{_error_text(last_error)}. Нажмите «Повторить»")
