"""Картинки установщика net67: боковая панель и значок в шапке страниц.

    py tools\\make_installer_art.py

Установщик собирает Inno Setup, и без своих картинок он показывает
стандартные: синий компьютер с коробкой. Программа при этом чёрно-белая,
и первое, что человек видел, — окно из другого набора.

Картинки рисуются из значка программы (`ico/net67.ico`) и лежат в
`installer/art/`. Они в git: сборке на GitHub рисовать их нечем и
незачем. Скрипт нужен, только чтобы пересобрать их, когда поменяется
значок или подпись. Требует Pillow — в зависимостях программы его нет.

## Размеры

Inno Setup сам выбирает из нескольких файлов тот, что ближе к масштабу
экрана, и дотягивает его до точного размера. Поэтому каждой картинки —
по файлу на 100, 125, 150, 200 и 250 %: одну мелкую он размыл бы на
ноутбуке с масштабом 150 %, где сидит половина людей.

Боковая панель держит пропорцию 164:314 — её требует сам установщик.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "ico" / "net67.ico"
OUT = ROOT / "installer" / "art"

#: Фон — цвет окна установщика в его тёмной теме, #2b2b2b.
#:
#: Картинки рисуются ровно этим цветом, без прозрачности и переходов.
#: Сначала панель была темнее окна, с переходом сверху вниз, а значок в
#: шапке — прозрачным: под прозрачным установщик подкладывал свой цвет,
#: и вышло три оттенка серого в одном окне. Владелец: «неравномерные
#: цвета какие-то». Теперь картинка сливается с окном, и на странице
#: виден только сам значок.
WINDOW = (43, 43, 43)
BORDER = (74, 74, 74)
TEXT = (242, 242, 242)
MUTED = (168, 168, 168)

#: Масштабы экрана, под которые готовятся картинки.
SCALES = (100, 125, 150, 200, 250)

#: Боковая панель при 100 % — 202x386, как у установщика по умолчанию.
SIDE_BASE = (202, 386)
#: Значок в шапке страниц при 100 %.
SMALL_BASE = 55

FONT_BOLD = "C:/Windows/Fonts/seguisb.ttf"
FONT_REGULAR = "C:/Windows/Fonts/segoeui.ttf"


def _logo(size: int) -> Image.Image:
    icon = Image.open(ICON)
    icon.size = max(icon.info.get("sizes", {(256, 256)}))
    return icon.convert("RGBA").resize((size, size), Image.LANCZOS)


def side_image(scale: int) -> Image.Image:
    width = round(SIDE_BASE[0] * scale / 100)
    height = round(SIDE_BASE[1] * scale / 100)
    # Рисуем вчетверо крупнее и уменьшаем: текст и края значка выходят
    # гладкими без собственного сглаживания.
    k = 4
    image = Image.new("RGB", (width * k, height * k), WINDOW)
    draw = ImageDraw.Draw(image)
    unit = width * k / 202

    logo_size = round(84 * unit)
    logo = _logo(logo_size)
    x = (image.width - logo_size) // 2
    y = round(92 * unit)
    # Значок тёмный на тёмном: тонкая обводка отделяет его от панели.
    ring = round(1.2 * unit)
    radius = round(logo_size * 0.225)
    draw.rounded_rectangle(
        [x - ring, y - ring, x + logo_size + ring, y + logo_size + ring],
        radius=radius + ring,
        fill=BORDER,
    )
    image.paste(logo, (x, y), logo)

    title_font = ImageFont.truetype(FONT_BOLD, round(25 * unit))
    note_font = ImageFont.truetype(FONT_REGULAR, round(11.5 * unit))
    draw.text((image.width / 2, y + logo_size + round(30 * unit)), "net67", font=title_font, fill=TEXT, anchor="mm")
    draw.text(
        (image.width / 2, y + logo_size + round(56 * unit)),
        "обход блокировок",
        font=note_font,
        fill=MUTED,
        anchor="mm",
    )
    return image.resize((width, height), Image.LANCZOS)


def small_image(scale: int) -> Image.Image:
    size = round(SMALL_BASE * scale / 100)
    k = 4
    canvas = Image.new("RGB", (size * k, size * k), WINDOW)
    logo_size = round(size * k * 0.86)
    offset = (size * k - logo_size) // 2
    ring = max(1, round(size * k * 0.012))
    radius = round(logo_size * 0.225)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [offset - ring, offset - ring, offset + logo_size + ring, offset + logo_size + ring],
        radius=radius + ring,
        fill=BORDER,
    )
    logo = _logo(logo_size)
    canvas.paste(logo, (offset, offset), logo)
    return canvas.resize((size, size), Image.LANCZOS)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for scale in SCALES:
        side_image(scale).save(OUT / f"side-{scale}.png", optimize=True)
        small_image(scale).save(OUT / f"small-{scale}.png", optimize=True)
    print(f"Картинки установщика: {len(SCALES) * 2} файлов в {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
