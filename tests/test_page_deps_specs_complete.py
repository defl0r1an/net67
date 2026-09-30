"""Каждой странице хватает того, что ей раздаёт page_composition.

После слияния с zapret из спецификации главной страницы выпало действие
start_onboarding_tour. Сборщик страницы требует его обязательным
аргументом, build_ui падал с TypeError, и окно оставалось чёрным. Ни один
тест этого не ловил: страницы в них собираются с подставленными deps, а не
через PAGE_DEPS_BUILDERS.

Здесь проверяется сама раздача: обязательные аргументы каждого сборщика
покрыты его PageDepsSpec, а всё, что спецификация просит, окно отдаёт.
"""

from __future__ import annotations

import ast
import inspect
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _window_sources_keys() -> tuple[set[str], set[str]]:
    """Ключи feature_deps и actions из build_window_page_deps_sources."""
    tree = ast.parse((SRC / "main" / "window_page_deps_setup.py").read_text(encoding="utf-8"))
    features: set[str] = set()
    actions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in ("feature_deps", "actions") and isinstance(node.value, ast.Dict):
            keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
            (features if node.arg == "feature_deps" else actions).update(keys)
    return features, actions


class PageDepsSpecsCompleteTests(unittest.TestCase):
    def test_every_required_builder_argument_is_provided(self) -> None:
        from ui.page_composition import PAGE_DEPS_BUILDERS

        problems: list[str] = []
        for page_name, spec in PAGE_DEPS_BUILDERS.items():
            provided = {"page_name"}
            provided.update(f"{name}_feature" for name in spec.features)
            provided.update(spec.actions)
            if spec.include_ui_state_store:
                provided.add("ui_state_store")
            for name, param in inspect.signature(spec.builder).parameters.items():
                if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
                    continue
                if param.default is inspect.Parameter.empty and name not in provided:
                    problems.append(f"{page_name.name}: {spec.builder.__name__} ждёт {name}")
        self.assertEqual(problems, [])

    def test_every_requested_dependency_is_published_by_the_window(self) -> None:
        from ui.page_composition import PAGE_DEPS_BUILDERS

        features, actions = _window_sources_keys()
        self.assertTrue(features and actions, "не нашёл feature_deps/actions в window_page_deps_setup.py")
        problems: list[str] = []
        for page_name, spec in PAGE_DEPS_BUILDERS.items():
            problems.extend(f"{page_name.name}: нет фичи {name}" for name in spec.features if name not in features)
            problems.extend(f"{page_name.name}: нет действия {name}" for name in spec.actions if name not in actions)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
