"""Данные пакетов кладут обе сборки, а не только локальная.

Часть файлов лежит ВНУТРИ пакета и читается относительно `__file__`:
`blockcheck/data/domains.txt`, `blockcheck/data/tcp_16_20_targets.json`,
`config/config.json`. Копировать их в корень приложения бесполезно —
код ищет их рядом с собой.

Локальная сборка отдавала их PyInstaller ключом `--add-data`. В сборке
на GitHub такого ключа не было вовсе — ни в ветке Nuitka, ни в ветке
PyInstaller. Выпуск с GitHub уезжал без них.

Заметить это было тяжело: приложение не падает. `blockcheck.targets`
не находит `domains.txt` и молча берёт встроенный список. Со стороны
получается «локальная сборка ведёт себя не так, как та, что с гита», и
разбирается такое долго.

Проверка сверяет три вещи: набор данных одинаков в обоих сборщиках,
ключи для каждого проставлены, и в артефакте есть проверка на месте ли
файлы — чтобы следующая пропажа роняла сборку, а не всплывала жалобой.
"""

from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "windows-release.yml"
LOCAL_BUILD = PROJECT_ROOT / "scripts" / "build_local.ps1"

#: Что обязано попасть внутрь собранного приложения.
PACKAGE_DATA = (
    "blockcheck/data",
    "config/config.json",
)


def _runtime_step() -> str:
    import yaml

    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in document["jobs"]["build"]["steps"]:
        if step.get("name") == "Build canonical runtime":
            return str(step.get("run") or "")
    raise AssertionError("в рабочем процессе нет шага сборки runtime")


class WorkflowTests(unittest.TestCase):
    def test_nuitka_ships_package_data(self) -> None:
        step = _runtime_step()

        self.assertIn("--include-data-dir=src\\blockcheck\\data=", step)
        self.assertIn("--include-data-files=src\\config\\config.json=", step)

    def test_pyinstaller_branch_ships_the_same(self) -> None:
        """Ветка выбирается кнопкой при запуске — обе должны давать одно."""
        step = _runtime_step()

        self.assertIn("--add-data=src\\blockcheck\\data;blockcheck\\data", step)
        self.assertIn("--add-data=src\\config\\config.json;config", step)

    def test_artifact_is_checked_for_package_data(self) -> None:
        """Пропажа обязана ронять сборку, а не всплывать жалобой."""
        step = _runtime_step()

        self.assertIn("domains.txt", step)
        self.assertIn("Сборщик не положил данные пакета", step)


class LocalBuildTests(unittest.TestCase):
    def test_local_build_ships_the_same_data(self) -> None:
        text = LOCAL_BUILD.read_text(encoding="utf-8")

        self.assertIn("src\\blockcheck\\data", text)
        self.assertIn("src\\config\\config.json", text)


class SourceTests(unittest.TestCase):
    def test_the_files_actually_exist(self) -> None:
        """Иначе сверять сборки нечего — данных нет и в исходниках."""
        for relative in PACKAGE_DATA:
            with self.subTest(path=relative):
                self.assertTrue((PROJECT_ROOT / "src" / relative).exists())

    def test_blockcheck_reads_data_next_to_itself(self) -> None:
        """Причина, по которой копирование в корень не помогает."""
        source = (PROJECT_ROOT / "src" / "blockcheck" / "targets.py").read_text(encoding="utf-8")

        self.assertIn("Path(__file__).parent", source)


if __name__ == "__main__":
    unittest.main()
