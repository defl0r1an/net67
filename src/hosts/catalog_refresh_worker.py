from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from log.log import log


class HostsCatalogRefreshWorker(QThread):
    """Проверяет изменение hosts-каталога вне UI-потока."""

    loaded = pyqtSignal(int, str, object)
    failed = pyqtSignal(int, str, str)

    def __init__(self, request_id: int, trigger: str, *, get_catalog_signature, parent=None):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._trigger = str(trigger or "")
        self._get_catalog_signature = get_catalog_signature

    def run(self) -> None:
        try:
            signature = self._get_catalog_signature()
        except Exception as exc:
            log(f"HostsCatalogRefreshWorker: не удалось проверить каталог hosts: {exc}", "ERROR")
            self.failed.emit(self._request_id, self._trigger, str(exc))
            return
        self.loaded.emit(self._request_id, self._trigger, signature)


__all__ = ["HostsCatalogRefreshWorker"]
