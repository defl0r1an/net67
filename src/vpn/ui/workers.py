"""Фоновые операции страницы VPN.

Все три действия страницы — поднять туннель, узнать состояние службы и
проверить сервер — уходят в системные вызовы с большими таймаутами:

* connect()   → amneziawg.exe /installtunnelservice, timeout 30 с
* get_status()→ awg.exe show, timeout 10 с
* check_server() → три ICMP-пакета и TCP-проба, до 10 с

Выполнялись они прямо в UI-потоке, поэтому окно намертво зависало на всё
это время: и при подключении, и при проверке, и даже при простом
открытии страницы — состояние службы запрашивалось в _update_details().
"""

from __future__ import annotations

from typing import Callable

import weakref

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, QThread, pyqtSignal, pyqtSlot


# Поток переживает удаление страницы. Иначе закрытие окна во время системного
# вызова удаляет работающий QThread вместе с родителем и завершает приложение.
_LIVE_JOBS = set()


class VpnJob(QObject):
    """Доставляет даже лямбда-обработчики в поток окна, пока страница жива."""

    def __init__(self, page, attr, call, on_done, on_failed, *, on_progress=None):
        super().__init__()
        self.page = weakref.ref(page)
        self.attr = attr
        self.on_done = on_done
        self.on_failed = on_failed
        self.on_progress = on_progress
        self.worker = VpnCallWorker(call, with_progress=on_progress is not None)
        self.worker.done.connect(self.deliver)
        self.worker.failed.connect(self.fail)
        if on_progress is not None:
            self.worker.progress.connect(self.deliver_progress)
        self.worker.finished.connect(self.finish)
        self.worker._vpn_job = self
        _LIVE_JOBS.add(self)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def _page(self):
        page = self.page()
        return page if page is not None and not sip.isdeleted(page) and not getattr(page, "_closing", False) else None

    @pyqtSlot(object)
    def deliver(self, result):
        if self._page() is not None and self.on_done is not None:
            self.on_done(result)

    @pyqtSlot(str)
    def fail(self, message):
        if self._page() is not None and self.on_failed is not None:
            self.on_failed(message)

    @pyqtSlot(object)
    def deliver_progress(self, result):
        if self._page() is not None and self.on_progress is not None:
            self.on_progress(result)

    def detach(self):
        self.on_done = self.on_failed = self.on_progress = None
        self.page = lambda: None
        self.worker.requestInterruption()

    @pyqtSlot()
    def shutdown(self):
        # При выходе системный вызов заканчивается до удаления Qt runtime.
        # Обычное закрытие страницы не ждёт и только отсоединяет обработчики.
        self.detach()
        self.worker.wait()

    @pyqtSlot()
    def finish(self):
        page = self._page()
        if page is not None and getattr(page, self.attr, None) is self.worker:
            setattr(page, self.attr, None)
        self.detach()
        self.worker.deleteLater()
        _LIVE_JOBS.discard(self)
        self.deleteLater()


class VpnCallWorker(QThread):
    """Выполняет один вызов вне UI-потока.

    Результат отдаётся как есть: разбирать его — дело страницы. Ошибку
    не проглатываем, а передаём текстом, иначе кнопка так и останется
    выключенной, а пользователь не поймёт, что произошло.
    """

    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(object)

    def __init__(self, call: Callable[..., object], parent=None, *, with_progress=False):
        super().__init__(parent)
        self._call = call
        self._with_progress = with_progress

    def run(self) -> None:
        try:
            result = self._call(self.progress.emit) if self._with_progress else self._call()
        except Exception as exc:  # noqa: BLE001 — текст уходит в UI
            self.failed.emit(str(exc))
            return
        self.done.emit(result)


__all__ = ["VpnCallWorker"]
