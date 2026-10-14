"""Настоящее главное окно собирается целиком: то, что упало в 0.17.67.

Перенесённые стрелки «назад/вперёд» брали panel.returnButton у боковой панели
qfluentwidgets, а у net67 своя оболочка (shell.app_window, NavigationCompat) —
и сборка окна падала, программа открывалась пустой. Все тесты при этом
проходили: каждый собирал свой кусок на чужом окне, а настоящий путь
create_window → build_ui не проходил ни один.

Окно собирается так же, как при запуске, но без экрана, в трее и без фоновых
задач (их ставит entry после показа окна), поэтому обход не запускается и
hosts не пишется. Потом открывается каждая страница: они строятся лениво, и
сломанная на оболочке net67 страница иначе проявилась бы только у людей.

Сборка идёт в отдельном процессе. В общем процессе тестов живое окно со
своими таймерами и фоновыми задачами оставалось после теста, и все
следующие тесты, крутящие очередь событий, замедлялись в разы: прогон
группы, в которой стоял этот тест, растягивался с семи минут на час.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = r'''
import sys
import os
import faulthandler
faulthandler.dump_traceback_later(30, repeat=True)
from settings import store as settings_store
settings_store.MAIN_DIRECTORY = os.environ["NET67_UI_TEST_DATA"]
from config.window_metrics import HEIGHT, WIDTH
from main.qt_runtime import ensure_qt_runtime

app = ensure_qt_runtime()
import log.log as log_module

errors = []
original_log = log_module.log


def spy(message, level="INFO", *args, **kwargs):
    if str(level).upper() in {"ERROR", "CRITICAL"}:
        errors.append(str(message))
    return original_log(message, level, *args, **kwargs)


log_module.log = spy
from app.page_names import PageName
from main.application_controller import ApplicationController
from main.window import LupiDPIApp
from ui.window_adapter import show_page

controller = ApplicationController(window_cls=LupiDPIApp, start_in_tray=True)
window = controller.create_window()
window.build_ui(WIDTH, HEIGHT)
for _ in range(20):
    app.processEvents()
if window.stackedWidget.count() <= 0:
    errors.append("в стопке страниц нет ни одной страницы")
for page_name in PageName:
    try:
        if not show_page(window, page_name, allow_internal=True):
            errors.append(f"страница {page_name.name} не открылась")
    except Exception as exc:
        errors.append(f"страница {page_name.name}: {exc!r}")
    for _ in range(5):
        app.processEvents()

# Из исходников готовых пресетов нет: папку presets кладёт сборка.
errors = [line for line in errors if "Пресеты не найдены" not in line]
for line in errors:
    print("BUILD-ERROR", line, flush=True)
print("BUILD-OK" if not errors else "BUILD-FAILED", flush=True)
# Живое окно с фоновыми задачами не закрываем по-честному: процессу хватает выхода.
exit_code = 0 if not errors else 1
if sys.platform == "win32":
    # ExitProcess ждёт завершения DLL фоновых потоков Qt и может зависнуть
    # уже после BUILD-OK. Окно одноразовое: завершаем его без выгрузки DLL.
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.TerminateProcess(kernel32.GetCurrentProcess(), exit_code)
os._exit(exit_code)
'''


def _run_ui_script(script, env, folder, timeout=180):
    stdout_path = Path(folder) / "stdout.log"
    stderr_path = Path(folder) / "stderr.log"
    # Файлы не ждут EOF от фоновых потомков уже завершённого процесса.
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(
            [sys.executable, "-c", script], cwd=str(ROOT), env=env,
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            timeout=timeout,
        )
    return completed, stdout_path.read_text(encoding="utf-8", errors="replace"), stderr_path.read_text(encoding="utf-8", errors="replace")


class MainWindowBuildsTests(unittest.TestCase):
    def test_real_window_builds_ui_and_opens_every_page(self) -> None:
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(ROOT / "src"), env.get("PYTHONPATH", "")) if part
        )
        with tempfile.TemporaryDirectory(prefix="net67-ui-test-") as folder:
            env["NET67_UI_TEST_DATA"] = folder
            # Фикстуры родителя не изолируют настройки дочернего процесса.
            try:
                completed, output, stderr = _run_ui_script(_SCRIPT, env, folder)
            except subprocess.TimeoutExpired:
                stdout = (Path(folder) / "stdout.log").read_text(encoding="utf-8", errors="replace")
                stderr = (Path(folder) / "stderr.log").read_text(encoding="utf-8", errors="replace")
                self.fail(f"Окно не собрано за 180 с.\n{stdout[-3000:]}\n{stderr[-6000:]}")
            stderr_tail = stderr[-6000:]
            details = "\n".join(line for line in output.splitlines() if line.startswith("BUILD-"))
            self.assertIn("BUILD-OK", output, f"{details}\n{stderr_tail}")
            self.assertEqual(completed.returncode, 0, f"{details}\n{stderr_tail}")
    def test_finished_window_does_not_wait_for_descendant_output(self) -> None:
        import signal

        script = """
import os,sys,subprocess
from pathlib import Path
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'], close_fds=False)
Path(os.environ['NET67_CHILD_PID_PATH']).write_text(str(child.pid))
print('BUILD-OK', flush=True)
os._exit(0)
"""
        with tempfile.TemporaryDirectory(prefix="net67-output-test-") as folder:
            pid_path = Path(folder) / "child.pid"
            env = dict(os.environ, NET67_CHILD_PID_PATH=str(pid_path))
            try:
                completed, output, _stderr = _run_ui_script(script, env, folder, timeout=2)
                self.assertEqual(completed.returncode, 0)
                self.assertIn("BUILD-OK", output)
            finally:
                if pid_path.exists():
                    pid = int(pid_path.read_text())
                    # Останавливаем только созданного этим тестом потомка.
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=5,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        os.kill(pid, signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
