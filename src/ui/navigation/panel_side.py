"""С какой стороны выезжает панель расширенного режима.

Простой вид показывает одну главную страницу. Всё остальное открывается
кнопкой «Расширенные настройки», и панель с разделами должна выезжать
плавно — а с какой стороны, человек выбирает сам в оформлении.

Модуль отвечает только за выбор стороны и за то, как эта сторона
превращается в направление движения. Ни Qt, ни анимации здесь нет
намеренно: правило «слева панель приезжает справа налево» должно
проверяться без окна на экране.

Почему сторона вообще настройка. Панель перекрывает часть содержимого,
пока выезжает. На широком мониторе удобнее слева, на вертикальном —
сверху, а левше с окном у правого края экрана — справа. Угадать за
человека нельзя, а цена ошибки — привычное движение мышью каждый раз не
туда.
"""

from __future__ import annotations

from dataclasses import dataclass


SIDE_LEFT = "left"
SIDE_RIGHT = "right"
SIDE_TOP = "top"

#: Сторона по умолчанию.
#:
#: Слева — потому что там панель стояла всегда, и смена умолчания
#: переучивала бы всех, кто уже пользуется программой.
DEFAULT_SIDE = SIDE_LEFT


@dataclass(frozen=True, slots=True)
class PanelSide:
    key: str
    title: str
    #: По какой оси едет панель: "x" или "y".
    axis: str
    #: Знак смещения в спрятанном состоянии. Панель слева прячется
    #: влево (-1), справа — вправо (+1), сверху — вверх (-1).
    hidden_sign: int


SIDES: tuple[PanelSide, ...] = (
    PanelSide(SIDE_LEFT, "Слева", "x", -1),
    PanelSide(SIDE_RIGHT, "Справа", "x", 1),
    PanelSide(SIDE_TOP, "Сверху", "y", -1),
)

_BY_KEY = {side.key: side for side in SIDES}


def normalize_side(value) -> str:
    """Приводит значение к известной стороне. Мусор — сторона по умолчанию."""
    key = str(value or "").strip().lower()
    return key if key in _BY_KEY else DEFAULT_SIDE


def get_side(value) -> PanelSide:
    return _BY_KEY[normalize_side(value)]


def side_titles() -> tuple[tuple[str, str], ...]:
    """Пары (ключ, название) для выпадающего списка в оформлении."""
    return tuple((side.key, side.title) for side in SIDES)


def hidden_offset(value, *, width: int, height: int) -> tuple[int, int]:
    """Смещение панели в спрятанном состоянии, в пикселях (dx, dy).

    Размер берётся снаружи: считать его здесь означало бы тянуть Qt в
    модуль, который должен проверяться без окна.
    """
    side = get_side(value)
    extent = int(width if side.axis == "x" else height)
    extent = max(0, extent)
    if side.axis == "x":
        return (side.hidden_sign * extent, 0)
    return (0, side.hidden_sign * extent)


def visible_offset() -> tuple[int, int]:
    """Смещение в раскрытом состоянии. Всегда ноль — панель на месте."""
    return (0, 0)


def load_side() -> str:
    """Сторона из настроек. Настройки недоступны — сторона по умолчанию."""
    try:
        from settings.store import get_advanced_panel_side

        return normalize_side(get_advanced_panel_side())
    except Exception:
        return DEFAULT_SIDE


__all__ = [
    "DEFAULT_SIDE",
    "SIDES",
    "SIDE_LEFT",
    "SIDE_RIGHT",
    "SIDE_TOP",
    "PanelSide",
    "get_side",
    "hidden_offset",
    "load_side",
    "normalize_side",
    "side_titles",
    "visible_offset",
]
