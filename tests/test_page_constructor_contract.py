"""Каждая страница должна получать то, что просит в конструкторе.

Проверка появилась после пустого окна. Убирая страницу доната, я снял
`open_premium` из сборщиков зависимостей, но забыл про сам параметр в
конструкторах двух страниц управления. Приложение запустилось, показало
заголовок с версией — и всё:

    Startup: build_ui failed: Zapret2ModeControlPage.__init__()
    missing 1 required keyword-only argument: 'open_premium'

Сборка интерфейса обёрнута в `try/except` — иначе окно вообще не
открылось бы, — и ошибка ушла в лог, которого никто не читает. Четыре
тысячи тестов при этом были зелёными: они проверяли сборщики и схему
навигации по отдельности, а стык между ними — нет.

Здесь стык и проверяется, причём без Qt: сверяются имена. Конструктору
страницы нужны ключевые аргументы; сборщик зависимостей отдаёт словарь.
Если в конструкторе есть обязательное имя, которого сборщик не даёт,
страница не построится — и тест это скажет.
"""

from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _required_keyword_names(func) -> set[str]:
    """Обязательные ключевые аргументы функции."""
    signature = inspect.signature(func)
    return {
        name
        for name, parameter in signature.parameters.items()
        if name not in ("self", "parent")
        and parameter.default is inspect.Parameter.empty
        and parameter.kind
        in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    }


def _provided_keys(spec) -> set[str]:
    """Что сборщик кладёт в kwargs страницы.

    Читаем возвращаемый словарь по исходнику: вызвать сборщик нельзя —
    он ждёт живые сервисы, а нам нужны только имена.
    """
    source = inspect.getsource(spec.builder)
    keys: set[str] = set()
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith('"') and '":' in stripped:
            keys.add(stripped.split('"')[1])
    return keys


class PageConstructorContractTests(unittest.TestCase):
    """Ни одна страница не должна просить того, чего ей не дают."""

    def test_every_page_gets_what_its_constructor_requires(self) -> None:
        from importlib import import_module

        from ui.navigation.schema import PAGE_ROUTE_SPECS
        from ui.page_composition import PAGE_DEPS_BUILDERS

        try:
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:  # pragma: no cover - среда без Qt
            self.skipTest(f"Qt недоступен: {exc}")
        QApplication.instance() or QApplication([])

        for page_name, spec in PAGE_DEPS_BUILDERS.items():
            route = PAGE_ROUTE_SPECS.get(page_name)
            if route is None:
                continue
            with self.subTest(page=page_name.name):
                try:
                    module = import_module(route.module_name)
                except Exception as exc:  # pragma: no cover - зависит от среды
                    self.skipTest(f"{route.module_name} не импортируется: {exc}")
                page_cls = getattr(module, route.class_name)

                required = _required_keyword_names(page_cls.__init__)
                provided = _provided_keys(spec)

                missing = required - provided
                self.assertFalse(
                    missing,
                    f"{route.class_name}: сборщик не передаёт {sorted(missing)}",
                )

    def test_no_page_still_asks_for_the_donation_screen(self) -> None:
        """Именно этот аргумент и оставил окно пустым."""
        root = PROJECT_SRC
        offenders = []
        for path in root.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "open_premium" in text:
                offenders.append(path.relative_to(root).as_posix())

        self.assertEqual(offenders, [])


class BuildFailureIsLoudTests(unittest.TestCase):
    """Провал сборки интерфейса не должен выглядеть как пустое окно."""

    def test_build_failure_is_logged_as_error(self) -> None:
        from main import window_startup

        source = inspect.getsource(window_startup.WindowStartupMixin._deferred_init)

        self.assertIn("build_ui failed", source)
        self.assertIn('"ERROR"', source)


if __name__ == "__main__":
    unittest.main()
