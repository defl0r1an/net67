"""Координатор запуска обязан быть QObject.

Обработчики завершения подключаются к сигналам рабочих потоков. Если
приёмник не QObject, Qt не может определить его поток и делает
соединение прямым — слот выполняется в потоке, испустившем сигнал.

Пока запуск шёл из UI-потока, это сходило с рук. Кнопка «Включить»
вызывает start() из потока оркестратора, и там цепочка обрывалась. В
логе это видно буквально:

    10:38:16  Пресет успешно запущен -> DPI запущен асинхронно -> DPI успешно запущен
    10:38:44  Пресет успешно запущен -> (тишина)

set_busy(False) не вызывался, и на странице навсегда оставалось
«Запуск net67...» с заблокированными кнопками остановки.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

LAUNCH_RUNTIME = PROJECT_SRC / "winws_runtime" / "runtime" / "launch_runtime.py"
DEPS = PROJECT_SRC / "oneclick" / "deps.py"


def _class(path: Path, name: str) -> ast.ClassDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"в {path.name} нет класса {name}")


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"в {path.name} нет функции {name}")


class LaunchRuntimeIsQObjectTests(unittest.TestCase):
    def test_runtime_inherits_qobject(self) -> None:
        node = _class(LAUNCH_RUNTIME, "PresetLaunchRuntime")
        bases = [ast.unparse(base) for base in node.bases]

        self.assertIn(
            "QObject",
            bases,
            "без QObject сигналы рабочих потоков доставляются напрямую "
            "и обработчик завершения не отрабатывает",
        )

    def test_constructor_calls_super(self) -> None:
        """QObject без super().__init__() не инициализируется."""
        node = _class(LAUNCH_RUNTIME, "PresetLaunchRuntime")
        init = next(
            child
            for child in node.body
            if isinstance(child, ast.FunctionDef) and child.name == "__init__"
        )

        self.assertIn("super().__init__()", ast.unparse(init))

    def test_finish_handlers_exist(self) -> None:
        """Именно они снимают признак занятости."""
        source = LAUNCH_RUNTIME.read_text(encoding="utf-8")

        self.assertIn("_on_dpi_start_finished", source)
        self.assertIn("_on_dpi_stop_finished", source)


class StartWaitIgnoresPreviousProcessTests(unittest.TestCase):
    """Проба не должна засчитывать процесс, работавший до запуска."""

    def test_wait_remembers_previous_state(self) -> None:
        source = ast.unparse(_function(DEPS, "_make_start_dpi"))

        self.assertIn("was_running", source)

    def test_previous_process_is_awaited_to_stop(self) -> None:
        from oneclick.deps import _make_start_dpi

        calls: list[str] = []
        # Сначала работает старый процесс, потом пауза, потом новый.
        states = iter([True, True, False, False, True, True, True])

        class _Actions:
            @staticmethod
            def start(**_kwargs):
                calls.append("start")
                return True

            @staticmethod
            def is_any_running(*, silent=True):
                _ = silent
                try:
                    return next(states)
                except StopIteration:
                    return True

        ok, message = _make_start_dpi(_Actions())()

        self.assertTrue(ok, message)
        self.assertEqual(calls, ["start"])

    def test_no_previous_process_still_waits_for_start(self) -> None:
        from oneclick.deps import _make_start_dpi

        states = iter([False, False, False, True])

        class _Actions:
            @staticmethod
            def start(**_kwargs):
                return True

            @staticmethod
            def is_any_running(*, silent=True):
                _ = silent
                try:
                    return next(states)
                except StopIteration:
                    return True

        ok, _message = _make_start_dpi(_Actions())()

        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
