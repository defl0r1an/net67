"""Раскладывает картинки флагов в `ico/flags/` под коды стран.

Список серверов ищет файлы вида `nl.png` — по коду страны. Этот скрипт
приносит их из открытого набора и переименовывает: в наборах имена
кодируются точками Unicode (`1f1f3-1f1f1.png` это 🇳🇱), и вручную
разбирать двести пятьдесят таких имён никто не станет.

## Что можно скачать этим скриптом

Только наборы со свободной лицензией:

    twemoji  — набор Twitter, CC-BY 4.0. Плоский рисунок, ближе всего
               к Apple по виду флагов: те же прямоугольники с полосами.
    noto     — Noto Color Emoji от Google, SIL OFL.

Эмодзи Apple сюда не входят и не могут: они часть macOS, отдельно не
распространяются, и зеркала, которые их раздают, делают это без права.
Если нужны именно они — берите со своего Mac, там у вас лицензионная
копия. Как это сделать, написано ниже в разделе «Про Apple».

## Запуск

    py -3.14 scripts\\fetch_flags.py
    py -3.14 scripts\\fetch_flags.py --source noto --size 72

## Про Apple

Флаги лежат в шрифте `/System/Library/Fonts/Apple Color Emoji.ttc`.
Достать их можно на самой macOS — например, открыть «Просмотр
шрифтов», найти нужный символ и сохранить, или прогнать шрифт любым
инструментом для извлечения растровых таблиц. Скопировать сам файл
шрифта на Windows нельзя: он там не отрисуется, формат таблиц свой.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import urlopen


#: Откуда берём картинки. Только свободные наборы.
SOURCES = {
    "twemoji": (
        "https://raw.githubusercontent.com/jdecked/twemoji/main/assets/72x72/{name}.png",
        "CC-BY 4.0, Twitter/jdecked",
    ),
    "noto": (
        "https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/{size}/emoji_u{name_underscore}.png",
        "SIL OFL, Google",
    ),
}

#: Сдвиг от латинской буквы к региональному индикатору.
_BASE = 0x1F1E6
_A = ord("A")


def codepoints(code: str) -> tuple[str, str]:
    """Имя файла в наборе: `1f1f3-1f1f1` и вариант через подчёркивание."""
    points = [_BASE + ord(ch) - _A for ch in code.upper()]
    hyphen = "-".join(f"{point:x}" for point in points)
    return (hyphen, hyphen.replace("-", "_"))


def _flags_module():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    import vpn.flags as flags

    return flags


def all_codes() -> list[str]:
    """Все страны по ISO 3166-1 — двести сорок девять штук."""
    return sorted(_flags_module().ISO_COUNTRY_CODES)


def known_codes() -> list[str]:
    """Только те, для которых у приложения есть перевод названия."""
    return sorted(_flags_module().COUNTRY_NAMES)


def fetch(url: str) -> bytes | None:
    try:
        with urlopen(url, timeout=20) as response:
            if response.status != 200:
                return None
            return response.read()
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Скачивает флаги стран в ico/flags")
    parser.add_argument("--source", choices=sorted(SOURCES), default="twemoji")
    parser.add_argument("--size", default="72", help="размер для noto: 72 или 128")
    parser.add_argument(
        "--only-known",
        action="store_true",
        help="только страны с переводом названия, а не все по ISO",
    )
    args = parser.parse_args(argv)

    template, licence = SOURCES[args.source]
    print(f"Набор: {args.source} ({licence})")

    codes = known_codes() if args.only_known else all_codes()
    print(f"Стран к загрузке: {len(codes)}")

    target = Path(__file__).resolve().parents[1] / "ico" / "flags"
    target.mkdir(parents=True, exist_ok=True)

    saved = 0
    missing: list[str] = []
    for code in codes:
        hyphen, underscore = codepoints(code)
        url = template.format(name=hyphen, name_underscore=underscore, size=args.size)
        data = fetch(url)
        if not data:
            missing.append(code)
            continue
        (target / f"{code.lower()}.png").write_bytes(data)
        saved += 1
        print(f"  {code} -> {code.lower()}.png")

    print()
    print(f"Сохранено: {saved}")
    if missing:
        # Промахи бывают: в наборах нет флагов для территорий без своего
        # флага — Антарктиды, Буве, отдельных заморских владений.
        print(f"Нет в наборе ({len(missing)}): {', '.join(missing)}")
    print(f"Папка: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
