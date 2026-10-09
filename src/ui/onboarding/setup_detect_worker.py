"""Поток проверки доступности сервисов в туре первого запуска.

Отдельный модуль по той же причине, что oneclick/ui/oneclick_worker.py:
модуль с наследником QThread считается фоновым и не может строить виджеты,
а карточки тура (ui/onboarding/setup_choices.py) — виджеты.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from log.log import log


class _DetectWorker(QThread):
    """Проверяет доступность сервисов. В потоке: DNS, TCP и HTTP занимают до минуты."""

    progress = pyqtSignal(str)
    finished_with = pyqtSignal(list)

    def __init__(self, urls, parent=None):
        super().__init__(parent)
        self._urls = list(urls or ())
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        from urllib.parse import urlparse

        results: list[tuple[str, bool, str]] = []
        try:
            from blockcheck.models import PreflightVerdict
            from blockcheck.preflight import check_one_domain

            for url in self._urls:
                if self._cancelled:
                    break
                domain = urlparse(url).netloc or url
                self.progress.emit(f"Проверяем {domain}…")
                result = check_one_domain(domain, cancelled=lambda: self._cancelled)
                ok = result.verdict is PreflightVerdict.PASSED
                dns = getattr(result, "dns_result", None)
                kind = "dns_timeout" if getattr(dns, "error_code", "") == "DNS_TIMEOUT" else ""
                results.append((domain, ok, str(result.verdict_detail or ""), kind))
        except Exception as exc:
            log(f"Проверка доступности в туре: {exc}", "WARNING")
        self.finished_with.emit(results)
