"""Ленивые экспорты страниц главного окна.

Важно: пакет `ui.pages` не должен eagerly импортировать все страницы сразу.
Главное окно загружает страницы по прямым путям вроде `ui.pages.appearance_page`,
и если `__init__.py` тянет весь пакет целиком, то первая lazy-инициализация
любой страницы фактически импортирует десятки чужих модулей и их зависимости.

Это ломает изоляцию lazy-загрузки, ухудшает старт и может показывать ошибку
не той страницы, которая реально открывалась первой.
"""

from __future__ import annotations

from importlib import import_module


_PAGE_EXPORTS: dict[str, tuple[str, str]] = {
    "Zapret2ModeControlPage": ("presets.ui.control.zapret2.page", "Zapret2ModeControlPage"),
    "Zapret2PresetSetupPage": ("profile.ui.preset_setup_page", "Zapret2PresetSetupPage"),
    "Zapret2UserPresetsPage": ("presets.ui.zapret2.user_presets_page", "Zapret2UserPresetsPage"),
    "Zapret2ProfileSetupPage": ("profile.ui.profile_setup_page", "Zapret2ProfileSetupPage"),
    "Zapret2ProfileOrderPage": ("profile.ui.profile_order_page", "Zapret2ProfileOrderPage"),
    "NetworkPage": ("dns.ui.page", "NetworkPage"),
    "HostsPage": ("hosts.ui.page", "HostsPage"),
    "AboutPage": (".about_page", "AboutPage"),
    "SupportPage": (".support_page", "SupportPage"),
    "LogsPage": ("log.ui.page", "LogsPage"),
    "BlockcheckPage": ("blockcheck.ui.page", "BlockcheckPage"),
    "ServersPage": ("updater.ui.page", "ServersPage"),
    "ConnectionTestPage": ("diagnostics.ui.page", "ConnectionTestPage"),
}

__all__ = list(_PAGE_EXPORTS)


def __getattr__(name: str):
    spec = _PAGE_EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = spec
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
