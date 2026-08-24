"""Нативный мониторинг папки пресетов через ReadDirectoryChangesW.

Один overlapped-хэндл на каталог даёт точечные события «файл X добавлен /
удалён / переименован / изменён» (включая content-only записи), поэтому не
нужно держать отдельный watch на каждый файл и перечитывать весь список.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

FILE_ACTION_ADDED = 1
FILE_ACTION_REMOVED = 2
FILE_ACTION_MODIFIED = 3
FILE_ACTION_RENAMED_OLD_NAME = 4
FILE_ACTION_RENAMED_NEW_NAME = 5

_FILE_LIST_DIRECTORY = 0x0001
_FILE_SHARE_ALL = 0x1 | 0x2 | 0x4
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OVERLAPPED = 0x40000000

_FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
_FILE_NOTIFY_CHANGE_SIZE = 0x00000008
_FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010
_FILE_NOTIFY_CHANGE_CREATION = 0x00000040
_NOTIFY_FILTER = (
    _FILE_NOTIFY_CHANGE_FILE_NAME
    | _FILE_NOTIFY_CHANGE_SIZE
    | _FILE_NOTIFY_CHANGE_LAST_WRITE
    | _FILE_NOTIFY_CHANGE_CREATION
)

_WAIT_OBJECT_0 = 0
_WAIT_FAILED = 0xFFFFFFFF
_INFINITE = 0xFFFFFFFF
_ERROR_NOTIFY_ENUM_DIR = 1022
_ERROR_OPERATION_ABORTED = 995

_EVENT_BUFFER_SIZE = 64 * 1024


def parse_file_notify_information(buffer: bytes) -> list[tuple[int, str]]:
    """Разбирает буфер FILE_NOTIFY_INFORMATION в список (action, имя файла).

    Структура записи: DWORD NextEntryOffset, DWORD Action,
    DWORD FileNameLength (в байтах), WCHAR FileName[] (UTF-16-LE, без NUL).
    """
    events: list[tuple[int, str]] = []
    data = bytes(buffer or b"")
    offset = 0
    total = len(data)
    while offset + 12 <= total:
        next_entry_offset = int.from_bytes(data[offset:offset + 4], "little")
        action = int.from_bytes(data[offset + 4:offset + 8], "little")
        name_length = int.from_bytes(data[offset + 8:offset + 12], "little")
        name_start = offset + 12
        name_end = name_start + name_length
        if name_length < 0 or name_end > total:
            break
        try:
            name = data[name_start:name_end].decode("utf-16-le", errors="replace")
        except Exception:
            name = ""
        if name:
            events.append((int(action), name))
        if next_entry_offset <= 0:
            break
        offset += next_entry_offset
    return events


class _Overlapped(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", ctypes.c_uint32),
        ("OffsetHigh", ctypes.c_uint32),
        ("hEvent", ctypes.c_void_p),
    ]


_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def _bind_kernel32():
    """Загружает kernel32 с явными прототипами: без restype=c_void_p 64-битные
    хэндлы усекаются до c_int и INVALID_HANDLE_VALUE не распознаётся."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    c_void_p = ctypes.c_void_p
    c_uint32 = ctypes.c_uint32
    c_int = ctypes.c_int

    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p, c_uint32, c_uint32, c_void_p, c_uint32, c_uint32, c_void_p,
    ]
    kernel32.CreateFileW.restype = c_void_p
    kernel32.CreateEventW.argtypes = [c_void_p, c_int, c_int, ctypes.c_wchar_p]
    kernel32.CreateEventW.restype = c_void_p
    kernel32.SetEvent.argtypes = [c_void_p]
    kernel32.ResetEvent.argtypes = [c_void_p]
    kernel32.CloseHandle.argtypes = [c_void_p]
    kernel32.ReadDirectoryChangesW.argtypes = [
        c_void_p, c_void_p, c_uint32, c_int, c_uint32,
        ctypes.POINTER(c_uint32), c_void_p, c_void_p,
    ]
    kernel32.WaitForMultipleObjects.argtypes = [c_uint32, ctypes.POINTER(c_void_p), c_int, c_uint32]
    kernel32.WaitForMultipleObjects.restype = c_uint32
    kernel32.GetOverlappedResult.argtypes = [c_void_p, c_void_p, ctypes.POINTER(c_uint32), c_int]
    kernel32.CancelIoEx.argtypes = [c_void_p, c_void_p]
    return kernel32


class NativePresetsDirWatcher(QThread):
    """Поток, слушающий изменения каталога пресетов через WinAPI.

    Сигналы:
      - events(list[(action, file_name)]) — точечные изменения;
      - overflowed() — буфер событий переполнен, нужен полный rescan;
      - failed(str) — мониторинг умер, нужен fallback.
    """

    events = pyqtSignal(list)
    overflowed = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, directory, parent=None) -> None:
        super().__init__(parent)
        self._directory = str(Path(directory))
        self._kernel32 = None
        self._dir_handle = None
        self._stop_event = None
        self._io_event = None

    def start_watching(self) -> bool:
        """Открывает ресурсы синхронно (для мгновенного fallback) и стартует поток."""
        if os.name != "nt":
            return False
        try:
            kernel32 = _bind_kernel32()
            dir_handle = kernel32.CreateFileW(
                self._directory,
                _FILE_LIST_DIRECTORY,
                _FILE_SHARE_ALL,
                None,
                _OPEN_EXISTING,
                _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OVERLAPPED,
                None,
            )
            if not dir_handle or dir_handle == _INVALID_HANDLE_VALUE:
                return False
            stop_event = kernel32.CreateEventW(None, True, False, None)
            io_event = kernel32.CreateEventW(None, True, False, None)
            if not stop_event or not io_event:
                kernel32.CloseHandle(dir_handle)
                if stop_event:
                    kernel32.CloseHandle(stop_event)
                if io_event:
                    kernel32.CloseHandle(io_event)
                return False
        except Exception:
            return False

        self._kernel32 = kernel32
        self._dir_handle = dir_handle
        self._stop_event = stop_event
        self._io_event = io_event
        self.start()
        return True

    def stop_watching(self, wait_ms: int = 2000) -> None:
        kernel32 = self._kernel32
        stop_event = self._stop_event
        if kernel32 is not None and stop_event:
            try:
                kernel32.SetEvent(stop_event)
            except Exception:
                pass
        try:
            self.wait(int(wait_ms))
        except Exception:
            pass

    def run(self) -> None:  # pragma: no cover - системный цикл, крутится в потоке
        kernel32 = self._kernel32
        dir_handle = self._dir_handle
        stop_event = self._stop_event
        io_event = self._io_event
        if kernel32 is None or not dir_handle or not stop_event or not io_event:
            self.failed.emit("native watcher is not initialized")
            return

        buffer = ctypes.create_string_buffer(_EVENT_BUFFER_SIZE)
        bytes_returned = ctypes.c_uint32(0)
        wait_handles = (ctypes.c_void_p * 2)(stop_event, io_event)

        try:
            while True:
                kernel32.ResetEvent(io_event)
                overlapped = _Overlapped()
                overlapped.hEvent = io_event
                started = kernel32.ReadDirectoryChangesW(
                    dir_handle,
                    buffer,
                    _EVENT_BUFFER_SIZE,
                    False,
                    _NOTIFY_FILTER,
                    None,
                    ctypes.byref(overlapped),
                    None,
                )
                if not started:
                    self.failed.emit(f"ReadDirectoryChangesW failed: {ctypes.get_last_error()}")
                    return

                wait_result = kernel32.WaitForMultipleObjects(2, wait_handles, False, _INFINITE)
                if wait_result == _WAIT_OBJECT_0:
                    # stop_event: гасим незавершённый запрос и выходим.
                    kernel32.CancelIoEx(dir_handle, ctypes.byref(overlapped))
                    kernel32.GetOverlappedResult(dir_handle, ctypes.byref(overlapped), ctypes.byref(bytes_returned), True)
                    return
                if wait_result != _WAIT_OBJECT_0 + 1:
                    self.failed.emit(f"WaitForMultipleObjects failed: {ctypes.get_last_error()}")
                    return

                ok = kernel32.GetOverlappedResult(
                    dir_handle,
                    ctypes.byref(overlapped),
                    ctypes.byref(bytes_returned),
                    False,
                )
                if not ok:
                    error = ctypes.get_last_error()
                    if error == _ERROR_OPERATION_ABORTED:
                        return
                    if error == _ERROR_NOTIFY_ENUM_DIR:
                        self.overflowed.emit()
                        continue
                    self.failed.emit(f"GetOverlappedResult failed: {error}")
                    return

                if int(bytes_returned.value) <= 0:
                    # По контракту WinAPI нулевой ответ означает переполнение
                    # внутреннего буфера: часть событий потеряна.
                    self.overflowed.emit()
                    continue

                parsed = parse_file_notify_information(buffer.raw[: int(bytes_returned.value)])
                if parsed:
                    self.events.emit(parsed)
        finally:
            try:
                kernel32.CloseHandle(dir_handle)
                kernel32.CloseHandle(stop_event)
                kernel32.CloseHandle(io_event)
            except Exception:
                pass
            self._dir_handle = None
            self._stop_event = None
            self._io_event = None
