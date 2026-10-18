"""Проверка адресов по запросу: сеть и запись hosts выполняются вне окна."""
from PyQt6.QtCore import QThread, pyqtSignal

class HostsAddressCheckWorker(QThread):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id: int, *, parent=None):
        super().__init__(parent)
        self._request_id = request_id
        self._cancelled = False

    def stop(self):
        self._cancelled = True

    def run(self):
        from hosts import commands
        try:
            from utils.probe_gate import Why, user_run

            # Пропуск шлюза проб: пока человек ждёт результата, плановая проверка не идёт.
            with user_run("hosts_addresses"):
                prepared = commands.check_addresses(
                    why=Why.USER, fresh=True, commit=False, should_stop=lambda: self._cancelled
                )
            if self._cancelled or prepared is None:
                return
            overlay, report = prepared
            from hosts import proxy_domains
            from hosts.hosts import HOSTS_EDIT_LOCK

            # Сеть уже проверена. Набор адресов и блок файла меняются
            # вместе, чтобы щелчок по другой плитке не вклинился между ними.
            with commands._CHECK_LOCK, HOSTS_EDIT_LOCK:
                if self._cancelled:
                    return
                if overlay is not None:
                    commands._OVERLAY_BEFORE_REFRESH = proxy_domains.get_engine_overlay()
                    proxy_domains.set_engine_overlay(overlay)
                result = commands.refresh_applied_selection()
                if not result.success:
                    raise OSError(result.message)
            snapshot = commands.load_page_snapshot()
            self.loaded.emit(self._request_id, (report, snapshot))
        except Exception as exc:
            message = str(exc)
            try:
                commands._settle_overlay_after_refresh(write_failed=True)
            except Exception as rollback_error:
                message += f". Не удалось восстановить прежний набор: {rollback_error}"
            self.failed.emit(self._request_id, message)
