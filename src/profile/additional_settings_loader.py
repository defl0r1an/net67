from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


class AdditionalSettingsLoadWorker(QThread):
    loaded = pyqtSignal(int, dict)

    def __init__(self, request_id: int, state_loader, parent=None):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._state_loader = state_loader

    def run(self) -> None:
        state: dict = {}
        try:
            state = self._state_loader() or {}
        except Exception:
            state = {}
        self.loaded.emit(self._request_id, state)
