"""Читает сохранённый отчёт вне потока окна."""
from PyQt6.QtCore import QThread, pyqtSignal


class DnsPastReportWorker(QThread):
    completed = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id, *, load_text, log_file, parent=None):
        super().__init__(parent)
        self._request_id = request_id
        self._load_text = load_text
        self._log_file = log_file

    def run(self):
        try:
            text = self._load_text(self._log_file)
        except Exception as exc:
            self.failed.emit(self._request_id, str(exc))
            return
        self.completed.emit(self._request_id, text)
