"""Сверка набора зависимостей страниц управления с их сигнатурами.

Один и тот же build_control_page_kwargs обслуживает и net67 v2, и
net67 v1. Стоит добавить ключ и забыть про вторую страницу — она упадёт
с TypeError при первом открытии, причём только в рантайме и только в том
режиме, который разработчик не проверял.

Именно так чуть не сломался net67 v1 при добавлении runtime_feature.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

DEPS_FILE = PROJECT_SRC / "ui" / "page_deps" / "presets.py"


def _control_deps_keys() -> set[str]:
    """Ключи, которые возвращает именно build_control_page_kwargs."""
    source = DEPS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_control_page_kwargs":
            keys: set[str] = set()
            for statement in ast.walk(node):
                # Словарь может возвращаться сразу или собираться в
                # переменную и дополняться по ходу (kwargs["..."] = ...).
                value = None
                if isinstance(statement, ast.Return) and isinstance(statement.value, ast.Dict):
                    value = statement.value
                elif isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Dict):
                    value = statement.value
                if value is not None:
                    keys.update(
                        key.value
                        for key in value.keys
                        if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    )
                if isinstance(statement, ast.Assign):
                    for target in statement.targets:
                        if (
                            isinstance(target, ast.Subscript)
                            and isinstance(target.slice, ast.Constant)
                            and isinstance(target.slice.value, str)
                        ):
                            keys.add(target.slice.value)
            return keys
    return set()


def _page_keyword_args(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    names = {arg.arg for arg in item.args.kwonlyargs}
                    if item.args.kwarg is not None:
                        names.add("**")
                    return names
    return set()


class ControlPageDepsContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.keys = _control_deps_keys()

    def test_deps_builder_is_found(self) -> None:
        self.assertTrue(self.keys, "не удалось разобрать build_control_page_kwargs")

    def test_zapret2_accepts_every_dependency(self) -> None:
        accepted = _page_keyword_args(
            PROJECT_SRC / "presets" / "ui" / "control" / "zapret2" / "page.py",
            "Zapret2ModeControlPage",
        )
        if "**" in accepted:
            self.skipTest("страница принимает **kwargs")
        self.assertEqual(self.keys - accepted, set())


    def test_runtime_actions_expose_is_any_running(self) -> None:
        source = (
            PROJECT_SRC / "presets" / "ui" / "control" / "control_page_shared.py"
        ).read_text(encoding="utf-8")

        self.assertIn("is_any_running", source)


class OneClickButtonWiringTests(unittest.TestCase):
    def test_button_is_mounted_on_zapret2_page(self) -> None:
        source = (
            PROJECT_SRC / "presets" / "ui" / "control" / "zapret2" / "page.py"
        ).read_text(encoding="utf-8")

        self.assertIn("OneClickButton", source)
        self.assertIn("self.oneclick_button", source)

    def test_orchestrator_runs_off_the_ui_thread(self) -> None:
        """Проверка DNS и опрос доменов блокирующие — в UI-потоке нельзя."""
        source = (PROJECT_SRC / "oneclick" / "ui" / "oneclick_worker.py").read_text(encoding="utf-8")

        self.assertIn("QThread", source)
        self.assertRegex(source, r"class _OneClickWorker\(QThread\)")

    def test_worker_gets_runtime_feature_in_constructor(self) -> None:
        """Регрессия: раньше поле задавалось отдельным методом и могло не быть."""
        source = (PROJECT_SRC / "oneclick" / "ui" / "button.py").read_text(encoding="utf-8")

        self.assertIn("runtime_feature", source)
        self.assertNotIn("def set_runtime_feature", source)


if __name__ == "__main__":
    unittest.main()
