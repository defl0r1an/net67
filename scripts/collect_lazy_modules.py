"""Печатает список динамически загружаемых модулей — по одному на строку.

Страницы и фасады грузятся через import_module по строке, поэтому
статический анализ PyInstaller их не видит. Список отсюда передаётся
сборщику как --hidden-import.

Вынесено отдельным файлом намеренно: встроенный в PowerShell-скрипт
Python-код ломался о разбор here-string в Windows PowerShell 5.1.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    from app.feature_facades import iter_lazy_feature_facade_modules
    from ui.page_registry import iter_lazy_page_modules

    modules = set(iter_lazy_feature_facade_modules()) | set(iter_lazy_page_modules())

    # Импортируются внутри функций. PyInstaller обычно такое находит, но
    # промах означал бы, что в собранном приложении не откроются кнопка
    # «Включить» и мастер первого запуска.
    modules |= {
        "oneclick.ui.button",
        "oneclick.deps",
        "oneclick.runner",
        "oneclick.plans",
        "wizard.ui.dialog",
        "wizard.apply",
        "wizard.plans",
    }

    for name in sorted(modules):
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
