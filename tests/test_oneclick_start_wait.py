"""Шаг запуска DPI ждёт готовности по тому, что у него есть.

`runtime_feature.start()` только ставит запуск в очередь и сразу
возвращает True. Оркестратор принимал это за успех и бежал дальше, а при
неудачной самопроверке откат вызывал stop() поверх незавершённого старта.
Признак «занято» ставился и снимался вперемешку, и на странице навсегда
оставалось «Запуск net67...» с заблокированными кнопками.

Первая попытка починки опрашивала runtime_feature.snapshot(). Но сюда
приходит не RuntimeFeature, а ControlRuntimeActions — узкий набор из
пяти вызовов без snapshot(). Обращение падало на каждой итерации, и
ожидание всегда доходило до таймаута: «Защита соединения не запустилась
за 40 секунд».
"""

from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


@dataclass
class _NarrowActions:
    """Ровно то, что реально приходит в build_oneclick_deps."""

    start: Callable[..., object]
    stop: Callable[[], object]
    stop_and_exit: Callable[[], object]
    is_available: Callable[[], object]
    is_any_running: Callable[..., object] | None = None
    calls: list = field(default_factory=list)


def _actions(*, start_ok=True, running_after=1, has_probe=True) -> _NarrowActions:
    state = {"started": False, "probes": 0}

    def start(**_kwargs):
        state["started"] = True
        return start_ok

    def is_any_running(*, silent=True):
        _ = silent
        state["probes"] += 1
        return state["started"] and state["probes"] >= running_after

    return _NarrowActions(
        start=start,
        stop=lambda: True,
        stop_and_exit=lambda: True,
        is_available=lambda: True,
        is_any_running=is_any_running if has_probe else None,
    )


class StartDpiWaitTests(unittest.TestCase):
    def test_narrow_actions_have_no_snapshot(self) -> None:
        """Фиксируем причину прошлой поломки."""
        from presets.ui.control.control_page_shared import ControlRuntimeActions

        self.assertFalse(
            hasattr(ControlRuntimeActions, "snapshot"),
            "если snapshot появится, шаг запуска можно упростить",
        )

    def test_success_when_process_appears(self) -> None:
        from oneclick.deps import _make_start_dpi

        ok, message = _make_start_dpi(_actions(running_after=2))()

        self.assertTrue(ok, message)
        self.assertEqual(message, "")

    def test_failure_when_start_is_rejected(self) -> None:
        from oneclick.deps import _make_start_dpi

        ok, message = _make_start_dpi(_actions(start_ok=False))()

        self.assertFalse(ok)
        self.assertIn("запустить", message)

    def test_no_probe_means_no_invented_verdict(self) -> None:
        """Без пробы честнее вернуть успех, чем ждать таймаут впустую."""
        from oneclick.deps import _make_start_dpi

        ok, _message = _make_start_dpi(_actions(has_probe=False))()

        self.assertTrue(ok)

    def test_wait_does_not_use_snapshot(self) -> None:
        import ast

        source = (PROJECT_SRC / "oneclick" / "deps.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_make_start_dpi"
        )
        # Ищем именно вызов, а не слово: в docstring оно есть намеренно.
        calls = [
            node.func.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]

        self.assertNotIn("snapshot", calls, "snapshot у ControlRuntimeActions нет")
        self.assertIn("is_any_running", ast.unparse(function))

    def test_timeout_is_reported_not_silently_passed(self) -> None:
        from oneclick.deps import _make_start_dpi

        actions = _actions(running_after=10**9)
        original = __import__("time").monotonic
        ticks = iter([0.0, 0.1] + [100.0] * 50)

        import time as time_module

        time_module.monotonic = lambda: next(ticks)
        try:
            ok, message = _make_start_dpi(actions)()
        finally:
            time_module.monotonic = original

        self.assertFalse(ok)
        self.assertIn("40 секунд", message)


if __name__ == "__main__":
    unittest.main()
