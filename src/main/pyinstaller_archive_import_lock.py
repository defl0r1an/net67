from __future__ import annotations

import sys
import threading
from typing import Any


_EXTRACT_LOCK = threading.RLock()
_INSTALLED = False
_ORIGINAL_EXTRACT: Any = None


def _is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None))


def install_pyinstaller_archive_import_lock() -> bool:
    """Защищает PyInstaller-архив от параллельного чтения в фоновых потоках."""
    global _INSTALLED, _ORIGINAL_EXTRACT

    if _INSTALLED:
        return True
    if not _is_frozen_app():
        return False

    try:
        import pyimod01_archive
    except Exception:
        return False

    reader_cls = getattr(pyimod01_archive, "ZlibArchiveReader", None)
    original_extract = getattr(reader_cls, "extract", None)
    if not callable(original_extract):
        return False
    if bool(getattr(original_extract, "_zapret_import_lock_wrapped", False)):
        _INSTALLED = True
        return True

    def _locked_extract(self, *args, **kwargs):
        with _EXTRACT_LOCK:
            return original_extract(self, *args, **kwargs)

    _locked_extract._zapret_import_lock_wrapped = True
    _ORIGINAL_EXTRACT = original_extract
    reader_cls.extract = _locked_extract
    _INSTALLED = True
    return True


def _reset_for_tests() -> None:
    global _INSTALLED, _ORIGINAL_EXTRACT

    try:
        import pyimod01_archive

        reader_cls = getattr(pyimod01_archive, "ZlibArchiveReader", None)
        if reader_cls is not None and _ORIGINAL_EXTRACT is not None:
            reader_cls.extract = _ORIGINAL_EXTRACT
    except Exception:
        pass
    _INSTALLED = False
    _ORIGINAL_EXTRACT = None


__all__ = ["install_pyinstaller_archive_import_lock"]
