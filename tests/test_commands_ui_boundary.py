from __future__ import annotations

import ast
from pathlib import Path
import unittest


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"

FORBIDDEN_COMMAND_IMPORT_ROOTS = {
    "PyQt6",
    "qfluentwidgets",
    "tray",
    "ui",
}

FORBIDDEN_COMMAND_IMPORT_MODULES = {
    "presets.ui_store",
}


class CommandsUiBoundaryTests(unittest.TestCase):
    def test_command_modules_do_not_import_gui_modules(self) -> None:
        offenders: list[str] = []
        for path in self._iter_command_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            rel_path = path.relative_to(SRC_ROOT).as_posix()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = str(alias.name or "").split(".", 1)[0]
                        if root in FORBIDDEN_COMMAND_IMPORT_ROOTS:
                            offenders.append(f"{rel_path}:{node.lineno}:import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = str(node.module or "")
                    root = module.split(".", 1)[0]
                    if root in FORBIDDEN_COMMAND_IMPORT_ROOTS:
                        offenders.append(f"{rel_path}:{node.lineno}:from {node.module} import ...")
                    if module in FORBIDDEN_COMMAND_IMPORT_MODULES:
                        offenders.append(f"{rel_path}:{node.lineno}:from {node.module} import ...")

        self.assertEqual([], offenders)

    def _iter_command_modules(self) -> list[Path]:
        return sorted(
            path
            for path in SRC_ROOT.rglob("*.py")
            if path.name == "commands.py" or path.name.endswith("_commands.py")
        )


if __name__ == "__main__":
    unittest.main()
