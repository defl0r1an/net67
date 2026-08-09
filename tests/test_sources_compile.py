"""Каждый модуль в src должен компилироваться.

Два файла обновлятора лежали сломанными: массовая правка брендинга
поставила `from branding import APP_NAME` выше `from __future__ import
annotations`, а это SyntaxError. Модули загружаются лениво, поэтому
приложение стартовало нормально и падало бы только при проверке
обновлений — то есть у пользователя, а не на сборке.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"


def _sources() -> list[Path]:
    return [
        path
        for path in PROJECT_SRC.rglob("*.py")
        if "__pycache__" not in path.parts
    ]


class SourcesCompileTests(unittest.TestCase):
    def test_every_module_parses(self) -> None:
        broken: list[str] = []

        for path in _sources():
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as error:
                relative = path.relative_to(PROJECT_SRC)
                broken.append(f"{relative}:{error.lineno}: {error.msg}")

        self.assertEqual(broken, [], "модули не компилируются:\n" + "\n".join(broken))

    def test_future_import_stays_first(self) -> None:
        """`from __future__` обязан идти раньше любого другого импорта."""
        offenders: list[str] = []

        for path in _sources():
            lines = path.read_text(encoding="utf-8").splitlines()
            future_at = next(
                (
                    number
                    for number, line in enumerate(lines)
                    if line.startswith("from __future__ import")
                ),
                None,
            )
            if future_at is None:
                continue

            earlier = [
                number + 1
                for number, line in enumerate(lines[:future_at])
                if line.startswith(("import ", "from "))
            ]
            if earlier:
                relative = path.relative_to(PROJECT_SRC)
                offenders.append(f"{relative}: импорт в строках {earlier}")

        self.assertEqual(
            offenders,
            [],
            "импорт стоит выше from __future__:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
