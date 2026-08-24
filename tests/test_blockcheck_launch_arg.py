"""Диагностика запускает winws2 так же, как основной обход.

winws2 — cygwin-бинарник, и аргумент `@путь с пробелом` он не разбирает:
печатает баннер версии и выходит с кодом 1. Для основного запуска это
давно обходится через `at_config_launch_arg`, а сканер стратегий собирал
аргумент сам, строкой `f"@{preset_path}"`.

Итог: диагностика падала на каждой стратегии подряд у всех, у кого
программа лежит по пути с пробелом — а это и `C:\\Program Files\\net67`
после установки, и любая папка вроде `AyuGram Desktop`:

    FAIL: winws2 crashed (exit=1): failed to split command line options
    from file 'C:\\...\\AyuGram Desktop\\...\\blockcheck_probe.txt'

Основной обход при этом работал, поэтому выглядело как поломка именно
диагностики.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
SCANNER = SRC / "blockcheck" / "strategy_scanner.py"


def _launch_function() -> ast.FunctionDef:
    tree = ast.parse(SCANNER.read_text(encoding="utf-8"), filename=str(SCANNER))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_launch_winws2":
            return node
    raise AssertionError("_launch_winws2 не найдена в сканере стратегий")


class BlockcheckLaunchArgTests(unittest.TestCase):
    def test_launch_uses_the_shared_at_config_helper(self) -> None:
        source = ast.unparse(_launch_function())

        self.assertIn(
            "at_config_launch_arg",
            source,
            "сканер собирает аргумент @файл сам — путь с пробелом снова сломает запуск",
        )

    def test_launch_does_not_glue_the_path_by_hand(self) -> None:
        """Никаких f'@{...}' в запуске: ровно эта строка и падала."""
        for node in ast.walk(_launch_function()):
            if not isinstance(node, ast.JoinedStr):
                continue
            rendered = ast.unparse(node)
            self.assertFalse(
                rendered.startswith("f'@") or rendered.startswith('f"@'),
                f"путь склеен вручную: {rendered}",
            )

    def test_helper_strips_the_space_for_a_path_under_the_work_dir(self) -> None:
        import os
        import sys

        if str(SRC) not in sys.path:
            sys.path.insert(0, str(SRC))

        from winws_runtime.runners.preset_runner_support import at_config_launch_arg

        work_dir = os.path.join(os.sep, "opt", "net 67")
        preset = os.path.join(work_dir, "blockcheck_probe.txt")

        arg = at_config_launch_arg(preset, work_dir)

        self.assertEqual(arg, "@blockcheck_probe.txt")
        self.assertNotIn(" ", arg)


if __name__ == "__main__":
    unittest.main()
