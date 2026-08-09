"""Раскладка ресурсов в собранном artifact.

Собранное приложение искало пресеты в artifact\\presets\\winws2_builtin, а
скрипт сборки копировал туда src\\presets целиком — это Python-пакет, а не
папка ресурсов. В артефакте оказывались commands.py и file_store.py, и
приложение честно сообщало, что пресетов нет.

Тест сверяет карту копирования в scripts/build_local.ps1 с тем, что
реально спрашивает код: EnginePaths.from_root в core/paths.py и
_strategy_catalogs_root в profile/strategy_catalog.py.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_local.ps1"


def _script() -> str:
    return BUILD_SCRIPT.read_text(encoding="utf-8")


def _copy_pairs() -> dict[str, str]:
    """Пары @("источник", "цель") из блока $pairs."""
    text = _script()
    start = text.index("$pairs = @(")
    end = text.index(")", text.index("@(\"bin\"", start))
    block = text[start:end]
    return {
        source: target
        for source, target in re.findall(r'@\("([^"]+)",\s*"([^"]+)"\)', block)
    }


class BuildResourceMapTests(unittest.TestCase):
    def setUp(self) -> None:
        if not BUILD_SCRIPT.exists():
            self.skipTest("scripts/build_local.ps1 отсутствует")

    def test_builtin_presets_go_to_engine_specific_folders(self) -> None:
        pairs = _copy_pairs()

        self.assertEqual(
            pairs.get(r"src\presets\builtin\winws1"),
            r"presets\winws1_builtin",
        )
        self.assertEqual(
            pairs.get(r"src\presets\builtin\winws2"),
            r"presets\winws2_builtin",
        )

    def test_python_packages_are_not_copied_as_resources(self) -> None:
        """src\\presets, src\\profile и src\\lists — пакеты, не ресурсы."""
        pairs = _copy_pairs()

        for package in (r"src\presets", r"src\profile", r"src\lists"):
            self.assertNotIn(
                package,
                pairs,
                f"{package} — Python-пакет; копирование его в корень артефакта "
                "и было причиной «пресеты не найдены»",
            )

    def test_strategy_catalogs_are_copied(self) -> None:
        pairs = _copy_pairs()

        self.assertEqual(
            pairs.get(r"src\profile\strategy_catalogs"),
            r"profile\strategy_catalogs",
        )

    def test_package_data_uses_add_data(self) -> None:
        """blockcheck читает data через __file__, копия в корень не поможет."""
        text = _script()

        self.assertIn(r"src\blockcheck\data", text)
        self.assertIn("--add-data=", text)

    def test_build_fails_loudly_when_presets_missing(self) -> None:
        self.assertIn("No builtin presets were copied", _script())


class BuildMapMatchesRuntimeTests(unittest.TestCase):
    """Цели копирования должны совпадать с путями, которые ищет код."""

    def test_targets_match_engine_paths(self) -> None:
        from core.paths import AppPaths
        from settings.mode import ENGINE_WINWS1, ENGINE_WINWS2

        root = Path("C:/app")
        app_paths = AppPaths(user_root=root, local_root=root)
        pairs = _copy_pairs()

        for engine, source in (
            (ENGINE_WINWS1, r"src\presets\builtin\winws1"),
            (ENGINE_WINWS2, r"src\presets\builtin\winws2"),
        ):
            engine_paths = app_paths.engine_paths(engine)
            expected = engine_paths.builtin_presets_dir.relative_to(root)
            actual = Path(pairs[source].replace("\\", "/"))

            self.assertEqual(
                actual,
                Path(expected.as_posix()),
                f"скрипт кладёт пресеты {engine} не туда, где их ищет AppPaths",
            )

            user_expected = engine_paths.user_presets_dir.relative_to(root)
            self.assertIn(
                str(user_expected).replace("/", "\\"),
                _script(),
                f"папка пользовательских пресетов {engine} не создаётся",
            )

    def test_strategy_catalog_target_matches_runtime(self) -> None:
        import profile.strategy_catalog as strategy_catalog

        source = strategy_catalog.__file__
        text = Path(source).read_text(encoding="utf-8")

        # Путь собирается как user_root / "profile" / "strategy_catalogs".
        self.assertIn('"profile" / "strategy_catalogs"', text)

        pairs = _copy_pairs()
        self.assertEqual(
            Path(pairs[r"src\profile\strategy_catalogs"].replace("\\", "/")),
            Path("profile/strategy_catalogs"),
        )


class ShippedResourcesExistTests(unittest.TestCase):
    """Источники из карты копирования должны существовать в репозитории."""

    def test_builtin_presets_are_present(self) -> None:
        for engine in ("winws1", "winws2"):
            folder = PROJECT_SRC / "presets" / "builtin" / engine
            self.assertTrue(folder.is_dir(), f"нет папки {folder}")
            self.assertTrue(
                list(folder.glob("*.txt")),
                f"в {folder} нет ни одного пресета",
            )

    def test_strategy_catalogs_are_present(self) -> None:
        root = PROJECT_SRC / "profile" / "strategy_catalogs"
        self.assertTrue(root.is_dir())

        for engine in ("winws1", "winws2"):
            self.assertTrue(
                list((root / engine).glob("*.txt")),
                f"нет каталогов стратегий для {engine}",
            )


if __name__ == "__main__":
    unittest.main()
