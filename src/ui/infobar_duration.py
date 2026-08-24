from __future__ import annotations

from typing import Any


SUCCESS_INFOBAR_MIN_DURATION_MS = 5000
_PATCHED_ATTR = "_zapret_success_min_duration_installed"
_ORIGINAL_ATTR = "_zapret_success_min_duration_original"
_DURATION_ARG_INDEX = 4


def _coerce_success_duration(value: Any, minimum_ms: int = SUCCESS_INFOBAR_MIN_DURATION_MS) -> int:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return int(minimum_ms)
    if duration < 0:
        return duration
    return max(duration, int(minimum_ms))


def _with_min_success_duration(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    minimum_ms: int = SUCCESS_INFOBAR_MIN_DURATION_MS,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    next_kwargs = dict(kwargs)
    if len(args) > _DURATION_ARG_INDEX:
        next_args = list(args)
        next_args[_DURATION_ARG_INDEX] = _coerce_success_duration(
            next_args[_DURATION_ARG_INDEX],
            minimum_ms,
        )
        return tuple(next_args), next_kwargs

    next_kwargs["duration"] = _coerce_success_duration(
        next_kwargs.get("duration", minimum_ms),
        minimum_ms,
    )
    return args, next_kwargs


def install_success_infobar_min_duration(
    info_bar_cls: type | None = None,
    minimum_ms: int = SUCCESS_INFOBAR_MIN_DURATION_MS,
) -> None:
    """Один раз задаёт нижнюю границу времени для успешных InfoBar.

    В qfluentwidgets по умолчанию успешное окно живёт около секунды. Здесь мы
    не меняем предупреждения и ошибки, а только не даём коротким success-окнам
    закрыться быстрее заданного минимума.
    """
    if info_bar_cls is None:
        from qfluentwidgets import InfoBar

        info_bar_cls = InfoBar

    if bool(getattr(info_bar_cls, _PATCHED_ATTR, False)):
        return

    original_success = getattr(info_bar_cls, "success")

    def success_with_min_duration(cls, *args, **kwargs):
        next_args, next_kwargs = _with_min_success_duration(args, kwargs, minimum_ms)
        return original_success(*next_args, **next_kwargs)

    setattr(info_bar_cls, _ORIGINAL_ATTR, original_success)
    setattr(info_bar_cls, "success", classmethod(success_with_min_duration))
    setattr(info_bar_cls, _PATCHED_ATTR, True)
