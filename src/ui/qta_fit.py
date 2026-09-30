"""Широкие значки qtawesome — в ту же ширину, что и обычные.

qtawesome рисует глиф шрифтом в 0,875 от высоты квадрата и считает, что
глиф квадратный. У Font Awesome это не так: геймпад, сеть, Discord,
«код» и «язык» шириной в 640 единиц при квадрате в 512. Замер: при
квадрате 20 px такой глиф в естественном виде шириной 21,9 px, а
рисуется ровно в 20 — края срезаны. Рядом с обычными значками (17–18 px
с воздухом по бокам) он выходил крупнее, упирался в край и выглядел
съехавшим влево: так владелец и описал плитки ntc.party, Supercell и
Destiny 2 в редакторе hosts и карточку «Онлайн-игры» в подборе стратегии.

Править каждое место бессмысленно — значков больше сотни. Поэтому здесь
обёртка над ``qtawesome.icon``: у одиночного глифа шире квадрата она
уменьшает ``scale_factor`` так, чтобы ширина вышла как у обычного
значка. Явно переданный ``scale_factor`` и составные значки не трогает.
"""

from __future__ import annotations

__all__ = ["fit_scale_factor", "glyph_width_ratio", "install_wide_glyph_fit"]

#: Ширина, до которой ужимается широкий глиф, в долях квадрата.
#:
#: Столько занимают обычные значки Font Awesome: 18 px из 20 (замер
#: Telegram, глобуса, гарнитуры). Уже — и широкий значок станет мельче
#: соседей по высоте заметнее, чем выпирал по ширине.
TARGET_WIDTH = 0.9

#: Доля квадрата, которую qtawesome отдаёт под шрифт (см. CharIconPainter).
_QTA_DRAW_RATIO = 0.875

#: Глифы шире этого (в долях кегля) считаются широкими. Обычные в
#: Font Awesome — 0,97–1,0; Material Design — ровно 1,0.
_WIDE_THRESHOLD = 1.03

_RATIO_CACHE: dict[str, float] = {}
_ORIGINAL_ICON = None


def glyph_width_ratio(name: str) -> float:
    """Ширина глифа к кеглю шрифта; 1.0, если узнать не вышло."""
    cached = _RATIO_CACHE.get(name)
    if cached is not None:
        return cached
    ratio = 1.0
    try:
        import qtawesome
        from PyQt6.QtGui import QFontMetricsF

        prefix, _, short = str(name).partition(".")
        iconic = qtawesome._instance()
        char = iconic.charmap[prefix][short]
        size = 100
        ratio = QFontMetricsF(iconic.font(prefix, size)).horizontalAdvance(char) / size
    except Exception:
        ratio = 1.0
    _RATIO_CACHE[name] = ratio
    return ratio


def fit_scale_factor(ratio: float) -> float:
    """``scale_factor``, при котором глиф с такой шириной не шире обычного."""
    if ratio <= _WIDE_THRESHOLD:
        return 1.0
    return min(1.0, TARGET_WIDTH / (_QTA_DRAW_RATIO * ratio))


def install_wide_glyph_fit() -> bool:
    """Подменяет ``qtawesome.icon`` обёрткой. Повторный вызов ничего не делает.

    Нужен созданный QApplication: ширину глифа меряет QFontMetricsF.
    """
    global _ORIGINAL_ICON
    try:
        import qtawesome
    except Exception:
        return False
    if _ORIGINAL_ICON is not None:
        return True

    original = qtawesome.icon

    def icon(*names, **kwargs):
        if len(names) == 1 and isinstance(names[0], str) and "scale_factor" not in kwargs and "options" not in kwargs:
            factor = fit_scale_factor(glyph_width_ratio(names[0]))
            if factor < 1.0:
                kwargs["scale_factor"] = factor
        return original(*names, **kwargs)

    icon.__doc__ = original.__doc__
    _ORIGINAL_ICON = original
    qtawesome.icon = icon
    return True
