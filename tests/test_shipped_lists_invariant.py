"""Инвариант поставки списков.

Каждый lists/<file>.txt, на который ссылаются all_profiles.txt и builtin
preset-ы, обязан лежать в репозитории либо генерироваться приложением из
встроенных баз. Иначе после установки пресет падает с «Preset содержит
ссылки на отсутствующие файлы» (история: netrogat.txt удалялся сборкой
как generated, но не регенерировался).

## Проверка была мёртвой

Она смотрела в приватный репозиторий исходного проекта, папку рядом с
этой. Его здесь нет и не будет, так что `setUp` молча пропускал оба
теста, а инвариант не проверялся никогда.

Между тем ровно эта беда случилась: списки один раз уже пропали из
поставки, потому что их исключало правило `/lists/` в .gitignore.
Приложение запускалось и выглядело рабочим, а обход не работал.

Теперь проверка смотрит туда, где списки лежат на самом деле, —
в `lists/` этого репозитория, откуда их и забирает сборка.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PUBLIC_ROOT = Path(__file__).resolve().parents[1]
ALL_PROFILES_PATH = PUBLIC_ROOT / "src" / "profile" / "templates" / "all_profiles.txt"
BUILTIN_PRESETS_ROOT = PUBLIC_ROOT / "src" / "presets" / "builtin"
SHIPPED_LISTS_DIR = PUBLIC_ROOT / "lists"

# Эти итоговые файлы приложение собирает само из встроенных баз
# (lists/core/embedded_defaults.py), в поставке их быть не должно.
RUNTIME_GENERATED_LIST_NAMES = frozenset({"other.txt", "ipset-all.txt", "ipset-ru.txt"})

_LIST_REFERENCE_RE = re.compile(r"lists[/\\]([A-Za-z0-9_.\- ]+?\.txt)", flags=re.IGNORECASE)


def _referenced_list_names(text: str) -> set[str]:
    names: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for match in _LIST_REFERENCE_RE.finditer(line):
            names.add(match.group(1).strip().lower())
    return names


def _collect_required_list_names() -> dict[str, set[str]]:
    """Возвращает имя списка -> множество источников, которые на него ссылаются."""
    required: dict[str, set[str]] = {}

    sources: list[tuple[str, Path]] = [("all_profiles.txt", ALL_PROFILES_PATH)]
    sources.extend(
        (str(path.relative_to(BUILTIN_PRESETS_ROOT)), path)
        for path in sorted(BUILTIN_PRESETS_ROOT.rglob("*.txt"))
    )

    for source_name, path in sources:
        text = path.read_text(encoding="utf-8", errors="replace")
        for list_name in _referenced_list_names(text):
            required.setdefault(list_name, set()).add(source_name)
    return required


class ShippedListsInvariantTest(unittest.TestCase):
    def setUp(self) -> None:
        # Пропусков здесь быть не должно: оба пути — внутри репозитория.
        # Пропуск означал бы, что пропал сам предмет проверки.
        self.assertTrue(ALL_PROFILES_PATH.is_file(), f"нет {ALL_PROFILES_PATH}")
        self.assertTrue(SHIPPED_LISTS_DIR.is_dir(), f"нет {SHIPPED_LISTS_DIR}")

    def test_every_referenced_list_file_is_shipped_or_runtime_generated(self) -> None:
        shipped = {path.name.lower() for path in SHIPPED_LISTS_DIR.glob("*.txt")}
        available = shipped | {name.lower() for name in RUNTIME_GENERATED_LIST_NAMES}

        missing = {
            list_name: sorted(sources)
            for list_name, sources in sorted(_collect_required_list_names().items())
            if list_name not in available
        }

        self.assertEqual(
            missing,
            {},
            "Списки, на которые ссылаются профили/пресеты, отсутствуют в поставке "
            f"({SHIPPED_LISTS_DIR}): {missing}",
        )

    def test_runtime_generated_lists_can_be_rebuilt(self) -> None:
        """Приложение обязано уметь собрать эти списки само.

        Прежняя проверка требовала обратного — чтобы их не было в
        поставке: сборка исходного проекта их чистила. Здесь они лежат
        в репозитории как обычные файлы, и требование потеряло смысл.

        Смысл сохранился у другой половины правила. Эти списки приложение
        пересобирает из встроенных баз — при обновлении, при сбросе, при
        первом запуске на чистой машине. Пропадёт встроенная база —
        пересобирать станет нечем, и пресеты снова начнут падать на
        отсутствующем файле.
        """
        from lists.core import embedded_defaults

        for name in ("get_ipset_all_base_text", "get_ipset_ru_base_text"):
            with self.subTest(source=name):
                builder = getattr(embedded_defaults, name, None)
                self.assertTrue(callable(builder), f"нет источника {name}")
                self.assertTrue(str(builder() or "").strip(), f"{name} пуст")


if __name__ == "__main__":
    unittest.main()
