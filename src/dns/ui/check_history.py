"""Общая история вкладок DNS с фоновым чтением выбранного отчёта."""
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from dns.ui.history_rows import RowsView, history_groups
from diagnostics.history import format_time
from settings.schema import TAB_HISTORY_LIMIT
from ui.latest_worker_lane import LatestWorkerLane
from ui.log_report_dialog import show_log_report_dialog


class CheckHistory(QWidget):
    def __init__(self, *, dns_feature, kind: str, parent=None):
        super().__init__(parent)
        self._dns = dns_feature
        self._kind = kind
        self._runs = []
        self._closed = False
        self.rows = RowsView(self, icon='fa5s.history', clickable=True)
        self.rows.opened.connect(lambda _group, row: self._open(row))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.rows)
        self._lane = LatestWorkerLane(
            name=f'{kind}_history',
            create_worker=lambda request_id, run: self._dns.create_past_report_worker(request_id, kind=self._kind, log_file=str(run.get('log_file') or ''), parent=self),
            on_result=self._show_report,
            on_error=lambda run, _error: self._show_report(run, ''),
        )
        self.hide()

    def set_history(self, runs):
        self._runs = [dict(run) for run in runs or () if isinstance(run, dict)][-TAB_HISTORY_LIMIT:]
        groups = history_groups(self._runs)
        self.rows.show_groups(groups)
        self.setVisible(bool(groups))

    def append(self, entry):
        if isinstance(entry, dict):
            self.set_history([*self._runs, entry])

    def _open(self, row: int):
        if self._closed or not 0 <= row < len(self._runs):
            return
        self._lane.request(dict(self._runs[-1 - row]))

    def _show_report(self, run, text):
        if self._closed:
            return
        title = ' · '.join(part for part in (str(run.get('title') or ''), format_time(str(run.get('time') or ''))) if part)
        fallback = '\n'.join([str(run.get('headline') or ''), *map(str, run.get('problems') or ()), 'Полный отчёт недоступен.'])
        show_log_report_dialog(self.window(), title=title or 'Прошлая проверка', text=str(text or fallback))

    def cleanup(self):
        self._closed = True
        self._lane.close()
