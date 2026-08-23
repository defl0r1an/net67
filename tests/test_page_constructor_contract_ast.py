"""Тот же контракт страниц, но без Qt — по исходникам.

`test_page_constructor_contract.py` проверяет ровно это же, но перед
проверкой поднимает QApplication и импортирует модули страниц. Там, где
Qt не ставится — а это и здешний прогон, и любая машина без графики, —
тест не падает, а объявляет себя пропущенным. Выглядит зелёным.

Именно поэтому мимо него прошло:

    LogsPage.__init__() missing 1 required keyword-only argument:
    'orchestra_feature'

Оркестратор из программы вырезали, сборщик зависимостей перестал его
передавать, а конструктор страницы продолжал требовать. Раздел «Логи»
падал при открытии.

Здесь ничего не импортируется. Файлы разбираются как текст: из схемы
навигации берётся, какому классу какой модуль соответствует, из карты
зависимостей — какой сборщик обслуживает страницу, из сборщика — какие
ключи он кладёт в словарь. Дальше сверяются имена. Работает везде, где
есть Python.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"


def _parse(relative: str) -> ast.Module:
    path = SRC / relative
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _route_specs() -> dict[str, tuple[str, str]]:
    """PageName -> (модуль страницы, имя класса) из схемы навигации."""
    routes: dict[str, tuple[str, str]] = {}
    for node in ast.walk(_parse("ui/navigation/schema.py")):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "PageRouteSpec"):
            continue
        values = {
            kw.arg: kw.value
            for kw in node.keywords
            if kw.arg in ("page_name", "module_name", "class_name")
        }
        page = values.get("page_name")
        module = values.get("module_name")
        class_name = values.get("class_name")
        if not (
            isinstance(page, ast.Attribute)
            and isinstance(module, ast.Constant)
            and isinstance(class_name, ast.Constant)
        ):
            continue
        routes[page.attr] = (module.value, class_name.value)
    return routes


def _deps_builders() -> dict[str, str]:
    """PageName -> имя функции-сборщика из карты зависимостей."""
    builders: dict[str, str] = {}
    tree = _parse("ui/page_composition.py")

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        named = any(
            isinstance(target, ast.Name) and target.id == "PAGE_DEPS_BUILDERS"
            for target in targets
        )
        if not named or not isinstance(node.value, ast.Dict):
            continue

        for key, value in zip(node.value.keys, node.value.values):
            if not isinstance(key, ast.Attribute):
                continue
            builder = None
            if isinstance(value, ast.Call) and value.args:
                first = value.args[0]
                if isinstance(first, ast.Name):
                    builder = first.id
            elif isinstance(value, ast.Name):
                builder = value.id
            if builder:
                builders[key.attr] = builder

    return builders


def _find_function(name: str) -> ast.FunctionDef | None:
    for path in (SRC / "ui" / "page_deps").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
    return None


def _returned_keys(func: ast.FunctionDef) -> set[str] | None:
    """Строковые ключи словарей, которые функция возвращает.

    None означает «разобрать не удалось» — например, словарь собирается
    по кускам. Такие сборщики тест пропускает: врать о проверке хуже,
    чем честно её не делать.
    """
    keys: set[str] = set()
    seen_dict = False

    for node in ast.walk(func):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        if not isinstance(node.value, ast.Dict):
            return None
        seen_dict = True
        for key in node.value.keys:
            if key is None:  # **распаковка
                return None
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                return None
            keys.add(key.value)

    # Ключи могут доезжать и через промежуточную переменную.
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
                    seen_dict = True
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, str):
                keys.add(node.slice.value)

    return keys if seen_dict else None


def _required_kwargs(module_name: str, class_name: str) -> set[str] | None:
    path = SRC / (module_name.replace(".", "/") + ".py")
    if not path.exists():
        return None

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == class_name):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                args = item.args
                required: set[str] = set()

                # Только ключевые: позиционные у страниц — это parent.
                defaults = args.kw_defaults or []
                for arg, default in zip(args.kwonlyargs, defaults):
                    if default is None:
                        required.add(arg.arg)
                return required
    return None


class PageConstructorAstContractTests(unittest.TestCase):
    def test_builders_provide_every_required_argument(self) -> None:
        routes = _route_specs()
        builders = _deps_builders()

        self.assertTrue(routes, "схема навигации не разобралась")
        self.assertTrue(builders, "карта зависимостей не разобралась")

        checked = 0
        for page, builder_name in builders.items():
            route = routes.get(page)
            if route is None:
                continue
            module_name, class_name = route

            required = _required_kwargs(module_name, class_name)
            if required is None:
                continue

            func = _find_function(builder_name)
            if func is None:
                continue

            provided = _returned_keys(func)
            if provided is None:
                continue

            checked += 1
            missing = required - provided
            self.assertFalse(
                missing,
                f"{class_name}: {builder_name} не передаёт {sorted(missing)}",
            )

        self.assertGreater(checked, 3, "проверить удалось слишком мало страниц")

    def test_logs_page_opens_without_the_removed_orchestra(self) -> None:
        """Отдельно про раздел «Логи» — на нём это и сломалось."""
        required = _required_kwargs("log.ui.page", "LogsPage")
        self.assertIsNotNone(required)
        self.assertNotIn("orchestra_feature", required)


if __name__ == "__main__":
    unittest.main()
