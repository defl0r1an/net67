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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = r'''
import sys
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
import os
os._exit(0 if not errors else 1)
'''


class MainWindowBuildsTests(unittest.TestCase):
    def test_real_window_builds_ui_and_opens_every_page(self) -> None:
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(ROOT / "src"), env.get("PYTHONPATH", "")) if part
        )
        completed = subprocess.run(
            [sys.executable, "-c", _SCRIPT],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            timeout=180,
        )
        output = completed.stdout.decode("utf-8", "replace")
        details = "\n".join(line for line in output.splitlines() if line.startswith("BUILD-"))
        stderr_tail = completed.stderr.decode("utf-8", "replace")[-3000:]
        self.assertIn("BUILD-OK", output, f"{details}\n{stderr_tail}")
        self.assertEqual(completed.returncode, 0, f"{details}\n{stderr_tail}")


if __name__ == "__main__":
    unittest.main()
