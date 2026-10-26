"""Окно-продолжение установки: обновление видно от загрузки до новой версии.

Окно обновления живёт внутри net67.exe, а этот файл установщик как раз
заменяет. Между закрытием старой версии и открытием новой экран был
пустым или показывал голое окно установщика. Окно-продолжение — отдельный
процесс PowerShell (WinForms): этапы «Закрываем старую версию →
Устанавливаем → Открываем новую версию» с галочками, логотип бежит по
полосе, спокойные фразы. Гаснет, когда новая версия открылась.

Цепочка:

1. Старая программа зовёт ``start_install_splash`` (поток окна: логотип
   рисуется из значка программы) — здесь раскладываются JSON с текстами,
   PNG логотипа и скрипт (updater/install_splash_script.py), запускается
   PowerShell. Старая программа коротко ждёт метку «окно показано» и только
   потом запускает установщик — тихо (/VERYSILENT): его ход показывает окно.
2. Номер процесса установщика пишется в файл (``record_installer_pid``):
   по нему окно видит, когда установка кончилась.
3. Новая версия, собрав окно, зовёт ``mark_update_app_ready`` — окно гаснет.

Окно не встало за несколько секунд — обновление идёт по-старому: надпись о
закрытии и видимое окно установщика. Обновление важнее красоты, поэтому
любая неудача здесь только пишется в журнал.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from log.log import log

from updater.install_splash_script import (
    FAILED_LINGER_SECONDS,
    READY_TIMEOUT_SECONDS,
    SPLASH_SCRIPT,
    TOTAL_TIMEOUT_SECONDS,
)

#: Сколько старая программа ждёт, пока окно встанет на место, с.
#:
#: Холодный PowerShell с WinForms обычно укладывается в секунду-две; дольше
#: не держим — установка важнее.
SPLASH_SHOWN_TIMEOUT_SECONDS = 4.0
#: Метка «новая версия открылась» нужна только окну, которое ещё может ждать.
READY_MARK_MAX_AGE_SECONDS = TOTAL_TIMEOUT_SECONDS
_LOG_LEVEL = "🔁 UPDATE"
_SUCCESS_TEXT = "Installation process succeeded"


def splash_dir() -> Path:
    from config.runtime_layout import APPLICATION_PATHS

    return Path(APPLICATION_PATHS.update_cache_dir) / "install_splash"


@dataclass(slots=True)
class SplashHandle:
    directory: Path
    process: subprocess.Popen | None

    @property
    def shown_path(self) -> Path:
        return self.directory / "shown.txt"

    @property
    def installer_pid_path(self) -> Path:
        return self.directory / "installer.pid"

    @property
    def cancel_path(self) -> Path:
        return self.directory / "cancel.txt"

    def is_shown(self) -> bool:
        return self.shown_path.exists()

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def record_installer_pid(self, pid: int) -> None:
        try:
            self.installer_pid_path.write_text(str(int(pid)), encoding="ascii")
        except OSError as exc:
            log(f"Окно-продолжение: номер установщика не записан: {exc}", _LOG_LEVEL)

    def cancel(self) -> None:
        """Установка не началась: окно уходит само, по метке."""
        try:
            self.cancel_path.write_text("cancel", encoding="ascii")
        except OSError:
            pass
        if self.process is not None:
            try:
                self.process.terminate()
            except Exception:
                pass


def texts_for(version: str, current_version: str) -> dict:
    version = str(version or "").strip()
    current = str(current_version or "").strip()
    return {
        "title": f"Обновляем net67 до v{version}",
        "subtitle": f"v{current}  →  v{version}   ·   программа откроется сама",
        "stages": ["Закрываем старую версию", f"Устанавливаем v{version}", "Открываем новую версию"],
        "footer": "Окно закроется само, когда откроется новая версия",
        "failed_title": "Обновление не установилось",
        "failed_body": (
            "Установщик закончил без успеха. Откройте net67 снова — если не откроется, "
            "скачайте установщик со страницы выпусков. Окно закроется само."
        ),
        "window_title": f"Обновление net67 до v{version}",
    }


def _colors() -> dict:
    """Цвета окна программы: фон и текст — из её палитры, акцент — тот же, что у полосы в окне обновления."""
    fallback = {
        "background": "#171717",
        "card": "#242424",
        "text": "#f2f2f2",
        "muted": "#a8a8a8",
        "accent": "#60cdff",
        "track": "#3b3b3b",
        "fail": "#ff6b6b",
    }
    try:
        from shell.theme import palette
        from ui.theme import get_theme_tokens

        tokens = get_theme_tokens()
        colors = palette(not tokens.is_light)
        return {
            "background": colors.content,
            "card": colors.surface,
            "text": colors.text,
            "muted": colors.text_muted,
            "accent": str(tokens.accent_hex or fallback["accent"]),
            "track": colors.border_strong,
            "fail": fallback["fail"],
        }
    except Exception:
        return fallback


def _write_logo(path: Path) -> bool:
    """Логотип — значок программы. Только из потока окна: QIcon.pixmap там и живёт."""
    try:
        from PyQt6.QtWidgets import QApplication

        icon = QApplication.windowIcon()
        if icon is None or icon.isNull():
            return False
        return bool(icon.pixmap(96, 96).save(str(path), "PNG"))
    except Exception:
        return False


def build_spec(*, version: str, current_version: str, directory: Path, center: tuple[int, int] | None,
               old_pid: int, setup_log_path: str, jokes) -> dict:
    from config.runtime_layout import APPLICATION_PATHS

    cx, cy = center or (0, 0)
    return {
        "texts": texts_for(version, current_version),
        "jokes": list(jokes or ()),
        "colors": _colors(),
        "font_family": "Segoe UI",
        "center_x": int(cx),
        "center_y": int(cy),
        "old_pid": int(old_pid),
        "installer_pid_path": str(directory / "installer.pid"),
        "setup_log_path": str(setup_log_path or ""),
        "ready_path": str(directory / "ready.txt"),
        "shown_path": str(directory / "shown.txt"),
        "cancel_path": str(directory / "cancel.txt"),
        "log_path": str(directory / "splash.log"),
        "logo_path": str(directory / "logo.png"),
        "icon_path": str(APPLICATION_PATHS.stable_icon),
        "ready_timeout_seconds": READY_TIMEOUT_SECONDS,
        "total_timeout_seconds": TOTAL_TIMEOUT_SECONDS,
        "failed_linger_seconds": FAILED_LINGER_SECONDS,
    }


def _reset_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("shown.txt", "installer.pid", "cancel.txt", "ready.txt"):
        try:
            (directory / name).unlink(missing_ok=True)
        except OSError:
            pass


def _powershell_command(script: Path, spec: Path) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-STA",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(script),
        "-SpecPath",
        str(spec),
    ]


def _spawn(command: list[str]) -> subprocess.Popen:
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Окно должно пережить старую программу: если она сидит в задании Windows,
    # которое убивает детей при закрытии, PowerShell из него выводится.
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
    try:
        return subprocess.Popen(command, creationflags=no_window | breakaway, close_fds=True)
    except OSError:
        return subprocess.Popen(command, creationflags=no_window, close_fds=True)


def start_install_splash(*, version: str, current_version: str, setup_log_path: str,
                         center: tuple[int, int] | None = None) -> SplashHandle | None:
    """Раскладывает файлы и запускает окно. None — окна не будет, обновление идёт как раньше."""
    if os.name != "nt":
        return None
    try:
        from updater.ui.fun_texts import INSTALL_PHRASES, shuffled

        directory = splash_dir()
        _reset_directory(directory)
        _write_logo(directory / "logo.png")
        spec = build_spec(
            version=version,
            current_version=current_version,
            directory=directory,
            center=center,
            old_pid=os.getpid(),
            setup_log_path=setup_log_path,
            jokes=shuffled(INSTALL_PHRASES),
        )
        spec_path = directory / "install_splash.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        script_path = directory / "install_splash.ps1"
        script_path.write_bytes(SPLASH_SCRIPT.encode("ascii"))
        process = _spawn(_powershell_command(script_path, spec_path))
    except Exception as exc:
        log(f"Окно-продолжение установки не запущено: {exc}", _LOG_LEVEL)
        return None
    log(f"Окно-продолжение установки запущено (PID {process.pid})", _LOG_LEVEL)
    return SplashHandle(directory=directory, process=process)


def mark_update_app_ready() -> bool:
    """Новая версия открылась: окно-продолжение может уходить.

    Метка нужна, только если окно недавно запускалось: обычный запуск
    программы ничего не пишет.
    """
    try:
        directory = splash_dir()
        spec_path = directory / "install_splash.json"
        if not spec_path.exists():
            return False
        if time.time() - spec_path.stat().st_mtime > READY_MARK_MAX_AGE_SECONDS:
            return False
        (directory / "ready.txt").write_text("ready", encoding="ascii")
        log("Окну-продолжению установки сказано: новая версия открылась", _LOG_LEVEL)
        return True
    except OSError as exc:
        log(f"Метка «новая версия открылась» не записана: {exc}", _LOG_LEVEL)
        return False


def setup_log_succeeded(text: str) -> bool:
    """Та же проверка, что делает окно: строка успеха в журнале установщика."""
    return _SUCCESS_TEXT in str(text or "")


__all__ = [
    "SPLASH_SHOWN_TIMEOUT_SECONDS",
    "SplashHandle",
    "build_spec",
    "mark_update_app_ready",
    "setup_log_succeeded",
    "splash_dir",
    "start_install_splash",
    "texts_for",
]
