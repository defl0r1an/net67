from __future__ import annotations

from importlib import import_module


_EXPORTS: dict[str, tuple[str, str]] = {
    "build_app_features": ("app.feature_assembly", "build_app_features"),
    "AppFeatures": ("app.features", "AppFeatures"),
    "DnsFeature": ("app.features", "DnsFeature"),
    "AppRuntime": ("app.runtime", "AppRuntime"),
    "build_app_runtime": ("app.runtime", "build_app_runtime"),
    "AppStateAccess": ("app.state_access", "AppStateAccess"),
    "build_app_state_access": ("app.state_access", "build_app_state_access"),
    "AppRuntimeState": ("app.state_store", "AppRuntimeState"),
    "AppUiState": ("app.state_store", "AppUiState"),
    "MainWindowStateStore": ("app.state_store", "MainWindowStateStore"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    spec = _EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = spec
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
