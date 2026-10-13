"""Поток команд по трубам: окно не выполняет сетевые и системные операции."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import threading

from PyQt6.QtCore import QObject, pyqtSignal


VERSION = "2.22.0"


def engine_directory() -> Path:
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.bin_dir / "antigravity"


class AntigravityController(QObject):
    received = pyqtSignal(dict)
    failed = pyqtSignal(str)
    busy_changed = pyqtSignal(bool, str)
    _output = pyqtSignal(int, bytes)
    _ended = pyqtSignal(int, int)
    _launch_failed = pyqtSignal(int, str)

    def __init__(self, parent=None, *, directory: Path | None = None):
        super().__init__(parent)
        self.directory = directory if directory is not None else engine_directory()
        self.process = None
        self._lock = threading.Lock()
        self._starting = False
        self._initializing = False
        self._request_sequence = 0
        self._active_request = None
        self._generation = 0
        self._output.connect(self._deliver_output)
        self._ended.connect(self._finished)
        self._launch_failed.connect(self._process_error)
        self._buffer = bytearray()
        self.busy = False
        self._closing = False

    def start(self) -> bool:
        if self._starting or (self.process is not None and self.process.poll() is None):
            return True
        executable = self.directory / "net67_antigravity.exe"
        if not executable.is_file() or not (self.directory / "ag_network.exe").is_file():
            self.failed.emit("Компоненты Antigravity отсутствуют. Переустановите net67.")
            return False
        self._buffer.clear()
        self._closing = False
        self._starting = True
        self._initializing = True
        self._active_request = None
        self._generation += 1
        generation = self._generation
        from log.log import log

        log("Antigravity: запуск контроллера для чтения состояния", "INFO")
        self._set_busy(True, "Проверяю установки и настройки…")
        threading.Thread(target=self._run, args=(generation, executable), name="antigravity-pipe", daemon=True).start()
        return True

    @property
    def active_request_id(self):
        return self._active_request

    def _run(self, generation: int, executable: Path) -> None:
        try:
            process = subprocess.Popen(
                [str(executable)], cwd=str(self.directory), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            self._starting = False
            try:
                self._launch_failed.emit(generation, "Не удалось запустить управление Antigravity. Проверьте файлы программы.")
            except RuntimeError:
                pass
            return
        with self._lock:
            self.process = process
            self._starting = False
            if self._closing:
                process.stdin.close()
        try:
            for line in iter(process.stdout.readline, b""):
                try:
                    self._output.emit(generation, line)
                except RuntimeError:
                    # Окно уже уничтожено; трубу всё равно дочитываем, иначе
                    # очередь упрётся в заполненный stdout и не завершится.
                    pass
        finally:
            process.stdout.close()
            code = process.wait()
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            with self._lock:
                if self.process is process:
                    self.process = None
            try:
                self._ended.emit(generation, code)
            except RuntimeError:
                pass

    def send(self, command: str, **values) -> bool:
        process = self.process
        if self.busy or process is None or process.poll() is not None or self._closing:
            return False
        self._request_sequence += 1
        request_id = self._request_sequence
        payload = {"command": command, "request_id": request_id, **values}
        try:
            with self._lock:
                process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                process.stdin.flush()
        except (OSError, ValueError):
            self._process_error(self._generation, "Управление Antigravity остановилось. Нажмите «Проверить».")
            return False
        if command not in {"report"}:
            from log.log import log

            # Только имя действия: адреса прокси и коды доступа в журнал не попадают.
            log(f"Antigravity: отправлена команда {command}", "INFO")
            self._active_request = request_id
            self._set_busy(True, "Выполняю…")
        return True

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.busy = bool(busy)
        self.busy_changed.emit(self.busy, message)

    def _deliver_output(self, generation: int, data: bytes) -> None:
        if generation == self._generation and not self._closing:
            self.feed_output(data)

    def feed_output(self, data: bytes) -> None:
        """JSON может быть разрезан трубой внутри русской буквы или строки."""
        self._buffer.extend(data)
        while b"\n" in self._buffer:
            line, _, rest = self._buffer.partition(b"\n")
            self._buffer = bytearray(rest)
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Старые функции движка ещё могут печатать строки журнала.
                if line.strip():
                    self.received.emit({"event": "log", "level": "Info", "message": line.decode("utf-8", "replace")})
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("event")
            if kind == "busy":
                message = event.get("message")
                if message is not None or self._active_request is None:
                    self._set_busy(message is not None, str(message or ""))
            elif kind == "completed" and event.get("request_id") == self._active_request:
                self._active_request = None
                self._set_busy(False)
            elif kind == "status" and self._initializing:
                self._initializing = False
                self._set_busy(False)
            elif kind == "error":
                self._active_request = None
                self._set_busy(False)
            self.received.emit(event)

    def _process_error(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._set_busy(False)
        if not self._closing:
            self.failed.emit(message)

    def _finished(self, generation: int, exit_code: int) -> None:
        if generation != self._generation:
            return
        self._set_busy(False)
        if not self._closing:
            from log.log import log

            log(f"Контроллер Antigravity завершился ({exit_code})", "WARNING")
            self.failed.emit("Управление Antigravity остановилось. Нажмите «Проверить», чтобы запустить его снова.")

    def stop(self) -> None:
        self._closing = True
        with self._lock:
            process = self.process
            if process is None or process.poll() is not None or process.stdin.closed:
                return
            try:
                process.stdin.write(b'{"command":"stop"}\n')
                process.stdin.flush()
            except OSError:
                pass
            process.stdin.close()
        # Popen не убивает дочерний процесс при уничтожении объекта:
        # контроллер досиживает очередь даже после закрытия net67. Служба
        # живёт отдельно; её выключает только соответствующий переключатель.
