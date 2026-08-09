"""Каждая страница обязана иметь билдер зависимостей.

Проверка есть и в рантайме — validate_page_deps_builder_coverage(), — но
срабатывает она уже при построении окна: приложение запускается, показывает
пустой экран и красную плашку «Missing page deps builders».

Ровно так и вышло: страницы VPN и «Конфигурации» добавили в схему
навигации, а в PAGE_DEPS_BUILDERS внести забыли. Тест ловит это статически,
до сборки.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

COMPOSITION = PROJECT_SRC / "ui" / "page_composition.py"
NAV_SCHEMA = PROJECT_SRC / "ui" / "navigation" / "schema.py"


def _page_names_in(path: Path, *, inside_dict_only: bool) -> set[str]:
    """Имена PageName.X, встречающиеся в файле как ключи словаря."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key in node.keys:
            if (
                isinstance(key, ast.Attribute)
                and isinstance(key.value, ast.Name)
                and key.value.id == "PageName"
            ):
                found.add(key.attr)

    _ = inside_dict_only
    return found


class PageDepsCoverageTests(unittest.TestCase):
    def test_every_route_has_a_deps_builder(self) -> None:
        routes = _page_names_in(NAV_SCHEMA, inside_dict_only=True)
        builders = _page_names_in(COMPOSITION, inside_dict_only=True)

        self.assertTrue(routes, "не удалось разобрать PAGE_ROUTE_SPECS")
        self.assertTrue(builders, "не удалось разобрать PAGE_DEPS_BUILDERS")

        missing = routes - builders
        self.assertEqual(
            missing,
            set(),
            "у этих страниц нет билдера зависимостей — приложение упадёт "
            f"при построении интерфейса: {sorted(missing)}",
        )

    def test_new_pages_are_covered(self) -> None:
        """Явная проверка страниц, добавленных при доработке."""
        builders = _page_names_in(COMPOSITION, inside_dict_only=True)

        for page in ("VPN", "CONFIGS"):
            self.assertIn(page, builders)

    def test_runtime_validation_helper_exists(self) -> None:
        source = COMPOSITION.read_text(encoding="utf-8")

        self.assertIn("def validate_page_deps_builder_coverage", source)


class BrandingCoverageTests(unittest.TestCase):
    """Название продукта не должно оставаться зашитым в коде."""

    def test_no_hardcoded_product_name_in_ui(self) -> None:
        offenders: list[str] = []
        # Имена движков (Zapret 1/2) и файлов установщика на сервере
        # обновлений — не бренд, их проверяем отдельно и не трогаем.
        allowed_substrings = (
            "Zapret 1",
            "Zapret 2",
            "Zapret2Setup",
            "zapret-win-bundle",
            "zapretgui",  # только в комментариях о старых маркерах hosts
        )

        for path in (
            PROJECT_SRC / "ui" / "fluent_app_window.py",
            PROJECT_SRC / "tray.py",
            PROJECT_SRC / "support_request_bundle.py",
        ):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "Zapret" not in line:
                    continue
                if any(token in line for token in allowed_substrings):
                    continue
                offenders.append(f"{path.name}:{number}: {line.strip()}")

        self.assertEqual(offenders, [], "название продукта зашито вместо APP_NAME")


if __name__ == "__main__":
    unittest.main()
