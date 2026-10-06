"""Панель ошибок выглядит тревожно только когда есть повод.

Красный треугольник и пустая красная рамка висели на вкладке «Логи»
всегда — и при нуле ошибок тоже. Это дважды плохо: чистая работа
программы выглядела как поломка, а настоящая ошибка ничем не отличалась
бы от обычного вида панели.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from log.ui.runtime_helpers import (  # noqa: E402
    ERRORS_ICON_CLEAN,
    ERRORS_ICON_PROBLEM,
    errors_count_text,
    errors_panel_view,
)


def _tr(key: str, default: str) -> str:
    return default


class ErrorsPanelViewTests(unittest.TestCase):
    def test_clean_state_shows_a_green_check_and_nothing_else(self) -> None:
        view = errors_panel_view(count=0, is_light=False)

        self.assertFalse(view.has_errors)
        self.assertEqual(view.icon_name, ERRORS_ICON_CLEAN)
        self.assertFalse(view.show_text, "пустая рамка не должна показываться")
        self.assertFalse(view.show_clear_button, "очищать нечего")

    def test_first_error_brings_back_the_warning_triangle_and_the_frame(self) -> None:
        view = errors_panel_view(count=1, is_light=False)

        self.assertTrue(view.has_errors)
        self.assertEqual(view.icon_name, ERRORS_ICON_PROBLEM)
        self.assertTrue(view.show_text)
        self.assertTrue(view.show_clear_button)

    def test_icon_colour_differs_between_themes(self) -> None:
        # Один и тот же зелёный на светлой и тёмной теме читается плохо.
        light = errors_panel_view(count=0, is_light=True)
        dark = errors_panel_view(count=0, is_light=False)
        self.assertNotEqual(light.icon_color, dark.icon_color)

        light_err = errors_panel_view(count=2, is_light=True)
        dark_err = errors_panel_view(count=2, is_light=False)
        self.assertNotEqual(light_err.icon_color, dark_err.icon_color)

    def test_negative_and_none_count_read_as_clean(self) -> None:
        self.assertFalse(errors_panel_view(count=-1, is_light=False).has_errors)
        self.assertFalse(errors_panel_view(count=0, is_light=True).has_errors)

    def test_zero_is_named_in_words(self) -> None:
        self.assertEqual(errors_count_text(_tr, 0), "Ошибок нет")
        self.assertEqual(errors_count_text(_tr, 4), "Ошибок: 4")


class ErrorsPanelWiringTests(unittest.TestCase):
    """Состояние должно применяться там, где число ошибок меняется."""

    def _method_source(self, name: str) -> str:
        path = SRC / "log" / "ui" / "page.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.unparse(node)
        raise AssertionError(f"{name} не найден в странице логов")

    def test_adding_an_error_repaints_the_panel(self) -> None:
        self.assertIn("_apply_errors_panel_state", self._method_source("_add_errors"))

    def test_clearing_errors_repaints_the_panel(self) -> None:
        self.assertIn("_apply_errors_panel_state", self._method_source("_clear_errors"))

    def test_panel_starts_hidden_in_the_builder(self) -> None:
        path = SRC / "log" / "ui" / "logs_build.py"
        source = path.read_text(encoding="utf-8")

        self.assertIn("errors_text.setVisible(False)", source)
        self.assertIn("clear_errors_btn.setVisible(False)", source)

    def test_theme_no_longer_hardcodes_the_warning_icon(self) -> None:
        """Значок зависит от числа ошибок, а не только от темы."""
        source = self._method_source("_apply_page_theme")

        self.assertNotIn("fa5s.exclamation-triangle", source)
        self.assertIn("_apply_errors_panel_state", source)


if __name__ == "__main__":
    unittest.main()
