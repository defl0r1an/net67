"""Генератор бандла simple-иконок для профилей.

Извлекает из пакета simplepycons ТОЛЬКО те SVG, которые реально используются
каталогом иконок профилей (profile/icons.py), и записывает их в сгенерированный
модуль src/profile/ui/simple_icons_bundle.py.

Зачем: импорт simplepycons тянет ~3400 модулей (~2.6с и десятки МБ памяти),
поэтому в рантайме приложения он не используется вообще. simplepycons нужен
только на машине разработчика для регенерации бандла.

Запуск (из корня репозитория):
    PYTHONPATH=src python tools/generate_profile_icon_bundle.py

После добавления нового сервиса с иконкой "simple:<slug>:<fallback>" в
profile/icons.py — перезапустить генератор. Тест
tests/test_profile_icon_bundle.py упадёт, если бандл не покрывает каталог.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

BUNDLE_PATH = PROJECT_SRC / "profile" / "ui" / "simple_icons_bundle.py"

_HEADER = '''"""Бандл simple-иконок профилей. СГЕНЕРИРОВАНО — НЕ редактировать вручную.

Источник: пакет simplepycons (Simple Icons, CC0). Здесь лежат только SVG,
которые реально используются каталогом profile/icons.py — благодаря этому
рантайм не импортирует simplepycons (~3400 модулей, ~2.6с).

Регенерация: PYTHONPATH=src python tools/generate_profile_icon_bundle.py
"""
from __future__ import annotations


# slug -> (primary_color_hex, raw_svg)
SIMPLE_ICON_SVGS: dict[str, tuple[str, str]] = {
'''

_FOOTER = '''}


__all__ = ["SIMPLE_ICON_SVGS"]
'''


def collect_catalog_slugs() -> list[str]:
    """Собирает уникальные simple-слаги из каталога иконок профилей."""
    import profile.icons as profile_icons

    slugs: set[str] = set()
    for attr_name in dir(profile_icons):
        attr = getattr(profile_icons, attr_name)
        if not isinstance(attr, dict):
            continue
        for value in attr.values():
            icon_name = str(getattr(value, "icon_name", "") or "")
            if not icon_name.startswith("simple:"):
                continue
            slug = icon_name.removeprefix("simple:").partition(":")[0]
            slug = slug.strip().lower().replace("-", "")
            if slug:
                slugs.add(slug)
    return sorted(slugs)


def extract_icon(all_icons, slug: str) -> tuple[str, str] | None:
    try:
        icon = all_icons[slug]
    except Exception:
        getter = getattr(all_icons, f"get_{slug}_icon", None)
        if not callable(getter):
            return None
        try:
            icon = getter()
        except Exception:
            return None
    raw_svg = str(getattr(icon, "raw_svg", "") or "").strip()
    if not raw_svg:
        return None
    primary_color = str(getattr(icon, "primary_color", "") or "").lstrip("#").strip()
    return (f"#{primary_color}" if primary_color else "", raw_svg)


def main() -> int:
    slugs = collect_catalog_slugs()
    if not slugs:
        print("Каталог иконок не дал ни одного simple-слага — ничего не делаю.", file=sys.stderr)
        return 1

    from simplepycons import all_icons

    lines: list[str] = [_HEADER]
    missing: list[str] = []
    for slug in slugs:
        entry = extract_icon(all_icons, slug)
        if entry is None:
            missing.append(slug)
            continue
        primary_color, raw_svg = entry
        lines.append(f"    {slug!r}: ({primary_color!r}, {raw_svg!r}),\n")
    lines.append(_FOOTER)

    if missing:
        print(f"ОШИБКА: в simplepycons не найдены слаги: {', '.join(missing)}", file=sys.stderr)
        return 1

    BUNDLE_PATH.write_text("".join(lines), encoding="utf-8")
    print(f"Записан {BUNDLE_PATH.relative_to(PROJECT_ROOT)}: {len(slugs)} иконок.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
