from __future__ import annotations

import atexit
import ctypes
import os
import shutil
import subprocess
import sys
import time

from branding import APP_NAME
from config.build_info import APP_VERSION

from log.log import log

from app.restart import AFTER_RESTART_ARG
from startup.admin_check import is_admin
from utils.subproc import run_hidden

#: Сколько новый экземпляр ждёт, пока прежний закроется при перезапуске.
#:
#: Прежний перед выходом останавливает обход и выгружает драйвер — это
#: секунды, а не минуты. Дольше ждать незачем: что-то пошло не так, и
#: лучше открыться обычным вторым запуском (он покажет окно прежнего).
RESTART_WAIT_SECONDS = 20.0
RESTART_POLL_SECONDS = 0.25


def wait_for_mutex_release(
    name: str,
    handle,
    *,
    create_mutex,
    release_mutex,
    timeout: float = RESTART_WAIT_SECONDS,
    poll: float = RESTART_POLL_SECONDS,
    sleep=time.sleep,
    clock=time.monotonic,
):
    """Ждёт, пока мьютекс единственного экземпляра освободится. (хэндл, занят ли).

    Свой хэндл перед каждой новой попыткой закрывается: именованный
    мьютекс живёт, пока открыт хоть один хэндл, и с нашим открытым он не
    исчез бы никогда — ожидание длилось бы до таймаута.
    """
    deadline = clock() + float(timeout)
    already_running = True
    while already_running and clock() < deadline:
        release_mutex(handle)
        sleep(poll)
        handle, already_running = create_mutex(name)
    if already_running:
        log("Перезапуск: прежний экземпляр не закрылся вовремя", "WARNING")
    return handle, already_running


def handle_update_mode(argv: list[str] | None = None) -> None:
    args = list(argv or sys.argv)
    if len(args) < 4:
        log("--update: недостаточно аргументов", "❌ ERROR")
        return

    old_exe, new_exe = args[2], args[3]

    for _ in range(10):
        if not os.path.exists(old_exe) or os.access(old_exe, os.W_OK):
            break
        time.sleep(0.5)

    try:
        shutil.copy2(new_exe, old_exe)
        run_hidden([old_exe])
        log("Файл обновления применён", "INFO")
    except Exception as exc:
        log(f"Ошибка в режиме --update: {exc}", "❌ ERROR")
    finally:
        try:
            os.remove(new_exe)
        except FileNotFoundError:
            pass


def _respect_running_setup(args: list[str]) -> None:
    """Не мешает идущей установке обновления.

    Установщик убивает net67.exe и заменяет файлы. Открытый в это время
    net67 держит свой exe: установка с /SUPPRESSMSGBOXES срывалась молча,
    и оставалась полуобновлённая папка — «много что ломается». Поэтому,
    пока держится мьютекс установщика, открытый вручную net67 выходит
    сразу — до запроса прав и до Qt, чтобы не держать файлы. Надпись
    перед закрытием на обновление просит не открывать программу, а
    установщик в конце откроет её сам — с --after-update, и такой
    запуск дожидается конца установки, а не выходит.
    """
    from startup.single_instance import AFTER_UPDATE_ARG, setup_is_running, wait_for_setup_to_finish

    try:
        running = setup_is_running()
    except Exception:
        return
    if not running:
        return
    if AFTER_UPDATE_ARG in args:
        if not wait_for_setup_to_finish():
            log("Установщик не закончил за 90 с — открываюсь всё равно", "WARNING")
        return
    log("Идёт установка обновления — этот запуск выходит, net67 откроется сам", "INFO")
    sys.exit(0)


def shell_bootstrap(argv: list[str] | None = None) -> bool:
    args = list(argv or sys.argv)

    if "--version" in args:
        ctypes.windll.user32.MessageBoxW(None, APP_VERSION, f"{APP_NAME} – версия", 0x40)
        sys.exit(0)

    if "--update" in args and len(args) > 3:
        handle_update_mode(args)
        sys.exit(0)

    _respect_running_setup(args)

    start_in_tray = "--tray" in args

    if not is_admin():
        params = subprocess.list2cmdline(list(args[1:]))
        shell_exec_result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            params,
            None,
            1,
        )
        if int(shell_exec_result) <= 32:
            ctypes.windll.user32.MessageBoxW(
                None,
                "Не удалось запросить права администратора.",
                APP_NAME,
                0x10,
            )
        sys.exit(0)

    from startup.single_instance import (
        create_mutex,
        create_show_event,
        release_mutex,
        signal_show_event,
    )

    mutex_handle, already_running = create_mutex("net67SingleInstance")
    if already_running and AFTER_RESTART_ARG in args:
        # Перезапуск кнопкой (app/restart.py): прежний экземпляр запустил нас
        # и закрывается. Обычный второй запуск тут попросил бы его показать
        # окно и вышел — и программа не открылась бы вовсе.
        mutex_handle, already_running = wait_for_mutex_release(
            "net67SingleInstance",
            mutex_handle,
            create_mutex=create_mutex,
            release_mutex=release_mutex,
        )
    if already_running:
        if signal_show_event():
            log("Существующему экземпляру послан сигнал показать окно", "INFO")
        elif start_in_tray:
            log("Второй экземпляр из автозапуска — выходим молча", "INFO")
        else:
            ctypes.windll.user32.MessageBoxW(
                None,
                f"Экземпляр {APP_NAME} уже запущен, но не удалось показать окно!",
                APP_NAME,
                0x40,
            )
        sys.exit(0)

    atexit.register(lambda: release_mutex(mutex_handle))
    # Событие создаётся до инициализации Qt: второй экземпляр, запущенный
    # во время загрузки первого, доставит сигнал без потерь.
    create_show_event()
    return bool(start_in_tray)
