from __future__ import annotations


def get_current_launch_method(*, default: str = "") -> str:
    from settings.dpi.launch_method import get_current_launch_method as _get_current_launch_method

    return _get_current_launch_method(default=default)


__all__ = ["get_current_launch_method"]
