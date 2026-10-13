"""«Здоровье сети»: задержка до публичных серверов для трея.

Раз в полминуты в фоне пингует 1.1.1.1. Ответа нет — пробует TCP-соединение
с 1.1.1.1 и 8.8.8.8 на порт 443: в корпоративных сетях ICMP часто закрыт, и
по одному пингу трей писал «нет подключения» при живом интернете. «Нет
ответа» ставится, только когда не ответил ни один способ, и подпись называет
именно это, а не «нет интернета»: проверено два адреса, а не вся сеть.

Трей берёт ``NetworkPulseMonitor``. ``NetworkPulseWidget`` в окно пока не
встроен.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.accessibility import set_control_accessibility
from ui.fluent_widgets import set_tooltip


PING_HOST = "1.1.1.1"
#: Куда стучаться по TCP, если пинг не вернулся. Два разных владельца:
#: недоступность одного из них ещё не значит, что сети нет.
TCP_HOSTS: tuple[str, ...] = ("1.1.1.1", "8.8.8.8")
TCP_PORT = 443
TCP_TIMEOUT_S = 1.5

#: Подпись для случая, когда не ответил никто. Называет, что проверено.
NO_ANSWER_TEXT = "нет ответа от 1.1.1.1 и 8.8.8.8"


def _ping_ms(host: str) -> float | None:
    from utils.windows_icmp import ping_ipv4_host_winapi

    result = ping_ipv4_host_winapi(host, count=1, timeout_ms=1000)
    if result.ok and result.average_ms is not None:
        return float(result.average_ms)
    return None


def _tcp_connect_ms(host: str) -> float | None:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, TCP_PORT), timeout=TCP_TIMEOUT_S):
            pass
    except OSError:
        return None
    return (time.perf_counter() - started) * 1000.0


def measure_network_pulse(
    *,
    ping: Callable[[str], float | None] = _ping_ms,
    connect: Callable[[str], float | None] = _tcp_connect_ms,
) -> tuple[bool, float]:
    """(ответил ли кто-нибудь, задержка в мс).

    Задержка TCP — время рукопожатия: тот же один круг до сервера, что и у
    пинга, поэтому подпись в трее одна для обоих способов.
    """
    for probe, hosts in ((ping, (PING_HOST,)), (connect, TCP_HOSTS)):
        for host in hosts:
            try:
                latency = probe(host)
            except Exception:
                latency = None
            if latency is not None:
                return True, float(latency)
    return False, 0.0


_RUNNING_PULSE_WORKERS: set = set()


class _PingWorker(QThread):
    measured = pyqtSignal(bool, float)

    def run(self) -> None:
        try:
            ok, latency = measure_network_pulse()
        except Exception:
            ok, latency = False, 0.0
        self.measured.emit(ok, latency)


class NetworkPulseMonitor(QObject):
    """Фоновый мониторинг сетевого пульса (ICMP RTT) для трея и компонентов приложения."""

    statusChanged = pyqtSignal(bool, float)

    def __init__(self, parent=None, *, interval_ms: int = 30_000, initial_delay_ms: int = 1500) -> None:
        super().__init__(parent)
        self._connected: bool | None = None
        self._latency_ms: float = 0.0
        self._checking = False
        self._closed = False

        self._timer = QTimer(self)
        self._timer.setInterval(max(5000, int(interval_ms)))
        self._timer.timeout.connect(self.check_now)

        self._thread: QThread | None = None
        self._worker: _PingWorker | None = None

        if initial_delay_ms > 0:
            self._initial_timer = QTimer(self)
            self._initial_timer.setSingleShot(True)
            self._initial_timer.timeout.connect(self.check_now)
            self._initial_timer.start(int(initial_delay_ms))
        self._timer.start()

    @property
    def is_connected(self) -> bool:
        return bool(self._connected)

    @property
    def latency_ms(self) -> float:
        return self._latency_ms

    def check_now(self) -> None:
        if self._closed or self._checking:
            return
        self._checking = True

        worker = _PingWorker()
        worker.measured.connect(self._on_check_finished)
        worker.finished.connect(self._on_worker_finished)
        worker.finished.connect(worker.deleteLater)
        _RUNNING_PULSE_WORKERS.add(worker)
        worker.finished.connect(lambda w=worker: _RUNNING_PULSE_WORKERS.discard(w))
        self._thread = worker
        self._worker = worker
        worker.start()

    def _on_worker_finished(self) -> None:
        if self.sender() is self._worker:
            self._thread = None
            self._worker = None
            self._checking = False

    def _on_check_finished(self, ok: bool, latency: float) -> None:
        if self._closed:
            return
        self._connected = bool(ok)
        self._latency_ms = float(latency)
        self.statusChanged.emit(ok, latency)

    def cleanup(self) -> None:
        self._closed = True
        self._timer.stop()
        if hasattr(self, "_initial_timer"):
            self._initial_timer.stop()
        # Сокет имеет ограниченный таймаут. Поток доживает независимо от трея,
        # чтобы закрытие окна не уничтожало QThread посреди сетевого запроса.


class NetworkPulseWidget(QWidget):
    """Компактный виджет пульса сети."""

    networkStatusChanged = pyqtSignal(bool, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("net67NetworkPulse")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(26)

        self._connected: bool | None = None
        self._latency_ms: float = 0.0
        self._checking = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        self._dot = _DotWidget(self)
        layout.addWidget(self._dot)

        self._label = QLabel("...", self)
        try:
            from ui.theme import get_theme_tokens
            tokens = get_theme_tokens()
            fg_color = tokens.fg_muted
        except Exception:
            fg_color = "rgba(128, 128, 128, 0.70)"
        self._label.setStyleSheet(f"color: {fg_color}; font-size: 11px; font-weight: 500;")
        layout.addWidget(self._label)

        self._monitor = NetworkPulseMonitor(self)
        self._monitor.statusChanged.connect(self._on_check_finished)
        self._update_ui(True, 0.0, initial=True)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.check_now()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.check_now()
            return
        super().keyPressEvent(event)

    def check_now(self) -> None:
        self._monitor.check_now()

    def _on_check_finished(self, ok: bool, latency: float) -> None:
        self._checking = False
        self._connected = bool(ok)
        self._latency_ms = float(latency)
        self._update_ui(ok, latency)
        self.networkStatusChanged.emit(ok, latency)

    def _update_ui(self, ok: bool, latency: float, initial: bool = False) -> None:
        if initial:
            dot_color = QColor("#5fcdfe")
            self._label.setText("сеть...")
            tooltip = "Инициализация проверки связи с сетью..."
        elif ok:
            ms = max(1, int(round(latency)))
            if ms < 100:
                dot_color = QColor("#52c477")  # зелёный
            elif ms < 250:
                dot_color = QColor("#ffb300")  # жёлтый
            else:
                dot_color = QColor("#ff9800")  # оранжевый
            self._label.setText(f"{ms} мс")
            tooltip = f"Задержка до 1.1.1.1 или 8.8.8.8: {ms} мс.\nНажмите для повторной проверки."
        else:
            dot_color = QColor("#ff4d4f")  # красный
            self._label.setText("нет ответа")
            tooltip = f"Сеть: {NO_ANSWER_TEXT} — ни на пинг, ни на соединение.\nНажмите для повторной проверки."

        self._dot.set_color(dot_color)
        set_tooltip(self, tooltip)
        set_control_accessibility(
            self,
            name=f"Здоровье сети: {'доступна' if ok else 'нет связи'}, {self._label.text()}",
            description=tooltip,
        )
        self.update()

    def cleanup(self) -> None:
        self._monitor.cleanup()


class _DotWidget(QWidget):
    """Круглая цветная точка индикатора."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._color = QColor("#52c477")

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(0, 0, self.width(), self.height())
