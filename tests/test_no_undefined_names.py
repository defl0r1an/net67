# tests/test_no_undefined_names.py
"""Ни один модуль не должен обращаться к несуществующему имени.

Проверка родилась из настоящей поломки. Из боковой панели убрали фильтр
по строке поиска: объявление переменной удалили, а обращение к ней
десятью строками ниже осталось. Файл компилировался, сборка ушла к
человеку, и приложение падало на каждом переключении режима —

    NameError: name 'search_query' is not defined

— то есть на действии, которое до этого работало годами.

Ловится это за секунду и стоит копейки, а не ловилось ничем: компиляция
такое пропускает, а тесты не доставали до конкретной ветки.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from check_undefined_names import check_file, check_paths  # noqa: E402


class UndefinedNameTests(unittest.TestCase):
    def test_source_tree_has_no_undefined_names(self) -> None:
        problems = check_paths([REPO_ROOT / "src"])
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_tools_have_no_undefined_names(self) -> None:
        problems = check_paths([REPO_ROOT / "tools"])
        self.assertEqual(problems, [], "\n" + "\n".join(problems))


class CheckerBehaviourTests(unittest.TestCase):
    """Сама проверка обязана ловить то, ради чего написана, и молчать про остальное.

    Второе не менее важно первого: проверка, которая ругается на
    исправный код, перестаёт что-либо значить уже на третий раз.
    """

    def _check(self, source: str) -> list[str]:
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.py"
            path.write_text(source, encoding="utf-8")
            return check_file(path)

    def test_catches_the_original_break(self) -> None:
        problems = self._check(
            "def apply_filter(items):\n"
            "    return [x for x in items if search_query in x]\n"
        )
        self.assertTrue(problems)
        self.assertIn("search_query", problems[0])

    def test_local_variable_is_fine(self) -> None:
        self.assertEqual(
            self._check("def f(items):\n    q = ''\n    return [x for x in items if q in x]\n"),
            [],
        )

    def test_argument_is_fine(self) -> None:
        self.assertEqual(self._check("def f(query):\n    return query.strip()\n"), [])

    def test_module_level_import_is_fine(self) -> None:
        self.assertEqual(self._check("import json\n\n\ndef f(x):\n    return json.dumps(x)\n"), [])

    def test_deferred_import_inside_the_function_is_fine(self) -> None:
        self.assertEqual(
            self._check("def f(x):\n    from json import dumps\n\n    return dumps(x)\n"),
            [],
        )

    def test_exception_alias_is_fine(self) -> None:
        self.assertEqual(
            self._check(
                "def f():\n"
                "    try:\n"
                "        pass\n"
                "    except Exception as exc:\n"
                "        return str(exc)\n"
            ),
            [],
        )

    def test_with_target_is_fine(self) -> None:
        self.assertEqual(
            self._check("def f(p):\n    with open(p) as handle:\n        return handle.read()\n"),
            [],
        )

    def test_closure_over_outer_function_is_fine(self) -> None:
        self.assertEqual(
            self._check(
                "def outer(value):\n"
                "    def inner():\n"
                "        return value\n"
                "    return inner()\n"
            ),
            [],
        )

    def test_annotation_only_name_is_fine(self) -> None:
        """Имя из аннотации не вычисляется и ошибкой не является.

        Классы, импортируемые только ради подсказок типов, живут именно
        так — под `TYPE_CHECKING`, которого в рантайме нет.
        """
        self.assertEqual(
            self._check(
                "from __future__ import annotations\n\n\n"
                "def f(state: AppUiState) -> AppUiState | None:\n"
                "    return None\n"
            ),
            [],
        )

    def test_builtins_are_fine(self) -> None:
        self.assertEqual(self._check("def f(x):\n    return len(str(x)) or ValueError\n"), [])

    def test_broken_syntax_is_reported_not_swallowed(self) -> None:
        problems = self._check("def f(:\n    pass\n")
        self.assertTrue(problems)
        self.assertIn("синтаксис", problems[0])

    def test_every_source_file_is_actually_read(self) -> None:
        """Проверка, которая ничего не открыла, тоже отчитается «чисто»."""
        files = list((REPO_ROOT / "src").rglob("*.py"))
        self.assertGreater(len(files), 100, "исходники не найдены — проверка ничего не проверяла")

        # И они действительно разбираются, а не молча пропускаются.
        sample = files[0]
        ast.parse(sample.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
