"""Перезапуск net67 по кнопке — после применения набора или файла настроек.

Часть настроек читается один раз при запуске (тема, язык, поведение
трея, выбранный пресет движка), и до перезапуска программа живёт со
старыми. Раньше страница так и писала «применится после перезапуска», но
перезапускать было нечем — только выйти из трея и открыть снова.

Как устроено. Новый экземпляр запускается до выхода старого, с меткой
AFTER_RESTART_ARG: обычный второй запуск увидел бы мьютекс единственного
экземпляра, послал бы старому «покажи окно» и вышел. С меткой он ждёт,
пока старый освободит мьютекс (main/shell.py). Обход, если он был включён,
поднимается снова (RESUME_BYPASS_ARG), даже если автозапуск обхода
выключен: человек перезапускал программу, а не выключал обход.
"""

from __future__ import annotations

import os
import subprocess
import sys

from log.log import log

AFTER_RESTART_ARG = "--after-restart"
RESUME_BYPASS_ARG = "--resume-bypass"

#: Метки, которые к новому запуску не переходят.
#:
#: «--tray» спрятал бы окно, хотя человек нажал кнопку в открытом окне;
#: наши метки ставятся заново по текущему состоянию.
_DROPPED_ARGS = frozenset({"--tray", AFTER_RESTART_ARG, RESUME_BYPASS_ARG})

_ACTIVE_PHASES = frozenset({"autostart_pending", "starting", "running"})


def relaunch_command(*, executable: str, argv: list[str], frozen: bool, resume_bypass: bool) -> list[str]:
    """Командная строка нового экземпляра.

    Собранная программа — это сам exe (artifact/_internal/net67.exe): его
    и запускаем. Из исходников exe — интерпретатор, и первым доводом идёт
    путь к скрипту.
    """
    rest = [arg for arg in list(argv[1:]) if arg not in _DROPPED_ARGS]
    command = [str(executable)]
    if not frozen and argv:
        command.append(str(argv[0]))
    command.extend(rest)
    command.append(AFTER_RESTART_ARG)
    if resume_bypass:
        command.append(RESUME_BYPASS_ARG)
    return command


def bypass_is_active(window) -> bool:
    """Включён ли обход сейчас — по состоянию окна, без обращения к системе."""
    try:
        phase = str(window._ui_root.launch_phase() or "").strip().lower()
    except Exception:
        return False
    return phase in _ACTIVE_PHASES


def restart_application(window) -> bool:
    """Запускает новый экземпляр и закрывает этот. False — новый не запустился."""
    command = relaunch_command(
        executable=sys.executable,
        argv=list(sys.argv),
        frozen=bool(getattr(sys, "frozen", False)),
        resume_bypass=bypass_is_active(window),
    )
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen(command, cwd=os.getcwd(), creationflags=flags, close_fds=True)  # noqa: S603
    except Exception as exc:
        log(f"Перезапуск: новый экземпляр не запустился: {exc}", "ERROR")
        return False
    log("Перезапуск: новый экземпляр запущен, этот закрывается", "INFO")
    # Обход останавливаем: новый экземпляр поднимет его сам, а два движка
    # разом не уживутся — драйвер перехвата у них общий.
    window.request_exit(stop_dpi=True)
    return True


__all__ = [
    "AFTER_RESTART_ARG",
    "RESUME_BYPASS_ARG",
    "bypass_is_active",
    "relaunch_command",
    "restart_application",
]
