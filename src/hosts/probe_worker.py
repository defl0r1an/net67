from __future__ import annotations

import threading
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from log.log import log


class HostsProfileProbeWorker(QThread):
    """Проверяет DNS-профили одного сервиса вне UI-потока.

    Отдельный класс, а не общий HostsCallWorker: проверка идёт десять с
    лишним секунд, и без счётчика «проверено N из M» плитка выглядела бы
    зависшей. Остановить её тоже надо уметь — страницу могут закрыть.
    """

    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)
    progress = pyqtSignal(int, int, int)

    def __init__(self, request_id: int, call: Callable[..., object], parent=None):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._call = call
        self._cancelled = threading.Event()

    def stop(self) -> None:
        """Зовёт OneShotWorkerRuntime.stop(): идущие соединения доживают свой
        таймаут, новые не начинаются."""
        self._cancelled.set()

    def run(self) -> None:
        try:
            result = self._call(
                progress=lambda done, total: self.progress.emit(self._request_id, int(done), int(total)),
                cancelled=self._cancelled.is_set,
            )
        except Exception as exc:
            log(f"Hosts (probe): {exc}", "ERROR")
            self.failed.emit(self._request_id, str(exc))
            return
        if self._cancelled.is_set():
            return
        self.loaded.emit(self._request_id, result)


__all__ = ["HostsProfileProbeWorker"]
