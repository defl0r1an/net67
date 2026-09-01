# tools/check_undefined_names.py
"""Ищет обращения к именам, которых в модуле нет.

## Зачем

Компиляция такое пропускает. `search_query` без объявления — законный
Python ровно до той секунды, когда строка выполнится. Именно так и
случилось: из боковой панели убрали фильтр по строке поиска, удалили
объявление переменной, а обращение к ней десятью строками ниже осталось.
Файл компилировался, тесты не доставали до этой ветки, сборка ушла к
человеку — и приложение падало при каждом переключении режима:

    NameError: name 'search_query' is not defined

Вся ошибка — в одной осиротевшей строке, и любая проверка нашла бы её за
секунду. Эта — находит.

## Что считается объявленным

Имена модуля целиком: импорты, функции, классы, присваивания на верхнем
уровне. Внутри функции — ещё и её доводы, присваивания, вложенные
определения, переменные `with`, `except ... as` и переборов.

Замыкания разбираются грубо: имя из объемлющей функции считается
известным, потому что в модуле оно тоже видно. Пропустить ошибку так
можно, выдумать несуществующую — нет, а второе куда неприятнее: проверка,
которая ругается на исправный код, быстро перестаёт что-либо значить.

## Что пропускается намеренно

`__file__` и соседние двойные подчёркивания — их даёт сам Python.
`WindowsError` — встроенное имя Windows, которого нет на других системах,
а разбор идёт где угодно. Имена из аннотаций — при `from __future__
import annotations` они не вычисляются вовсе, и ссылка на класс, который
импортируется только для проверки типов, ошибкой не является.
"""

from __future__ import annotations

import ast
import builtins
import pathlib
import sys


BUILTIN_NAMES = set(dir(builtins))

#: Имена, которых нет в `builtins` этой системы, но которые законны.
EXTRA_KNOWN = {
    "__file__",
    "__name__",
    "__doc__",
    "__package__",
    "__spec__",
    "__loader__",
    "__builtins__",
    # Есть только на Windows, а проверку гоняют и на других системах.
    "WindowsError",
}


def _bind_targets(node, bound: set[str]) -> None:
    """Добавляет в набор всё, что этот узел связывает."""
    for name in ast.walk(node):
        if isinstance(name, ast.Name):
            bound.add(name.id)


def _annotation_nodes(tree) -> set[int]:
    """Узлы, живущие в аннотациях: их имена не вычисляются."""
    inside: set[int] = set()
    for node in ast.walk(tree):
        annotations = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotations.append(node.returns)
            args = node.args
            annotations.extend(
                arg.annotation
                for group in (args.posonlyargs, args.args, args.kwonlyargs)
                for arg in group
            )
            annotations.extend(
                getattr(arg, "annotation", None) for arg in (args.vararg, args.kwarg) if arg
            )
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)

        for annotation in annotations:
            if annotation is None:
                continue
            for sub in ast.walk(annotation):
                inside.add(id(sub))
    return inside


def _module_level_names(tree) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def _function_bound_names(node) -> set[str]:
    bound: set[str] = set()
    args = node.args
    for group in (args.posonlyargs, args.args, args.kwonlyargs):
        bound.update(arg.arg for arg in group)
    for arg in (args.vararg, args.kwarg):
        if arg is not None:
            bound.add(arg.arg)

    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
            bound.add(sub.id)
        elif isinstance(sub, (ast.Import, ast.ImportFrom)):
            for alias in sub.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(sub.name)
            inner = sub.args if hasattr(sub, "args") else None
            if inner is not None:
                for group in (inner.posonlyargs, inner.args, inner.kwonlyargs):
                    bound.update(arg.arg for arg in group)
                for arg in (inner.vararg, inner.kwarg):
                    if arg is not None:
                        bound.add(arg.arg)
        elif isinstance(sub, ast.ExceptHandler) and sub.name:
            bound.add(sub.name)
        elif isinstance(sub, (ast.With, ast.AsyncWith)):
            for item in sub.items:
                if item.optional_vars is not None:
                    _bind_targets(item.optional_vars, bound)
        elif isinstance(sub, ast.comprehension):
            _bind_targets(sub.target, bound)
        elif isinstance(sub, (ast.Global, ast.Nonlocal)):
            bound.update(sub.names)
        elif isinstance(sub, ast.MatchAs) and sub.name:
            bound.add(sub.name)
        elif isinstance(sub, ast.MatchStar) and sub.name:
            bound.add(sub.name)

    return bound


def check_file(path: pathlib.Path) -> list[str]:
    """Возвращает список замечаний по одному файлу."""
    try:
        # utf-8-sig: у сгенерированных при сборке файлов бывает BOM,
        # и обычный utf-8 спотыкается об него на первом же символе.
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno}: синтаксис — {exc.msg}"]

    known = _module_level_names(tree) | BUILTIN_NAMES | EXTRA_KNOWN
    skip = _annotation_nodes(tree)

    problems: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bound = known | _function_bound_names(node)
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Name) or not isinstance(sub.ctx, ast.Load):
                continue
            if id(sub) in skip or sub.id in bound:
                continue
            problems.append(f"{path}:{sub.lineno}: имя {sub.id!r} нигде не задано")

    return problems


def check_paths(paths) -> list[str]:
    problems: list[str] = []
    for item in paths:
        path = pathlib.Path(item)
        files = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for file in files:
            problems.extend(check_file(file))
    return sorted(set(problems))


def main(argv=None) -> int:
    targets = list(argv or sys.argv[1:]) or ["src"]
    problems = check_paths(targets)
    if not problems:
        print("Необъявленных имён нет")
        return 0

    print("\n".join(problems))
    print(f"\nВсего замечаний: {len(problems)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
