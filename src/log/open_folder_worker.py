from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from log.log import log


class LogsOpenFolderWorker(QThread):
    """Открывает папку логов вне UI-потока."""

    loaded = pyqtSignal(int, bool)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id: int, *, open_logs_folder, parent=None):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._open_logs_folder = open_logs_folder

    def run(self) -> None:
        try:
            self._open_logs_folder()
        except Exception as exc:
            log(f"LogsOpenFolderWorker: не удалось открыть папку логов: {exc}", "ERROR")
            self.failed.emit(self._request_id, str(exc))
            return
        self.loaded.emit(self._request_id, True)


__all__ = ["LogsOpenFolderWorker"]
