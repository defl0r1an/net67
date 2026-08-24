from __future__ import annotations

from importlib import import_module

__all__ = ["LupiDPIApp", "main"]


def __getattr__(name: str):
    if name == "LupiDPIApp":
        return import_module("main.window").LupiDPIApp
    if name == "main":
        return import_module("main.entry").main
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(__all__)
