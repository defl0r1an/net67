"""Собирает значок приложения из знака «67».

Макет: тёмная плашка `#171717`, на ней «67» шрифтом Barlow Condensed
ExtraBold цветом `#F4F4F3`. Цифры стоят впритык — в макете это
`letter-spacing: -8px` при кегле 150, то есть примерно -5.3% от кегля, —
а шестёрка приподнята на `-0.1em`.

## Почему не одна картинка на все размеры

Windows берёт из .ico подходящий размер сам, но уменьшать 256 до 16 он
будет своим алгоритмом, и тонкие штрихи Barlow Condensed при этом
превращаются в кашу. Поэтому каждый размер рисуется заново, со своим
кеглем и своим скруглением, и в мелких размерах знак намеренно крупнее
относительно плашки: на 16 пикселях поля съедают читаемость раньше,
чем это заметно на большом.

## Запуск

    python scripts/build_icon.py --font <путь к Barlow Condensed ExtraBold>

Шрифт нужен только для сборки и в репозиторий не кладётся: Barlow
распространяется под SIL OFL, и держать его копию рядом с исходниками
значит брать на себя условия её распространения. Взять можно с Google
Fonts — семейство Barlow Condensed, начертание ExtraBold.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


#: Цвета из макета.
PLATE_COLOR = "#171717"
GLYPH_COLOR = "#F4F4F3"

#: Размеры, которые кладём в .ico. Ниже 16 Windows не запрашивает,
#: выше 256 формат не поддерживает.
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

#: Доля кегля от стороны плашки. В макете 150 из 220 — это 0.68, и на
#: больших размерах так и есть. На мелких знак поднимаем: замер на 16
#: пикселях показал, что при 0.68 цифры занимают 9 пикселей по высоте и
#: перестают читаться.
GLYPH_SCALE = {16: 0.86, 20: 0.84, 24: 0.82, 32: 0.78, 40: 0.75, 48: 0.73}
GLYPH_SCALE_DEFAULT = 0.68

#: Скругление плашки, доля стороны. В макете 46 из 220.
CORNER_RATIO = 46.0 / 220.0

#: Насколько цифры наезжают друг на друга, доля кегля. В макете -8 при 150.
TRACKING_RATIO = -8.0 / 150.0

#: Подъём шестёрки, доля кегля. В макете -0.1em.
SIX_RISE_RATIO = -0.10


def _load_font(font_path: Path, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(str(font_path), size)


def _measure(draw, font, text: str) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), text, font=font)


def render_mark(size: int, font_path: Path, *, rounded: bool = True):
    """Рисует знак «67» на плашке заданного размера."""
    from PIL import Image, ImageDraw

    # Рисуем с запасом и уменьшаем: края скругления и штрихи цифр
    # получаются мягче, чем при отрисовке сразу в целевой размер.
    scale = 8 if size <= 64 else 2
    canvas = size * scale

    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if rounded:
        radius = int(round(canvas * CORNER_RATIO))
        draw.rounded_rectangle((0, 0, canvas - 1, canvas - 1), radius, fill=PLATE_COLOR)
    else:
        draw.rectangle((0, 0, canvas - 1, canvas - 1), fill=PLATE_COLOR)

    point = int(round(canvas * GLYPH_SCALE.get(size, GLYPH_SCALE_DEFAULT)))
    font = _load_font(font_path, point)
    tracking = point * TRACKING_RATIO
    rise = point * SIX_RISE_RATIO

    # Ширину берём по метрике шрифта, а не по краске: `letter-spacing`
    # в макете добавляется именно к метрической ширине, и по краске
    # цифры сходились бы теснее задуманного.
    advance_six = font.getlength("6")

    six = _measure(draw, font, "6")
    seven = _measure(draw, font, "7")

    # Ставим цифры в условные координаты, потом двигаем связку целиком.
    six_at = (0.0, rise)
    seven_at = (advance_six + tracking, 0.0)

    ink_left = min(six_at[0] + six[0], seven_at[0] + seven[0])
    ink_right = max(six_at[0] + six[2], seven_at[0] + seven[2])
    ink_top = min(six_at[1] + six[1], seven_at[1] + seven[1])
    ink_bottom = max(six_at[1] + six[3], seven_at[1] + seven[3])

    # Центрируем по краске, а не по строке. В вёрстке центрируется
    # строка целиком, и приподнятая шестёрка утаскивает знак вверх:
    # замер на 256 давал 50 пикселей сверху против 67 снизу. На плашке
    # приложения такой перекос виден сразу.
    shift_x = (canvas - (ink_right - ink_left)) / 2.0 - ink_left
    shift_y = (canvas - (ink_bottom - ink_top)) / 2.0 - ink_top

    draw.text((six_at[0] + shift_x, six_at[1] + shift_y), "6", font=font, fill=GLYPH_COLOR)
    draw.text((seven_at[0] + shift_x, seven_at[1] + shift_y), "7", font=font, fill=GLYPH_COLOR)

    return image.resize((size, size), Image.Resampling.LANCZOS)


def build_ico(font_path: Path, out_path: Path) -> list[int]:
    frames = [render_mark(size, font_path) for size in SIZES]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames[-1].save(out_path, format="ICO", sizes=[(s, s) for s in SIZES])
    return list(SIZES)


def build_png(font_path: Path, out_path: Path, size: int = 1024) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    render_mark(size, font_path).save(out_path, format="PNG")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сборка значка net67")
    parser.add_argument("--font", required=True, type=Path, help="Barlow Condensed ExtraBold")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    if not args.font.is_file():
        print(f"Шрифт не найден: {args.font}", file=sys.stderr)
        return 2

    for ico_dir in (args.root / "ico", args.root / "src" / "ico"):
        sizes = build_ico(args.font, ico_dir / "net67.ico")
        print(f"{ico_dir / 'net67.ico'}: {sizes}")

    build_png(args.font, args.root / "src" / "ico" / "net67_1024.png")
    print(f"{args.root / 'src' / 'ico' / 'net67_1024.png'}: 1024")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
