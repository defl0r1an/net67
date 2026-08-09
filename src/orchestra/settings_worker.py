from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from log.log import log


class OrchestraSettingSaveWorker(QThread):
    saved = pyqtSignal(int, str, object)
    failed = pyqtSignal(int, str, str)

    def __init__(
        self,
        request_id: int,
        *,
        key: str,
        value,
        runner=None,
        set_setting,
        parent=None,
    ):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._key = str(key or "").strip()
        self._value = value
        self._runner = runner
        self._set_setting = set_setting

    def run(self) -> None:
        try:
            self._set_setting(self._key, self._value, runner=self._runner)
        except Exception as exc:
            log(f"OrchestraSettingSaveWorker: не удалось сохранить {self._key}: {exc}", "ERROR")
            self.failed.emit(self._request_id, self._key, str(exc))
            return
        self.saved.emit(self._request_id, self._key, self._value)
