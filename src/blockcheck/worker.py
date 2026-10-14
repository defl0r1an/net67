"""Фоновый поток проверки BlockCheck.

Сам ничего не проверяет: запускает ``diagnostics.engine.run_blockcheck``,
пишет каждую строку отчёта в журнал ``blockcheck_run_*.log`` (его потом
забирает обращение в поддержку) и отдаёт странице готовый итог.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class BlockcheckWorker(QObject):
    """Проверка BlockCheck в QThread, которым владеет общий runtime страницы."""

    run_log_started = pyqtSignal(object)
    log_message = pyqtSignal(str)
    # Итог проверки (словарь из run_blockcheck), None — если её остановили,
    # {"failed": True, "error": …} — если проверка упала.
    finished = pyqtSignal(object)
    progress = pyqtSignal(str, int, int)
    partial = pyqtSignal(object)

    def __init__(
        self,
        scope: str = "main",
        user_domains: list[str] | None = None,
        *,
        start_run_log: Callable[[str, list[str]], object],
        append_run_log: Callable[[str | None, str], None],
        close_run_log: Callable[[str | None], None],
        load_geo_sites: Callable[[], object] | None = None,
        remember_run: Callable[[dict, str | None], dict] | None = None,
        save_report: Callable[[dict, str | None], str] | None = None,
        check_dns_servers: Callable[..., dict] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._scope = str(scope or "main")
        self._user_domains = list(user_domains or [])
        self._start_run_log = start_run_log
        self._append_run_log_action = append_run_log
        self._close_run_log_action = close_run_log
        self._load_geo_sites = load_geo_sites
        self._save_report = save_report
        self._remember_run = remember_run
        self._check_dns_servers = check_dns_servers
        self._lines: list[str] = []
        self._last_partial: dict | None = None
        self._cancelled = False
        self._running = False
        self._run_log_file = None

    def _geo_service_lookup(self):
        """Поиск «адрес → гео-сервис» из каталога hosts; без каталога — None."""
        if self._load_geo_sites is None:
            return None
        try:
            return self._load_geo_sites().service_for
        except Exception:
            logger.exception("Failed to load geo sites for blockcheck")
            return None

    def run(self):
        # Флаг «Стоп» здесь не сбрасывается: проверку могли остановить, пока
        # она ждала очереди фоновых задач. Обработчик создаётся на каждую
        # проверку заново.
        self._running = True
        report = None
        try:
            from diagnostics.engine import run_blockcheck

            log_state = self._start_run_log(self._scope, list(self._user_domains))
            self._run_log_file = log_state.path
            self.run_log_started.emit(log_state.path)
            if not log_state.created:
                logger.warning("Failed to create blockcheck run log")

            report = run_blockcheck(
                self._scope,
                user_domains=self._user_domains,
                emit=self._emit,
                should_stop=self.is_cancelled,
                geo_service_for=self._geo_service_lookup(),
                check_dns_servers=self._check_dns_servers,
                progress=self.progress.emit,
                partial=self._on_partial,
            )
            if isinstance(report, dict) and report.get("stopped"):
                self._save_unfinished(stopped=True)
                report = None
            if isinstance(report, dict) and not report.get("failed"):
                report["text"] = list(self._lines)
                self._remember(report)
        except Exception as e:
            logger.exception("BlockcheckWorker crashed")
            self._emit(f"❌ Проверка упала: {e}")
            self._save_unfinished(failed=True, error=str(e))
            report = {"failed": True, "error": str(e)}
        finally:
            try:
                self._close_run_log_action(self._run_log_file)
            except Exception:
                pass
            self._running = False
        self.finished.emit(report)

    def stop(self):
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def is_running(self) -> bool:
        return bool(self._running)

    def _emit(self, message: str) -> None:
        self._lines.append(str(message))
        try:
            self._append_run_log_action(self._run_log_file, message)
        except Exception:
            pass
        self.log_message.emit(message)

    def _on_partial(self, report: dict) -> None:
        self._last_partial = report
        self.partial.emit(report)

    def _remember(self, report: dict) -> None:
        """Записывает прогон в историю и дописывает, что изменилось с прошлого раза.

        Сбой записи не должен стоить человеку результата проверки.
        """
        if self._remember_run is None:
            return
        try:
            note = self._remember_run(report, self._run_log_file) or {}
        except Exception:
            logger.exception("Failed to remember blockcheck run")
            return
        report["json_file"] = str(note.get("json_file") or "")
        if report["json_file"]:
            self.run_log_started.emit(report["json_file"])
        report["history"] = [dict(run) for run in note.get("history") or () if isinstance(run, dict)]
        # Сравнение «с Zapret и без», изменения с прошлого раза и их строка уже лежат
        # в отчёте и в файле; здесь — только на экран.
        for line in note.get("lines") or ():
            self.log_message.emit(str(line))

    def _save_unfinished(self, **marks) -> None:
        # Уже измеренные факты нужны и после отмены; незавершённый прогон
        # не попадает в сравнение успешных проверок.
        if self._save_report is None or not self._run_log_file:
            return
        import os

        report = dict(self._last_partial or {"scope": self._scope})
        report.update(marks, text=list(self._lines))
        try:
            path = self._save_report(report, os.path.splitext(str(self._run_log_file))[0] + ".json")
            if path:
                self.run_log_started.emit(path)
        except Exception:
            logger.exception("Не удалось сохранить прерванную проверку")
