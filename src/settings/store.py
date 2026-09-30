from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from threading import RLock
from typing import Any

try:
    import winreg
except ImportError:  # pragma: no cover - WSL/static checks only
    winreg = None

from config.runtime_layout import APPLICATION_PATHS
from settings.mode import (
    DEFAULT_LAUNCH_METHOD,
    ENGINE_WINWS2,
    SELECTED_SOURCE_PRESET_FILE_NAME_KEY_WINWS2,
    normalize_launch_method,
)
from settings.normalize import (
    as_clean_str as _as_clean_str,
    as_dict as _as_dict,
    as_int as _as_int,
    normalize_hex_secret as _normalize_hex_secret,
    normalize_settings as _normalize_settings,
    normalize_lookup_key as _normalize_lookup_key,
    unique_dc_ip_list as _unique_dc_ip_list,
    unique_domain_list as _unique_domain_list,
    unique_int_list as _unique_int_list,
    unique_str_list as _unique_str_list,
)
from settings.schema import (
    DEFAULT_TG_PROXY_HOST as _DEFAULT_TG_PROXY_HOST,
    DEFAULT_TG_PROXY_PORT as _DEFAULT_TG_PROXY_PORT,
    DEFAULT_TG_PROXY_UPSTREAM_PORT as _DEFAULT_TG_PROXY_UPSTREAM_PORT,
    DEFAULT_TINTED_INTENSITY as _DEFAULT_TINTED_INTENSITY,
    DEFAULT_WINDOW_OPACITY as _DEFAULT_WINDOW_OPACITY,
    SETTINGS_DIR_NAME as _SETTINGS_DIR_NAME,
    SETTINGS_FILE_NAME as _SETTINGS_FILE_NAME,
    TRAY_CLOSE_MODE_NORMAL as _TRAY_CLOSE_MODE_NORMAL,
    VALID_TRAY_CLOSE_MODES as _VALID_TRAY_CLOSE_MODES,
    build_default_settings as _build_default_settings,
)
from utils.atomic_text import atomic_write_text

_SETTINGS_LOCK = RLock()
_SETTINGS_CACHE: dict[str, Any] | None = None
_SETTINGS_CACHE_SIGNATURE: tuple[str, int | None, int | None] | None = None
# Кэш, заполненный чтением с materialize=False, не гарантирует, что файл на
# диске починен/создан — materialize-чтение обязано пройти мимо такого кэша.
_SETTINGS_CACHE_MATERIALIZED = False
# winws1 здесь больше нет: движок из программы вырезан, а ключ
# selected_source_preset_file_name_winws1 оставался в settings.json
# мёртвым грузом.
_DIRECT_PRESET_SELECTION_PATHS = {
    ENGINE_WINWS2: ("program", SELECTED_SOURCE_PRESET_FILE_NAME_KEY_WINWS2),
}

# Тесты подменяют только этот корень, чтобы не писать в живой settings.json.
# В установленном приложении значение всегда приходит из APPLICATION_PATHS.
MAIN_DIRECTORY = str(APPLICATION_PATHS.root)


def _settings_root() -> Path:
    return Path(MAIN_DIRECTORY)


def get_settings_path() -> Path:
    return _settings_root() / _SETTINGS_DIR_NAME / _SETTINGS_FILE_NAME


def _settings_file_signature(path: Path | None = None) -> tuple[str, int | None, int | None]:
    resolved = path or get_settings_path()
    try:
        stat = resolved.stat()
        return (str(resolved), int(stat.st_mtime_ns), int(stat.st_size))
    except OSError:
        return (str(resolved), None, None)


def _format_settings_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


_SETTINGS_REVISION = 0


def _write_settings_file_locked(data: dict[str, Any]) -> None:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_SIGNATURE, _SETTINGS_CACHE_MATERIALIZED, _SETTINGS_REVISION
    _SETTINGS_REVISION += 1

    normalized = _normalize_settings(data)
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, _format_settings_json(normalized), encoding="utf-8")
    _SETTINGS_CACHE = copy.deepcopy(normalized)
    _SETTINGS_CACHE_SIGNATURE = _settings_file_signature(path)
    _SETTINGS_CACHE_MATERIALIZED = True


def _read_settings_file_locked(*, materialize: bool = True) -> dict[str, Any]:
    path = get_settings_path()
    defaults = _build_default_settings()
    if not path.exists():
        if materialize:
            _write_settings_file_locked(defaults)
        return defaults

    try:
        raw_text = path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    except Exception as exc:
        # Перезапись дефолтами стирает user_profiles и прочие пользовательские
        # данные — повреждённый оригинал обязан сохраниться рядом.
        _backup_corrupt_settings_locked(path, exc)
        if materialize:
            _write_settings_file_locked(defaults)
        return defaults

    normalized = _normalize_settings(raw)
    should_rewrite = False
    if materialize:
        should_rewrite = _format_settings_json(normalized) != _format_settings_json(raw)
    if should_rewrite:
        _write_settings_file_locked(normalized)
    return normalized


def _backup_corrupt_settings_locked(path: Path, error: Exception) -> None:
    backup_path = path.with_name(path.name + ".corrupt.bak")
    try:
        backup_path.write_bytes(path.read_bytes())
    except OSError:
        backup_path = None
    try:
        from log.log import log

        target = f", копия: {backup_path}" if backup_path is not None else ", копию сохранить не удалось"
        log(f"settings.json не читается ({error}); файл будет перезаписан дефолтами{target}", "ERROR")
    except Exception:
        pass


def _read_settings_cached_locked(*, materialize: bool = True) -> dict[str, Any]:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_SIGNATURE, _SETTINGS_CACHE_MATERIALIZED

    signature = _settings_file_signature()
    if (
        _SETTINGS_CACHE is not None
        and _SETTINGS_CACHE_SIGNATURE == signature
        and (_SETTINGS_CACHE_MATERIALIZED or not materialize)
    ):
        return _SETTINGS_CACHE

    data = _read_settings_file_locked(materialize=materialize)
    _SETTINGS_CACHE = copy.deepcopy(data)
    _SETTINGS_CACHE_SIGNATURE = _settings_file_signature()
    # Флаг описывает ИМЕННО этот снапшот: после materialize-чтения файл на
    # диске гарантированно нормализован, после обычного — гарантий нет.
    _SETTINGS_CACHE_MATERIALIZED = materialize
    return _SETTINGS_CACHE


def read_settings() -> dict[str, Any]:
    with _SETTINGS_LOCK:
        return copy.deepcopy(_read_settings_cached_locked())


def materialize_settings_file() -> dict[str, Any]:
    """Гарантирует, что settings.json существует и содержит полный нормализованный JSON."""
    with _SETTINGS_LOCK:
        return copy.deepcopy(_read_settings_cached_locked(materialize=True))


def replace_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Полностью заменяет настройки содержимым словаря.

    Используется импортом конфигурации и редактором файла настроек.
    Запись идёт через общий механизм, поэтому данные обязательно проходят
    нормализацию: неизвестные ключи выбрасываются, недопустимые значения
    заменяются значениями по умолчанию. Писать в файл напрямую нельзя —
    кривой конфиг сломал бы приложение.
    """
    payload = copy.deepcopy(dict(data or {}))

    def _replace(current: dict[str, Any]) -> None:
        current.clear()
        current.update(payload)

    return _update_settings(_replace)


def reset_settings() -> dict[str, Any]:
    data = _build_default_settings()
    with _SETTINGS_LOCK:
        _write_settings_file_locked(data)
    return copy.deepcopy(data)


def _get_path_value(data: dict[str, Any], path: tuple[str, ...], default: Any = None) -> Any:
    current: Any = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _set_path_value(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = data
    for part in path[:-1]:
        if not isinstance(current.get(part), dict):
            current[part] = {}
        current = current[part]
    current[path[-1]] = value


def _update_settings(mutator) -> dict[str, Any]:
    with _SETTINGS_LOCK:
        current = _read_settings_cached_locked()
        working = copy.deepcopy(current)
        mutator(working)
        normalized = _normalize_settings(working)
        if normalized == current:
            return copy.deepcopy(current)
        _write_settings_file_locked(normalized)
        return copy.deepcopy(normalized)


def _get_bool(path: tuple[str, ...], default: bool = False) -> bool:
    return bool(_get_path_value(read_settings(), path, default))


def _set_bool(path: tuple[str, ...], value: bool) -> bool:
    _update_settings(lambda data: _set_path_value(data, path, bool(value)))
    return True


def _get_int(path: tuple[str, ...], default: int = 0) -> int:
    return int(_get_path_value(read_settings(), path, default))


def _set_int(path: tuple[str, ...], value: int) -> bool:
    _update_settings(lambda data: _set_path_value(data, path, int(value)))
    return True


def _get_str(path: tuple[str, ...], default: str = "") -> str:
    return str(_get_path_value(read_settings(), path, default) or "")


def _set_str(path: tuple[str, ...], value: str) -> bool:
    _update_settings(lambda data: _set_path_value(data, path, str(value)))
    return True


def _get_str_in(path: tuple[str, ...], allowed: frozenset[str], default: str = "") -> str:
    value = _get_str(path, default)
    return value if value in allowed else default


def _set_str_in(path: tuple[str, ...], value: str, allowed: frozenset[str], default: str = "") -> bool:
    normalized = str(value or "")
    if normalized not in allowed:
        normalized = default
    return _set_str(path, normalized)


def _get_str_list(path: tuple[str, ...]) -> list[str]:
    value = _get_path_value(read_settings(), path, [])
    return list(value) if isinstance(value, list) else []


def _set_str_list(path: tuple[str, ...], value: object) -> bool:
    _update_settings(lambda data: _set_path_value(data, path, _unique_domain_list(value)))
    return True


def _set_dc_ip_list(path: tuple[str, ...], value: object) -> bool:
    _update_settings(lambda data: _set_path_value(data, path, _unique_dc_ip_list(value)))
    return True


def _get_nullable_str(path: tuple[str, ...]) -> str | None:
    value = _get_path_value(read_settings(), path, None)
    return value if isinstance(value, str) and value.strip() else None


def _set_nullable_str(path: tuple[str, ...], value: str | None) -> bool:
    _update_settings(lambda data: _set_path_value(data, path, None if value is None else str(value)))
    return True


def _presets_selection_path(engine: str) -> tuple[str, ...]:
    normalized = _as_clean_str(engine).lower()
    if normalized not in _DIRECT_PRESET_SELECTION_PATHS:
        raise ValueError(f"Unsupported preset selection engine: {engine}")
    return _DIRECT_PRESET_SELECTION_PATHS[normalized]


def get_program_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["program"])


def set_program_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: data["program"].update(_as_dict(values)))
    return copy.deepcopy(updated["program"])


def get_window_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["window"])


def set_window_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: data["window"].update(_as_dict(values)))
    return copy.deepcopy(updated["window"])


def get_appearance_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["appearance"])


def set_appearance_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: data["appearance"].update(_as_dict(values)))
    return copy.deepcopy(updated["appearance"])


def get_warnings_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["warnings"])


def set_warnings_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: data["warnings"].update(_as_dict(values)))
    return copy.deepcopy(updated["warnings"])


def get_telegram_proxy_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["telegram_proxy"])


def set_telegram_proxy_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: data["telegram_proxy"].update(_as_dict(values)))
    return copy.deepcopy(updated["telegram_proxy"])


def get_dns_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["dns"])


def set_dns_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: data["dns"].update(_as_dict(values)))
    return copy.deepcopy(updated["dns"])


def get_hosts_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["hosts"])


def set_hosts_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: data["hosts"].update(_as_dict(values)))
    return copy.deepcopy(updated["hosts"])


def get_ui_state_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["ui_state"])


def set_ui_state_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: data["ui_state"].update(_as_dict(values)))
    return copy.deepcopy(updated["ui_state"])


def get_profile_strategy_state_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["profile_strategy_state"])


def set_profile_strategy_state_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: _set_path_value(data, ("profile_strategy_state",), _as_dict(values)))
    return copy.deepcopy(updated["profile_strategy_state"])


def get_user_profiles_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["user_profiles"])


def set_user_profiles_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: _set_path_value(data, ("user_profiles",), _as_dict(values)))
    return copy.deepcopy(updated["user_profiles"])


def update_user_profiles_settings(mutator) -> dict[str, Any]:
    """Read-modify-write секции user_profiles одним вызовом _update_settings.

    `mutator` получает копию секции и меняет её на месте. Проверка
    уникальности, выбор id и запись идут под одним замком хранилища, и
    параллельная правка из другого воркера не теряется.
    """

    def _mutate(data: dict[str, Any]) -> None:
        section = copy.deepcopy(_as_dict(data.get("user_profiles")))
        mutator(section)
        _set_path_value(data, ("user_profiles",), section)

    updated = _update_settings(_mutate)
    return copy.deepcopy(updated["user_profiles"])


def get_user_fakes_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["user_fakes"])


def update_user_fakes_settings(mutator) -> dict[str, Any]:
    """Read-modify-write секции user_fakes: проверка имени, файл и запись разом."""

    def _mutate(data: dict[str, Any]) -> None:
        section = copy.deepcopy(_as_dict(data.get("user_fakes")))
        mutator(section)
        _set_path_value(data, ("user_fakes",), section)

    updated = _update_settings(_mutate)
    return copy.deepcopy(updated["user_fakes"])


def get_user_profiles_revision() -> str:
    """Детерминированный токен состояния user_profiles для ключей кэшей.

    Кэши, производные от пользовательских профилей, обязаны включать этот токен
    в ключ вместо ручной инвалидации: токен меняется при любой записи секции,
    в том числе из другого экземпляра сервиса или другого процесса.
    """
    with _SETTINGS_LOCK:
        data = _read_settings_cached_locked(materialize=False)
        payload = data.get("user_profiles") if isinstance(data, dict) else None
        return json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)


def get_updater_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["updater"])


def set_updater_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: data["updater"].update(_as_dict(values)))
    return copy.deepcopy(updated["updater"])


def get_blockcheck_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["blockcheck"])


def set_blockcheck_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: data["blockcheck"].update(_as_dict(values)))
    return copy.deepcopy(updated["blockcheck"])


def update_blockcheck_settings(mutator) -> dict[str, Any]:
    """Read-modify-write секции blockcheck под общим замком настроек.

    `mutator` получает копию секции, прочитанную под _SETTINGS_LOCK, и меняет
    её на месте. Итоги подбора стратегии пишутся из рабочего потока — без
    общего замка они затирали бы правку пользовательских доменов, сделанную
    в это же время на странице.
    """

    def _mutate(data: dict[str, Any]) -> None:
        section = copy.deepcopy(_as_dict(data.get("blockcheck")))
        mutator(section)
        data["blockcheck"] = section

    updated = _update_settings(_mutate)
    return copy.deepcopy(updated["blockcheck"])


def get_folders_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["folders"])


def set_folders_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: _set_path_value(data, ("folders",), _as_dict(values)))
    return copy.deepcopy(updated["folders"])


def get_profile_identity_registry(engine: str) -> dict[str, Any]:
    key = str(engine or "").strip().lower()
    registries = read_settings()["profile_identity"]
    return copy.deepcopy(registries.get(key) or {})


def set_profile_identity_registry(engine: str, registry: dict[str, Any]) -> dict[str, Any]:
    key = str(engine or "").strip().lower()
    updated = _update_settings(
        lambda data: _set_path_value(data, ("profile_identity", key), _as_dict(registry))
    )
    return copy.deepcopy(updated["profile_identity"].get(key) or {})


def get_dpi_autostart() -> bool:
    return _get_bool(("program", "dpi_autostart"), True)


def set_dpi_autostart(value: bool) -> bool:
    return _set_bool(("program", "dpi_autostart"), value)


def get_gui_autostart_enabled() -> bool:
    return _get_bool(("program", "gui_autostart_enabled"), False)


def set_gui_autostart_enabled(value: bool) -> bool:
    return _set_bool(("program", "gui_autostart_enabled"), value)


def get_strategy_launch_method() -> str:
    return normalize_launch_method(_get_str(("program", "strategy_launch_method"), DEFAULT_LAUNCH_METHOD))


def set_strategy_launch_method(value: str) -> bool:
    return _set_str(("program", "strategy_launch_method"), normalize_launch_method(value))


def get_selected_source_preset_file_name(engine: str) -> str | None:
    value = _get_str(_presets_selection_path(engine), "")
    return value or None


def set_selected_source_preset_file_name(engine: str, value: str | None) -> bool:
    normalized = _as_clean_str(value)
    return _set_str(_presets_selection_path(engine), normalized)


def clear_selected_source_preset_file_name(engine: str) -> bool:
    return _set_str(_presets_selection_path(engine), "")


def get_auto_update_enabled() -> bool:
    return _get_bool(("program", "auto_update_enabled"), True)


def set_auto_update_enabled(value: bool) -> bool:
    return _set_bool(("program", "auto_update_enabled"), value)


def get_discord_restart_enabled() -> bool:
    return _get_bool(("program", "discord_auto_restart"), False)


def set_discord_restart_enabled(value: bool) -> bool:
    return _set_bool(("program", "discord_auto_restart"), value)


def get_max_blocked() -> bool:
    return _get_bool(("program", "max_blocked"), False)


def set_max_blocked(value: bool) -> bool:
    return _set_bool(("program", "max_blocked"), value)


def get_russian_state_media_blocked() -> bool:
    return _get_bool(("program", "russian_state_media_blocked"), False)


def set_russian_state_media_blocked(value: bool) -> bool:
    return _set_bool(("program", "russian_state_media_blocked"), value)


def set_defender_disabled_memory(value: bool) -> bool:
    return _set_bool(("program", "defender_disabled"), value)


def get_defender_disabled_memory() -> bool:
    return _get_bool(("program", "defender_disabled"), False)


def get_window_geometry() -> dict[str, Any]:
    data = read_settings()
    return copy.deepcopy(
        {
            "x": _get_path_value(data, ("window", "x"), None),
            "y": _get_path_value(data, ("window", "y"), None),
            "width": _get_path_value(data, ("window", "width"), None),
            "height": _get_path_value(data, ("window", "height"), None),
            "maximized": bool(_get_path_value(data, ("window", "maximized"), False)),
        }
    )


def set_window_geometry(*, x: int | None, y: int | None, width: int | None, height: int | None, maximized: bool) -> bool:
    _update_settings(
        lambda data: data["window"].update(
            {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "maximized": bool(maximized),
            }
        )
    )
    return True


def get_window_opacity() -> int:
    return _get_int(("window", "opacity"), _DEFAULT_WINDOW_OPACITY)


def set_window_opacity(value: int) -> bool:
    return _set_int(("window", "opacity"), value)


def get_tray_close_mode() -> str:
    return _get_str_in(("window", "tray_close_mode"), _VALID_TRAY_CLOSE_MODES, _TRAY_CLOSE_MODE_NORMAL)


def set_tray_close_mode(value: str) -> bool:
    return _set_str_in(("window", "tray_close_mode"), value, _VALID_TRAY_CLOSE_MODES, _TRAY_CLOSE_MODE_NORMAL)


def get_display_mode() -> str:
    return _get_str(("appearance", "display_mode"), "dark")


def set_display_mode(value: str) -> bool:
    return _set_str(("appearance", "display_mode"), value)


def get_ui_language() -> str:
    return _get_str(("appearance", "ui_language"), "ru")


def set_ui_language(value: str) -> bool:
    return _set_str(("appearance", "ui_language"), value)


def get_mica_enabled() -> bool:
    return _get_bool(("appearance", "mica_enabled"), True)


def set_mica_enabled(value: bool) -> bool:
    return _set_bool(("appearance", "mica_enabled"), value)


def get_background_preset() -> str:
    return _get_str(("appearance", "background_preset"), "standard")


def set_background_preset(value: str) -> bool:
    return _set_str(("appearance", "background_preset"), value)


def get_animations_enabled() -> bool:
    return _get_bool(("appearance", "animations_enabled"), False)


def set_animations_enabled(value: bool) -> bool:
    return _set_bool(("appearance", "animations_enabled"), value)


def get_smooth_scroll_enabled() -> bool:
    return _get_bool(("appearance", "smooth_scroll_enabled"), False)


def set_smooth_scroll_enabled(value: bool) -> bool:
    return _set_bool(("appearance", "smooth_scroll_enabled"), value)


def get_editor_smooth_scroll_enabled() -> bool:
    return _get_bool(("appearance", "editor_smooth_scroll_enabled"), False)


def set_editor_smooth_scroll_enabled(value: bool) -> bool:
    return _set_bool(("appearance", "editor_smooth_scroll_enabled"), value)


def get_wizard_completed() -> bool:
    """Пройден ли мастер первого запуска."""
    return _get_bool(("ui_state", "wizard_completed"), False)


def set_wizard_completed(value: bool) -> bool:
    return _set_bool(("ui_state", "wizard_completed"), value)


def get_advanced_panel_side() -> str:
    """С какой стороны выезжает панель расширенного режима."""
    return _get_str(("ui_state", "advanced_panel_side"), "left")


def set_advanced_panel_side(value: str) -> bool:
    from ui.navigation.panel_side import normalize_side

    return _set_str(("ui_state", "advanced_panel_side"), normalize_side(value))


def get_autotune_enabled() -> bool:
    """Искать ли стратегию автоматически при запуске."""
    return _get_bool(("ui_state", "autotune_enabled"), False)


def set_autotune_enabled(value: bool) -> bool:
    return _set_bool(("ui_state", "autotune_enabled"), bool(value))


def get_provider_key() -> str:
    """Провайдер, выбранный при первом запуске. Пусто — не спрашивали."""
    return _get_str(("ui_state", "provider_key"), "")


def set_provider_key(value: str) -> bool:
    return _set_str(("ui_state", "provider_key"), str(value or ""))


def get_hosts_defaults_version() -> int:
    """Какая версия умолчаний hosts уже применена."""
    return _get_int(("ui_state", "hosts_defaults_version"), 0)


def set_hosts_defaults_version(value: int) -> bool:
    return _set_int(("ui_state", "hosts_defaults_version"), int(value))


def get_wizard_services() -> list[str]:
    """Сервисы, отмеченные пользователем в мастере."""
    data = read_settings().get("ui_state") or {}
    values = data.get("wizard_services") or []
    return [str(item) for item in values if isinstance(item, str)]


def set_wizard_services(values) -> bool:
    cleaned = sorted({str(item).strip() for item in (values or []) if str(item).strip()})
    updated = _update_settings(
        lambda data: data["ui_state"].update({"wizard_services": cleaned})
    )
    return bool(updated)


def get_advanced_mode() -> bool:
    """Включён ли расширенный интерфейс.

    False — простой режим: в сайдбаре только главная и оформление.
    True — видны все страницы, включая диагностику, режимы v1/Оркестр и VPN.
    """
    return _get_bool(("ui_state", "advanced_mode"), False)


def set_advanced_mode(value: bool) -> bool:
    return _set_bool(("ui_state", "advanced_mode"), value)


def get_sidebar_icon_style() -> str:
    return _get_str(("appearance", "sidebar_icon_style"), "standard")


def set_sidebar_icon_style(value: str) -> bool:
    return _set_str(("appearance", "sidebar_icon_style"), value)


def get_accent_color() -> str | None:
    return _get_nullable_str(("appearance", "accent_color"))


def set_accent_color(value: str | None) -> bool:
    return _set_nullable_str(("appearance", "accent_color"), value)


def get_follow_windows_accent() -> bool:
    return _get_bool(("appearance", "follow_windows_accent"), False)


def set_follow_windows_accent(value: bool) -> bool:
    return _set_bool(("appearance", "follow_windows_accent"), value)


def get_tinted_background() -> bool:
    return _get_bool(("appearance", "tinted_background"), False)


def set_tinted_background(value: bool) -> bool:
    return _set_bool(("appearance", "tinted_background"), value)


def get_tinted_background_intensity() -> int:
    return _get_int(("appearance", "tinted_background_intensity"), _DEFAULT_TINTED_INTENSITY)


def set_tinted_background_intensity(value: int) -> bool:
    return _set_int(("appearance", "tinted_background_intensity"), value)


def get_windows_system_accent() -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent",
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AccentColorMenu")
            r = value & 0xFF
            g = (value >> 8) & 0xFF
            b = (value >> 16) & 0xFF
            return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None


def get_tray_hint_shown() -> bool:
    return _get_bool(("warnings", "tray_hint_shown"), False)


def set_tray_hint_shown(value: bool = True) -> bool:
    return _set_bool(("warnings", "tray_hint_shown"), value)


def get_telega_warning_disabled() -> bool:
    return _get_bool(("warnings", "disable_telega_warning"), False)


def set_telega_warning_disabled(value: bool) -> bool:
    return _set_bool(("warnings", "disable_telega_warning"), value)


def get_kaspersky_warning_disabled() -> bool:
    return _get_bool(("warnings", "disable_kaspersky_warning"), False)


def set_kaspersky_warning_disabled(value: bool) -> bool:
    return _set_bool(("warnings", "disable_kaspersky_warning"), value)


def get_isp_dns_info_shown() -> bool:
    return _get_bool(("warnings", "isp_dns_info_shown"), False)


def set_isp_dns_info_shown(value: bool) -> bool:
    return _set_bool(("warnings", "isp_dns_info_shown"), value)


def get_tg_proxy_deeplink_done() -> bool:
    return _get_bool(("warnings", "tg_proxy_deeplink_done"), False)


def set_tg_proxy_deeplink_done(value: bool) -> bool:
    return _set_bool(("warnings", "tg_proxy_deeplink_done"), value)


def get_custom_dns_servers() -> list[dict[str, Any]]:
    value = _get_path_value(read_settings(), ("dns", "custom_servers"), [])
    return copy.deepcopy(value if isinstance(value, list) else [])


def set_custom_dns_servers(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updated = _update_settings(lambda data: _set_path_value(data, ("dns", "custom_servers"), value))
    return copy.deepcopy(updated["dns"]["custom_servers"])


def get_active_hosts_domains() -> set[str]:
    items = _get_path_value(read_settings(), ("hosts", "active_domains"), [])
    if not isinstance(items, list):
        return set()
    return set(_unique_str_list(items))


def set_active_hosts_domains(domains: set[str] | list[str]) -> bool:
    normalized = _unique_str_list(list(domains) if isinstance(domains, set) else domains)
    _update_settings(lambda data: _set_path_value(data, ("hosts", "active_domains"), normalized))
    return True


def add_active_hosts_domain(domain: str) -> bool:
    domains = get_active_hosts_domains()
    item = _as_clean_str(domain)
    if item:
        domains.add(item)
    return set_active_hosts_domains(domains)


def remove_active_hosts_domain(domain: str) -> bool:
    domains = get_active_hosts_domains()
    domains.discard(_as_clean_str(domain))
    return set_active_hosts_domains(domains)


def clear_active_hosts_domains() -> bool:
    return set_active_hosts_domains(set())


def get_hosts_selection() -> dict[str, str]:
    data = _get_path_value(read_settings(), ("hosts", "selection"), {})
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for raw_service_name, raw_profile_name in data.items():
        service_name = _as_clean_str(raw_service_name)
        profile_name = _as_clean_str(raw_profile_name)
        if service_name and profile_name:
            out[service_name] = profile_name
    return out


def set_hosts_selection(selection: dict[str, str]) -> bool:
    normalized: dict[str, str] = {}
    for raw_service_name, raw_profile_name in _as_dict(selection).items():
        service_name = _as_clean_str(raw_service_name)
        profile_name = _as_clean_str(raw_profile_name)
        if service_name and profile_name:
            normalized[service_name] = profile_name
    _update_settings(lambda data: _set_path_value(data, ("hosts", "selection"), normalized))
    return True


def get_tg_proxy_enabled() -> bool:
    # По умолчанию выключен.
    #
    # Прокси поднимался при каждом запуске программы, а тумблер «Прокси
    # Telegram вместе с обходом» при этом стоял в «выкл.». Со стороны
    # это выглядело как то, что настройка не работает: человек её не
    # включал, а прокси всё равно висел на порту.
    #
    # Прокси — отдельная служба со своим портом и своим влиянием на
    # Telegram. Поднимать её без спроса неправильно.
    return _get_bool(("telegram_proxy", "enabled"), False)


def set_tg_proxy_enabled(value: bool) -> bool:
    return _set_bool(("telegram_proxy", "enabled"), value)


def get_tg_proxy_host() -> str:
    return _get_str(("telegram_proxy", "host"), _DEFAULT_TG_PROXY_HOST)


def set_tg_proxy_host(value: str) -> bool:
    return _set_str(("telegram_proxy", "host"), value)


def get_tg_proxy_port() -> int:
    return _get_int(("telegram_proxy", "port"), _DEFAULT_TG_PROXY_PORT)


def set_tg_proxy_port(value: int) -> bool:
    return _set_int(("telegram_proxy", "port"), value)


def get_tg_proxy_mode() -> str:
    return _get_str(("telegram_proxy", "mode"), "mtproxy")


def set_tg_proxy_mode(value: str) -> bool:
    return _set_str(("telegram_proxy", "mode"), value)


def get_tg_proxy_upstream_enabled() -> bool:
    return _get_bool(("telegram_proxy", "upstream_enabled"), False)


def set_tg_proxy_upstream_enabled(value: bool) -> bool:
    return _set_bool(("telegram_proxy", "upstream_enabled"), value)


def get_tg_proxy_upstream_host() -> str:
    return _get_str(("telegram_proxy", "upstream_host"), "")


def set_tg_proxy_upstream_host(value: str) -> bool:
    return _set_str(("telegram_proxy", "upstream_host"), value)


def get_tg_proxy_upstream_port() -> int:
    return _get_int(("telegram_proxy", "upstream_port"), _DEFAULT_TG_PROXY_UPSTREAM_PORT)


def set_tg_proxy_upstream_port(value: int) -> bool:
    return _set_int(("telegram_proxy", "upstream_port"), value)


def get_tg_proxy_upstream_preset_id() -> str:
    return _get_str(("telegram_proxy", "upstream_preset_id"), "")


def set_tg_proxy_upstream_preset_id(value: str) -> bool:
    return _set_str(("telegram_proxy", "upstream_preset_id"), value)


def get_tg_proxy_upstream_mode() -> str:
    return _get_str(("telegram_proxy", "upstream_mode"), "fallback")


def set_tg_proxy_upstream_mode(value: str) -> bool:
    return _set_str(("telegram_proxy", "upstream_mode"), value)


def get_tg_proxy_upstream_udp_enabled() -> bool:
    return _get_bool(("telegram_proxy", "upstream_udp_enabled"), False)


def set_tg_proxy_upstream_udp_enabled(value: bool) -> bool:
    return _set_bool(("telegram_proxy", "upstream_udp_enabled"), value)


def get_tg_proxy_upstream_user() -> str:
    return _get_str(("telegram_proxy", "upstream_user"), "")


def set_tg_proxy_upstream_user(value: str) -> bool:
    return _set_str(("telegram_proxy", "upstream_user"), value)


def get_tg_proxy_upstream_pass() -> str:
    return _get_str(("telegram_proxy", "upstream_pass"), "")


def set_tg_proxy_upstream_pass(value: str) -> bool:
    return _set_str(("telegram_proxy", "upstream_pass"), value)


def get_tg_proxy_cloudflare_enabled() -> bool:
    return _get_bool(("telegram_proxy", "cloudflare_enabled"), False)


def set_tg_proxy_cloudflare_enabled(value: bool) -> bool:
    return _set_bool(("telegram_proxy", "cloudflare_enabled"), value)


def get_tg_proxy_cloudflare_domains() -> list[str]:
    return _get_str_list(("telegram_proxy", "cloudflare_domains"))


def set_tg_proxy_cloudflare_domains(value: object) -> bool:
    return _set_str_list(("telegram_proxy", "cloudflare_domains"), value)


def get_tg_proxy_cloudflare_worker_enabled() -> bool:
    return _get_bool(("telegram_proxy", "cloudflare_worker_enabled"), False)


def set_tg_proxy_cloudflare_worker_enabled(value: bool) -> bool:
    return _set_bool(("telegram_proxy", "cloudflare_worker_enabled"), value)


def get_tg_proxy_cloudflare_worker_domains() -> list[str]:
    return _get_str_list(("telegram_proxy", "cloudflare_worker_domains"))


def set_tg_proxy_cloudflare_worker_domains(value: object) -> bool:
    return _set_str_list(("telegram_proxy", "cloudflare_worker_domains"), value)


def get_tg_proxy_mtproxy_secret() -> str:
    return _get_str(("telegram_proxy", "mtproxy_secret"), "")


def set_tg_proxy_mtproxy_secret(value: str) -> bool:
    return _set_str(("telegram_proxy", "mtproxy_secret"), _normalize_hex_secret(value))


def get_tg_proxy_dc_ip() -> list[str]:
    return _get_str_list(("telegram_proxy", "dc_ip"))


def set_tg_proxy_dc_ip(value: object) -> bool:
    return _set_dc_ip_list(("telegram_proxy", "dc_ip"), value)


def get_tg_proxy_pool_size() -> int:
    return _get_int(("telegram_proxy", "pool_size"), 4)


def set_tg_proxy_pool_size(value: int) -> bool:
    return _set_int(("telegram_proxy", "pool_size"), value)


def get_tg_proxy_buffer_kb() -> int:
    return _get_int(("telegram_proxy", "buffer_kb"), 256)


def set_tg_proxy_buffer_kb(value: int) -> bool:
    return _set_int(("telegram_proxy", "buffer_kb"), value)


def get_tg_proxy_fake_tls_domain() -> str:
    return _get_str(("telegram_proxy", "fake_tls_domain"), "")


def set_tg_proxy_fake_tls_domain(value: str) -> bool:
    return _set_str(("telegram_proxy", "fake_tls_domain"), value)


def get_tg_proxy_proxy_protocol() -> bool:
    return _get_bool(("telegram_proxy", "proxy_protocol"), False)


def set_tg_proxy_proxy_protocol(value: bool) -> bool:
    return _set_bool(("telegram_proxy", "proxy_protocol"), value)


def get_tg_proxy_auto_deeplink() -> bool:
    return _get_bool(("telegram_proxy", "auto_deeplink"), True)


def set_tg_proxy_auto_deeplink(value: bool) -> bool:
    return _set_bool(("telegram_proxy", "auto_deeplink"), value)


__all__ = [
    "get_accent_color",
    "get_active_hosts_domains",
    "get_animations_enabled",
    "get_auto_update_enabled",
    "get_background_preset",
    "get_discord_restart_enabled",
    "get_display_mode",
    "get_custom_dns_servers",
    "get_dpi_autostart",
    "get_editor_smooth_scroll_enabled",
    "get_defender_disabled_memory",
    "get_follow_windows_accent",
    "get_folders_settings",
    "get_gui_autostart_enabled",
    "get_hosts_selection",
    "get_isp_dns_info_shown",
    "get_kaspersky_warning_disabled",
    "get_max_blocked",
    "get_mica_enabled",
    "get_program_settings",
    "get_profile_strategy_state_settings",
    "get_russian_state_media_blocked",
    "get_selected_source_preset_file_name",
    "get_advanced_mode",
    "get_sidebar_icon_style",
    "get_hosts_defaults_version",
    "get_advanced_panel_side",
    "get_autotune_enabled",
    "get_provider_key",
    "get_wizard_completed",
    "get_wizard_services",
    "get_settings_path",
    "get_smooth_scroll_enabled",
    "get_strategy_launch_method",
    "get_telega_warning_disabled",
    "get_tg_proxy_deeplink_done",
    "get_tg_proxy_cloudflare_domains",
    "get_tg_proxy_cloudflare_enabled",
    "get_tg_proxy_cloudflare_worker_domains",
    "get_tg_proxy_cloudflare_worker_enabled",
    "get_tg_proxy_buffer_kb",
    "get_tg_proxy_dc_ip",
    "get_tg_proxy_enabled",
    "get_tg_proxy_fake_tls_domain",
    "get_tg_proxy_host",
    "get_tg_proxy_mode",
    "get_tg_proxy_mtproxy_secret",
    "get_tg_proxy_pool_size",
    "get_tg_proxy_port",
    "get_tg_proxy_proxy_protocol",
    "get_tg_proxy_upstream_enabled",
    "get_tg_proxy_upstream_host",
    "get_tg_proxy_upstream_mode",
    "get_tg_proxy_upstream_udp_enabled",
    "get_tg_proxy_upstream_pass",
    "get_tg_proxy_upstream_preset_id",
    "get_tg_proxy_upstream_port",
    "get_tg_proxy_upstream_user",
    "get_tinted_background",
    "get_tinted_background_intensity",
    "get_tray_close_mode",
    "get_tray_hint_shown",
    "get_ui_language",
    "get_window_geometry",
    "get_window_opacity",
    "get_windows_system_accent",
    "materialize_settings_file",
    "read_settings",
    "remove_active_hosts_domain",
    "replace_settings",
    "reset_settings",
    "set_accent_color",
    "set_active_hosts_domains",
    "set_animations_enabled",
    "set_auto_update_enabled",
    "set_background_preset",
    "set_defender_disabled_memory",
    "set_discord_restart_enabled",
    "set_display_mode",
    "set_custom_dns_servers",
    "set_dpi_autostart",
    "set_editor_smooth_scroll_enabled",
    "set_follow_windows_accent",
    "set_folders_settings",
    "set_gui_autostart_enabled",
    "set_hosts_selection",
    "set_isp_dns_info_shown",
    "set_kaspersky_warning_disabled",
    "set_max_blocked",
    "set_mica_enabled",
    "set_program_settings",
    "set_profile_strategy_state_settings",
    "set_russian_state_media_blocked",
    "set_selected_source_preset_file_name",
    "set_advanced_mode",
    "set_sidebar_icon_style",
    "set_hosts_defaults_version",
    "set_advanced_panel_side",
    "set_autotune_enabled",
    "set_provider_key",
    "set_wizard_completed",
    "set_wizard_services",
    "set_smooth_scroll_enabled",
    "set_strategy_launch_method",
    "set_telega_warning_disabled",
    "set_tg_proxy_deeplink_done",
    "set_tg_proxy_cloudflare_domains",
    "set_tg_proxy_cloudflare_enabled",
    "set_tg_proxy_cloudflare_worker_domains",
    "set_tg_proxy_cloudflare_worker_enabled",
    "set_tg_proxy_buffer_kb",
    "set_tg_proxy_dc_ip",
    "set_tg_proxy_enabled",
    "set_tg_proxy_fake_tls_domain",
    "set_tg_proxy_host",
    "set_tg_proxy_mode",
    "set_tg_proxy_mtproxy_secret",
    "set_tg_proxy_pool_size",
    "set_tg_proxy_port",
    "set_tg_proxy_proxy_protocol",
    "set_tg_proxy_upstream_enabled",
    "set_tg_proxy_upstream_host",
    "set_tg_proxy_upstream_mode",
    "set_tg_proxy_upstream_udp_enabled",
    "set_tg_proxy_upstream_pass",
    "set_tg_proxy_upstream_preset_id",
    "set_tg_proxy_upstream_port",
    "set_tg_proxy_upstream_user",
    "set_tinted_background",
    "set_tinted_background_intensity",
    "set_tray_close_mode",
    "set_tray_hint_shown",
    "set_ui_language",
    "set_window_geometry",
    "set_window_opacity",
    "clear_selected_source_preset_file_name",
]


# ────────────────────────────────────────────────────────────────────
# Функции, которые зовёт код из исходного проекта.
#
# Там настройки живут в SQLite (settings.sqlite3), и переноса старого
# settings.json нет: у пользователя после обновления пропали бы VPN-ссылки,
# выбор сервисов hosts и настройки прокси. net67 остаётся на settings.json,
# а те же функции реализует поверх него. Сигнатуры и смысл — как в
# исходном проекте, чтобы пришедший код не отличал одно от другого.
# ────────────────────────────────────────────────────────────────────

_PRESET_UID_PREFIX = "pid:"


def close_settings_database() -> None:
    """В исходном проекте закрывает соединение с SQLite.

    У json соединения нет; смысл тот же — следующий читатель должен взять
    файл с диска, а не кеш прежнего. Этим пользуется изоляция настроек в
    тестах: каждый тест получает свой каталог, и кеш прошлого теста в нём
    оказался бы чужим.
    """
    global _SETTINGS_CACHE, _SETTINGS_CACHE_SIGNATURE, _SETTINGS_CACHE_MATERIALIZED
    with _SETTINGS_LOCK:
        _SETTINGS_CACHE = None
        _SETTINGS_CACHE_SIGNATURE = None
        _SETTINGS_CACHE_MATERIALIZED = False


def get_settings_database_path() -> Path:
    """В исходном проекте — путь к SQLite. Здесь — к settings.json."""
    return get_settings_path()


def prepare_settings_database() -> dict[str, Any]:
    """Создаёт и проверяет файл настроек. Для json это обычное чтение."""
    return read_settings()


def get_settings_revision() -> int:
    """Монотонная ревизия для зависимых кэшей: растёт на каждой записи."""
    with _SETTINGS_LOCK:
        return int(_SETTINGS_REVISION)


def get_last_seen_version() -> str:
    return _get_str(("program", "last_seen_version"), "")


def set_last_seen_version(value: str) -> bool:
    return _set_str(("program", "last_seen_version"), str(value or ""))


def set_live_animations_enabled(value: bool) -> bool:
    return _set_bool(("appearance", "live_animations_enabled"), value)


def get_onboarding_tour_done() -> bool:
    return _get_bool(("warnings", "onboarding_tour_done"), False)


def set_onboarding_tour_done(value: bool) -> bool:
    return _set_bool(("warnings", "onboarding_tour_done"), value)


def get_remote_presets_settings() -> dict[str, Any]:
    return copy.deepcopy(read_settings()["remote_presets"])


def set_remote_presets_settings(values: dict[str, Any]) -> dict[str, Any]:
    updated = _update_settings(lambda data: _set_path_value(data, ("remote_presets",), _as_dict(values)))
    return copy.deepcopy(updated["remote_presets"])


def _clean_scope_file(scope: str, file_name: str) -> tuple[str, str]:
    return str(scope or "").strip().lower(), str(file_name or "").strip()


def get_preset_uid(scope: str, file_name: str) -> str | None:
    scope, file_name = _clean_scope_file(scope, file_name)
    if not scope or not file_name:
        return None
    uid = _get_path_value(read_settings(), ("preset_registry", scope, file_name), None)
    return str(uid) if uid else None


def get_or_create_preset_uid(scope: str, file_name: str) -> str | None:
    scope, file_name = _clean_scope_file(scope, file_name)
    if not scope or not file_name:
        return None
    created: list[str] = []

    def _mutate(data: dict[str, Any]) -> None:
        registry = data.setdefault("preset_registry", {})
        entries = registry.setdefault(scope, {})
        if not entries.get(file_name):
            uid = f"{_PRESET_UID_PREFIX}{uuid.uuid4().hex}"
            entries[file_name] = uid
            created.append(uid)

    updated = _update_settings(_mutate)
    uid = _get_path_value(updated, ("preset_registry", scope, file_name), None)
    return str(uid) if uid else None


def rename_preset_identity(scope: str, old_file_name: str, new_file_name: str) -> bool:
    scope, old_file_name = _clean_scope_file(scope, old_file_name)
    _, new_file_name = _clean_scope_file(scope, new_file_name)
    if not scope or not old_file_name or not new_file_name or old_file_name == new_file_name:
        return False
    moved: list[bool] = []

    def _mutate(data: dict[str, Any]) -> None:
        for section in ("preset_registry", "remote_presets"):
            entries = _as_dict(data.get(section)).get(scope)
            if not isinstance(entries, dict) or old_file_name not in entries:
                continue
            # Имя уже занято — как UNIQUE в исходном проекте: не переносим.
            if section == "preset_registry" and new_file_name in entries:
                return
            entries[new_file_name] = entries.pop(old_file_name)
            if section == "preset_registry":
                moved.append(True)

    _update_settings(_mutate)
    return bool(moved)


def delete_preset_identity(scope: str, file_name: str) -> bool:
    """Удаляет пресет из реестра; привязка к источнику уходит вместе с ним."""
    scope, file_name = _clean_scope_file(scope, file_name)
    if not scope or not file_name:
        return False
    removed: list[bool] = []

    def _mutate(data: dict[str, Any]) -> None:
        for section in ("preset_registry", "remote_presets"):
            entries = _as_dict(data.get(section)).get(scope)
            if isinstance(entries, dict) and entries.pop(file_name, None) is not None and section == "preset_registry":
                removed.append(True)

    _update_settings(_mutate)
    return bool(removed)


def get_preset_remote_source(scope: str, file_name: str) -> dict[str, Any] | None:
    scope, file_name = _clean_scope_file(scope, file_name)
    if not scope or not file_name:
        return None
    binding = _get_path_value(read_settings(), ("remote_presets", scope, file_name), None)
    return copy.deepcopy(binding) if isinstance(binding, dict) else None


def list_preset_remote_sources(scope: str) -> dict[str, dict[str, Any]]:
    scope = str(scope or "").strip().lower()
    if not scope:
        return {}
    entries = _get_path_value(read_settings(), ("remote_presets", scope), {})
    return copy.deepcopy(entries) if isinstance(entries, dict) else {}


def set_preset_remote_source(scope: str, file_name: str, binding: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(binding, dict) or not str(binding.get("url") or "").strip():
        return None
    if get_or_create_preset_uid(scope, file_name) is None:
        return None
    scope, file_name = _clean_scope_file(scope, file_name)
    values = {
        "url": str(binding.get("url") or "").strip(),
        "etag": str(binding.get("etag") or ""),
        "last_modified": str(binding.get("last_modified") or ""),
        "synced_hash": str(binding.get("synced_hash") or ""),
        "checked_at": str(binding.get("checked_at") or ""),
        "updated_at": str(binding.get("updated_at") or ""),
        "error": str(binding.get("error") or ""),
        "auto": bool(binding.get("auto", True)),
        "detached": bool(binding.get("detached", False)),
    }
    _update_settings(lambda data: _set_path_value(data, ("remote_presets", scope, file_name), values))
    return get_preset_remote_source(scope, file_name)


def delete_preset_remote_source(scope: str, file_name: str) -> bool:
    scope, file_name = _clean_scope_file(scope, file_name)
    if not scope or not file_name:
        return False
    removed: list[bool] = []

    def _mutate(data: dict[str, Any]) -> None:
        entries = _as_dict(data.get("remote_presets")).get(scope)
        if isinstance(entries, dict) and entries.pop(file_name, None) is not None:
            removed.append(True)

    _update_settings(_mutate)
    return bool(removed)


def find_preset_remote_source_by_url(url: str) -> tuple[str, str, dict[str, Any]] | None:
    needle = str(url or "").strip()
    if not needle:
        return None
    sections = _as_dict(read_settings().get("remote_presets"))
    for scope, entries in sections.items():
        for file_name, binding in _as_dict(entries).items():
            if isinstance(binding, dict) and str(binding.get("url") or "").strip() == needle:
                return str(scope), str(file_name), copy.deepcopy(binding)
    return None
