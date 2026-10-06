"""Каждая команда, которую зовёт фасад, есть в модуле, куда он за ней ходит.

Фасады (app/feature_facades/*.py) берут команды из модуля в `_commands()`,
например `import updater.public`. В 0.14.67 фасад обновлятора звал
`remember_skipped_update`, `remember_whats_new` и `pending_whats_new`, а в
updater/public.py их не было: AttributeError ловился выше, и кнопка
«Установить» в окне обновления при запуске молча ничего не делала. Тесты
окна подменяли сам фасад и поломку не видели.

Тест читает исходник фасада, находит модуль из `_commands()` и вызовы
`self._commands().<имя>(` и проверяет, что каждое имя в модуле есть.
"""

from __future__ import annotations

import ast
import importlib
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FACADES = SRC / "app" / "feature_facades"


def _commands_module(tree: ast.Module) -> str | None:
    """Имя модуля, который возвращает `_commands()` фасада."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_commands":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Import):
                    return inner.names[0].name
                if isinstance(inner, ast.ImportFrom) and inner.module:
                    return f"{inner.module}.{inner.names[0].name}"
    return None


def _called_commands(tree: ast.Module) -> set[str]:
    """Имена из вызовов вида `self._commands().имя(...)` и `cls._commands().имя`."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        target = node.value
        if (
            isinstance(target, ast.Call)
            and isinstance(target.func, ast.Attribute)
            and target.func.attr == "_commands"
        ):
            names.add(node.attr)
    return names


class FeatureFacadeCommandExportsTests(unittest.TestCase):
    def test_every_command_a_facade_calls_exists_in_its_module(self) -> None:
        checked = 0
        for path in sorted(FACADES.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            module_name = _commands_module(tree)
            called = _called_commands(tree)
            if not module_name or not called:
                continue
            with self.subTest(facade=path.name, module=module_name):
                module = importlib.import_module(module_name)
                missing = sorted(name for name in called if not hasattr(module, name))
                self.assertEqual(missing, [])
                checked += 1
        self.assertGreater(checked, 5)

    def test_updater_facade_sees_the_update_window_commands(self) -> None:
        import updater.public as updater_public

        for name in ("remember_skipped_update", "remember_whats_new", "pending_whats_new"):
            with self.subTest(command=name):
                self.assertTrue(callable(getattr(updater_public, name, None)))


if __name__ == "__main__":
    unittest.main()
