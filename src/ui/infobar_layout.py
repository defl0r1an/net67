from __future__ import annotations

from typing import Any, Callable


# Ширина "хрома" InfoBar: иконка (36) + кнопка закрытия (36) + отступы layout'ов.
INFOBAR_CHROME_WIDTH_PX = 110
# Отступы менеджера InfoBar от краёв родительского окна (24 слева + 24 справа).
INFOBAR_PARENT_MARGINS_PX = 48
# Ширина родителя по умолчанию, когда parent неизвестен (как в InfoBar._adjustText).
DEFAULT_PARENT_WIDTH_PX = 900
# Длинный content рядом с заголовком выглядит плохо даже на широком окне.
MAX_HORIZONTAL_CONTENT_CHARS = 80
# Оценка ширины символа для 14px 'Segoe UI', когда метрики шрифта недоступны.
FALLBACK_CHAR_WIDTH_PX = 8

_PATCHED_ATTR = "_zapret_adaptive_layout_installed"
_ORIGINAL_NEW_ATTR = "_zapret_adaptive_layout_original_new"
_TITLE_ARG_INDEX = 1
_CONTENT_ARG_INDEX = 2
_ORIENT_ARG_INDEX = 3
_PARENT_ARG_INDEX = 7

MeasureTextFn = Callable[..., int]


def measure_infobar_text_px(text: str, *, semibold: bool = False) -> int:
    """Оценивает ширину самой длинной строки текста в пикселях.

    Использует метрики шрифта InfoBar (14px 'Segoe UI', semibold для title),
    а без работающего QGuiApplication откатывается на оценку по числу символов.
    """
    line = max(str(text or "").split("\n"), key=len, default="")
    if not line:
        return 0

    try:
        from PyQt6.QtGui import QFont, QFontMetrics, QGuiApplication

        if QGuiApplication.instance() is None:
            raise RuntimeError("QGuiApplication is not created yet")

        font = QFont("Segoe UI")
        font.setPixelSize(14)
        if semibold:
            font.setWeight(QFont.Weight.DemiBold)
        return int(QFontMetrics(font).horizontalAdvance(line))
    except Exception:
        return len(line) * FALLBACK_CHAR_WIDTH_PX


def should_use_vertical_orientation(
    title: str,
    content: str,
    parent_width: int,
    measure_text: MeasureTextFn | None = None,
) -> bool:
    """Решает, нужен ли вертикальный layout (content под заголовком).

    Горизонтальный InfoBar кладёт title и content в одну строку: если они
    не помещаются в окно, content зажимается в узкую колонку и обрезается.
    """
    content = str(content or "")
    title = str(title or "")
    if not content:
        return False
    if "\n" in content:
        return True
    if len(content) > MAX_HORIZONTAL_CONTENT_CHARS:
        return True

    measure = measure_text or measure_infobar_text_px
    width = int(parent_width or 0)
    if width <= 0:
        width = DEFAULT_PARENT_WIDTH_PX
    available = width - INFOBAR_PARENT_MARGINS_PX - INFOBAR_CHROME_WIDTH_PX
    return measure(title, semibold=True) + measure(content) > available


def _parent_width(parent: Any) -> int:
    width_fn = getattr(parent, "width", None)
    if not callable(width_fn):
        return 0
    try:
        return int(width_fn() or 0)
    except Exception:
        return 0


def _is_upgradeable_orientation(orient: Any) -> bool:
    if orient is None:
        return True
    try:
        from PyQt6.QtCore import Qt

        return orient == Qt.Orientation.Horizontal
    except Exception:
        return False


def _with_adaptive_orientation(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    measure_text: MeasureTextFn | None = None,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    title = args[_TITLE_ARG_INDEX] if len(args) > _TITLE_ARG_INDEX else kwargs.get("title", "")
    content = args[_CONTENT_ARG_INDEX] if len(args) > _CONTENT_ARG_INDEX else kwargs.get("content", "")
    orient = args[_ORIENT_ARG_INDEX] if len(args) > _ORIENT_ARG_INDEX else kwargs.get("orient")
    parent = args[_PARENT_ARG_INDEX] if len(args) > _PARENT_ARG_INDEX else kwargs.get("parent")

    if not _is_upgradeable_orientation(orient):
        return args, kwargs
    if not should_use_vertical_orientation(title, content, _parent_width(parent), measure_text):
        return args, kwargs

    from PyQt6.QtCore import Qt

    vertical = Qt.Orientation.Vertical
    if len(args) > _ORIENT_ARG_INDEX:
        next_args = list(args)
        next_args[_ORIENT_ARG_INDEX] = vertical
        return tuple(next_args), kwargs

    next_kwargs = dict(kwargs)
    next_kwargs["orient"] = vertical
    return args, next_kwargs


def install_infobar_adaptive_layout(info_bar_cls: type | None = None) -> None:
    """Один раз включает адаптивную ориентацию для всех InfoBar приложения.

    Все фабрики (success/info/warning/error) проходят через InfoBar.new,
    поэтому патчится только он: если однострочный горизонтальный вариант не
    помещается в окно родителя, ориентация переключается на вертикальную, а
    перенос строк выполняет штатный TextWrap. Явно заданная вертикальная
    ориентация не меняется.
    """
    if info_bar_cls is None:
        from qfluentwidgets import InfoBar

        info_bar_cls = InfoBar

    if bool(getattr(info_bar_cls, _PATCHED_ATTR, False)):
        return

    original_new = getattr(info_bar_cls, "new")

    def new_with_adaptive_orientation(cls, *args, **kwargs):
        next_args, next_kwargs = _with_adaptive_orientation(args, kwargs)
        return original_new(*next_args, **next_kwargs)

    setattr(info_bar_cls, _ORIGINAL_NEW_ATTR, original_new)
    setattr(info_bar_cls, "new", classmethod(new_with_adaptive_orientation))
    setattr(info_bar_cls, _PATCHED_ATTR, True)
