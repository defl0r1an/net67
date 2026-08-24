"""Никто не должен звать у фасада возможности того, чего у него нет.

Дважды подряд одна и та же поломка. Сначала страница «Логи» требовала
`orchestra_feature`, которого сборщик уже не давал, и раздел не
открывался. Потом я убрал `create_theme_persist_worker` из фасада
внешнего вида, а стартовый шаг продолжал его звать:

    AttributeError: 'AppearanceFeature' object has no attribute
    'create_theme_persist_worker'

Оба раза ошибка вылезала у человека при запуске, а не у меня при
проверке. Причина одна: между «кто зовёт» и «у кого есть» нет никакой
сверки — Python узнаёт об этом только в момент вызова.

Здесь сверка есть, и она статическая. Правило простое и механическое:
имя `<что-то>_feature` означает фасад `<Что-то>Feature`. Все обращения
`<что-то>_feature.атрибут` в исходниках собираются разбором кода, и
каждое имя ищется у соответствующего класса. Qt для этого не нужен —
классы тоже разбираются как текст.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
FACADES_DIR = SRC / "app" / "feature_facades"

#: Имя переменной → имя класса фасада.
FEATURE_CLASSES = {
    "appearance_feature": "AppearanceFeature",
    "blockcheck_feature": "BlockcheckFeature",
    "diagnostics_feature": "DiagnosticsFeature",
    "dns_feature": "DnsFeature",
    "hosts_feature": "HostsFeature",
    "lists_feature": "ListsFeature",
    "logs_feature": "LogsFeature",
    "presets_feature": "PresetsFeature",
    "profile_feature": "ProfileFeature",
    "program_settings_feature": "ProgramSettingsFeature",
    "tray_feature": "TrayFeature",
    "updater_feature": "UpdaterFeature",
    "window_geometry_feature": "WindowGeometryFeature",
}


def _class_attributes(class_name: str) -> set[str] | None:
    """Что у класса есть: методы, свойства и поля, назначенные в __init__."""
    for path in FACADES_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ClassDef) and node.name == class_name):
                continue

            names: set[str] = set()
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(item.name)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    names.add(item.target.id)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            names.add(target.id)

            # self.что-то = ... внутри любого метода
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                    if sub.value.id == "self" and isinstance(sub.ctx, ast.Store):
                        names.add(sub.attr)

            return names
    return None


def _feature_attribute_uses() -> list[tuple[Path, int, str, str]]:
    """Все обращения вида `<что-то>_feature.атрибут` в исходниках."""
    uses: list[tuple[Path, int, str, str]] = []
    for path in SRC.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            base = node.value
            if not (isinstance(base, ast.Name) and base.id in FEATURE_CLASSES):
                continue
            uses.append((path, node.lineno, base.id, node.attr))
    return uses


class FeatureAttributeContractTests(unittest.TestCase):
    def test_every_used_attribute_exists_on_its_facade(self) -> None:
        uses = _feature_attribute_uses()
        self.assertTrue(uses, "обращений к фасадам не нашлось — разбор сломался")

        missing: list[str] = []
        for path, lineno, variable, attribute in uses:
            class_name = FEATURE_CLASSES[variable]
            available = _class_attributes(class_name)
            if available is None:
                continue
            if attribute.startswith("_"):
                continue
            if attribute not in available:
                missing.append(
                    f"{path.relative_to(SRC).as_posix()}:{lineno}: "
                    f"{class_name} не имеет «{attribute}»"
                )

        self.assertEqual(missing, [], "\n".join(missing))

    def test_theme_manager_no_longer_asks_for_the_removed_worker(self) -> None:
        """Именно этот вызов и валился при запуске."""
        source = (SRC / "main" / "window_startup_services.py").read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )

        self.assertNotIn("create_theme_persist_worker", code)

    def test_theme_manager_constructor_matches_its_call_site(self) -> None:
        theme = (SRC / "ui" / "theme.py").read_text(encoding="utf-8")
        tree = ast.parse(theme)

        required: set[str] = set()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ClassDef) and node.name == "ThemeManager"):
                continue
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    for arg, default in zip(item.args.kwonlyargs, item.args.kw_defaults or []):
                        if default is None:
                            required.add(arg.arg)

        service = (SRC / "main" / "window_startup_services.py").read_text(encoding="utf-8")
        passed: set[str] = set()
        for node in ast.walk(ast.parse(service)):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "ThemeManager":
                passed = {kw.arg for kw in node.keywords if kw.arg}

        self.assertFalse(
            required - passed,
            f"ThemeManager требует {sorted(required - passed)}, а вызов их не передаёт",
        )


if __name__ == "__main__":
    unittest.main()
