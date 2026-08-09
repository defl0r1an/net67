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

from PyQt6.QtCore import QThread, pyqtSignal


class VpnCallWorker(QThread):
    """Выполняет один вызов вне UI-потока.

    Результат отдаётся как есть: разбирать его — дело страницы. Ошибку
    не проглатываем, а передаём текстом, иначе кнопка так и останется
    выключенной, а пользователь не поймёт, что произошло.
    """

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, call: Callable[[], object], parent=None):
        super().__init__(parent)
        self._call = call

    def run(self) -> None:
        try:
            result = self._call()
        except Exception as exc:  # noqa: BLE001 — текст уходит в UI
            self.failed.emit(str(exc))
            return
        self.done.emit(result)


__all__ = ["VpnCallWorker"]
