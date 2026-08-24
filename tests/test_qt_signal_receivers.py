"""Приёмники сигналов Qt обязаны поддерживать слабые ссылки.

PyQt держит на объект-приёмник слабую ссылку, чтобы разорвать связь,
когда объект соберёт сборщик мусора. Если у класса есть __slots__ без
__weakref__, `signal.connect(self.метод)` падает с

    TypeError: cannot create weak reference to 'RuntimeEvents' object

и это ещё полбеды. connect() к тому моменту уже вернул объект
QMetaObject.Connection, исключение осталось выставленным, и наружу
вылезает

    SystemError: <class 'PyQt6.QtCore.QMetaObject.Connection'>
                 returned a result with an exception set

По такому сообщению найти причину невозможно: в нём нет ни файла, ни
строки. Ровно оно валило шаг «launch runtime» при каждом запуске
приложения. Тест ищет такие классы разбором исходников, потому что для
воспроизведения нужен живой Qt.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"


def _decorator_name(node: ast.expr) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _dataclass_flag(decorator: ast.expr, name: str) -> bool:
    if not isinstance(decorator, ast.Call):
        return False
    for keyword in decorator.keywords:
        if keyword.arg == name and getattr(keyword.value, "value", False) is True:
            return True
    return False


def _connects_own_methods(class_node: ast.ClassDef) -> list[str]:
    """Методы самого класса, подключаемые к сигналам Qt."""
    found: list[str] = []
    for node in ast.walk(class_node):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
            and node.args
            and isinstance(node.args[0], ast.Attribute)
            and isinstance(node.args[0].value, ast.Name)
            and node.args[0].value.id == "self"
        ):
            found.append(node.args[0].attr)
    return sorted(set(found))


def _offenders() -> list[str]:
    problems: list[str] = []

    for path in PROJECT_SRC.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            has_slots = any(
                _decorator_name(d) == "dataclass" and _dataclass_flag(d, "slots")
                for d in node.decorator_list
            )
            has_weakref = any(
                _decorator_name(d) == "dataclass" and _dataclass_flag(d, "weakref_slot")
                for d in node.decorator_list
            )
            if not has_slots or has_weakref:
                continue

            methods = _connects_own_methods(node)
            if methods:
                relative = path.relative_to(PROJECT_SRC)
                problems.append(
                    f"{relative}:{node.lineno} {node.name} "
                    f"подключает {', '.join(methods)}"
                )

    return problems


class QtSignalReceiverTests(unittest.TestCase):
    def test_no_slotted_dataclass_connects_its_own_methods(self) -> None:
        offenders = _offenders()

        self.assertEqual(
            offenders,
            [],
            "класс со slots подключает свои методы к сигналу Qt — "
            "PyQt не сможет взять слабую ссылку и запуск упадёт с "
            "SystemError про QMetaObject.Connection:\n" + "\n".join(offenders),
        )

    def test_runtime_events_supports_weak_reference(self) -> None:
        """Тот самый класс, который валил запуск."""
        import weakref
        from dataclasses import dataclass, field
        from typing import Any

        source = (PROJECT_SRC / "app" / "feature_facades" / "runtime_parts.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        node = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "RuntimeEvents"
        )

        self.assertFalse(
            any(
                _decorator_name(d) == "dataclass" and _dataclass_flag(d, "slots")
                for d in node.decorator_list
            ),
            "RuntimeEvents снова объявлен со slots — запуск сломается",
        )

        # Контрольный пример: со slots слабая ссылка действительно не берётся.
        @dataclass(slots=True)
        class Slotted:
            value: Any = None

        @dataclass
        class Plain:
            value: Any = None
            items: list = field(default_factory=list)

        with self.assertRaises(TypeError):
            weakref.ref(Slotted())

        self.assertIsNotNone(weakref.ref(Plain()))


class StartupDiagnosticsTests(unittest.TestCase):
    """Шаг запуска обязан писать traceback, иначе искать нечего."""

    def test_startup_step_failure_logs_traceback(self) -> None:
        source = (PROJECT_SRC / "main" / "startup_coordinator.py").read_text(encoding="utf-8")

        self.assertIn("Ошибка startup-шага", source)
        self.assertIn("format_exc()", source)


if __name__ == "__main__":
    unittest.main()
