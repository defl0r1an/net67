"""Архитектурные проверки договора «Пресет — точка истины» ловят нарушения.

Каждая проверка получает синтетический исходник с нарушением и должна его
найти, а на правильном варианте — промолчать. Отдельно: весь проект проходит
app.architecture_checks, и модуль договора импортируется без зависимостей
(его читает CI на голом python3).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from app import architecture_checks as checks
from presets.preset_contract import GENERATED_CONFIG_EXEMPTIONS


REPO_ROOT = checks.REPO_ROOT


def _source(rel_path: str, code: str) -> tuple[Path, str]:
    return REPO_ROOT / rel_path, textwrap.dedent(code)








# Тесты отдельных проверок исходного проекта (запуск winws2 ровно с одним
# @config, владение записью файла пресета, подготовка запуска) отсюда убраны:
# в net67 свой app/architecture_checks.py, этих функций в нём нет. Проверка
# всего проекта ниже гоняет набор net67.
class WholeProjectTests(unittest.TestCase):
    def test_project_passes_architecture_checks(self) -> None:
        problems = checks.run_checks()
        self.assertEqual([problem.format() for problem in problems], [])

    def test_contract_module_imports_without_project_dependencies(self) -> None:
        code = (
            "import sys; sys.path.insert(0, 'src'); import presets.preset_contract; "
            "print(sorted({m.split('.')[0] for m in sys.modules} & {'PyQt6', 'log', 'settings', 'profile', 'requests'}))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
