from __future__ import annotations


def get_window_geometry() -> dict:
    from settings import store as settings_store

    return dict(settings_store.get_window_geometry() or {})


def set_window_geometry(*, x, y, width, height, maximized: bool) -> None:
    from settings import store as settings_store

    settings_store.set_window_geometry(
        x=x,
        y=y,
        width=width,
        height=height,
        maximized=bool(maximized),
    )


__all__ = ["get_window_geometry", "set_window_geometry"]
