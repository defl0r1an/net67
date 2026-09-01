from __future__ import annotations

from typing import Any

from settings.mode import (
    ALL_LAUNCH_METHODS,
    DEFAULT_LAUNCH_METHOD,
    SELECTED_SOURCE_PRESET_FILE_NAME_KEY_WINWS2,
)

SETTINGS_DIR_NAME = "settings"
SETTINGS_FILE_NAME = "settings.json"
SETTINGS_VERSION = 1

DEFAULT_WINDOW_OPACITY = 100
DEFAULT_TINTED_INTENSITY = 15
MAX_TINTED_INTENSITY = 100
DEFAULT_TG_PROXY_HOST = "127.0.0.1"
DEFAULT_TG_PROXY_PORT = 1353
DEFAULT_TG_PROXY_UPSTREAM_PORT = 1080

VALID_LAUNCH_METHODS = ALL_LAUNCH_METHODS
VALID_DISPLAY_MODES = frozenset({"dark", "light", "system"})
VALID_UI_LANGUAGES = frozenset({"ru", "en"})
VALID_BACKGROUND_PRESETS = frozenset({"standard", "amoled"})
VALID_SIDEBAR_ICON_STYLES = frozenset({"standard", "windows11_fluent"})
VALID_TG_PROXY_MODES = frozenset({"socks5", "mtproxy"})
VALID_TG_PROXY_UPSTREAM_MODES = frozenset({"fallback", "always"})
TRAY_CLOSE_MODE_MINIMIZE_AND_CLOSE = "minimize_and_close"
TRAY_CLOSE_MODE_MINIMIZE_ONLY = "minimize_only"
TRAY_CLOSE_MODE_NORMAL = "normal"
VALID_TRAY_CLOSE_MODES = frozenset(
    {
        TRAY_CLOSE_MODE_MINIMIZE_AND_CLOSE,
        TRAY_CLOSE_MODE_MINIMIZE_ONLY,
        TRAY_CLOSE_MODE_NORMAL,
    }
)


def default_program() -> dict[str, Any]:
    return {
        "dpi_autostart": True,
        "gui_autostart_enabled": False,
        "strategy_launch_method": DEFAULT_LAUNCH_METHOD,
        SELECTED_SOURCE_PRESET_FILE_NAME_KEY_WINWS2: "",
        "auto_update_enabled": True,
        "remove_github_api": True,
        # Перезапуск Discord выключен по умолчанию.
        #
        # Настройка закрывает чужое приложение и открывает заново — при
        # каждой смене стратегии. Делать такое без спроса нельзя: в
        # Discord в этот момент может идти разговор, и человек, который
        # про настройку не знал, увидит просто оборвавшийся звонок.
        "discord_auto_restart": False,
        "max_blocked": False,
        "russian_state_media_blocked": False,
        "defender_disabled": False,
        # Охват VPN: весь трафик системы через туннель или только
        # браузер через системный прокси. Выключено по умолчанию —
        # туннель правит таблицу маршрутов и требует прав администратора.
        "vpn_tun_mode": False,
        # Поднимать ли прокси Telegram вместе с обходом.
        #
        # Прокси и обход — разные вещи и включались порознь: прокси при
        # старте программы, обход по кнопке. Кому нужен Telegram только
        # под обходом, приходилось помнить про две кнопки.
        "telegram_proxy_with_bypass": False,
    }


def default_window() -> dict[str, Any]:
    return {
        "x": None,
        "y": None,
        "width": None,
        "height": None,
        "maximized": False,
        "opacity": DEFAULT_WINDOW_OPACITY,
        "tray_close_mode": TRAY_CLOSE_MODE_NORMAL,
    }


def default_appearance() -> dict[str, Any]:
    return {
        "display_mode": "dark",
        "ui_language": "ru",
        "mica_enabled": True,
        "accent_color": None,
        "follow_windows_accent": False,
        "tinted_background": False,
        "tinted_background_intensity": DEFAULT_TINTED_INTENSITY,
        "background_preset": "standard",
        # Анимации включены. Умолчание было False, а переключатель к нему
        # из интерфейса убран, — то есть анимации оказались выключены у
        # всех и включить их было нечем. Лента песчинок из-за этого
        # стояла неподвижно.
        "animations_enabled": True,
        "smooth_scroll_enabled": False,
        "editor_smooth_scroll_enabled": False,
        "sidebar_icon_style": "standard",
    }


def default_warnings() -> dict[str, Any]:
    return {
        "tray_hint_shown": False,
        "disable_telega_warning": False,
        "disable_kaspersky_warning": False,
        "isp_dns_info_shown": False,
        "tg_proxy_deeplink_done": False,
    }


def default_telegram_proxy() -> dict[str, Any]:
    return {
        # Выключен по умолчанию.
        #
        # Прокси поднимался при каждом запуске программы, а тумблер
        # «Прокси Telegram вместе с обходом» стоял при этом в «выкл.».
        # Со стороны это выглядело как сломанная настройка: человек её
        # не включал, а прокси всё равно висел на порту.
        #
        # Прокси — отдельная служба со своим портом и своим влиянием на
        # Telegram. Поднимать её без спроса неправильно.
        "enabled": False,
        "host": DEFAULT_TG_PROXY_HOST,
        "port": DEFAULT_TG_PROXY_PORT,
        "mode": "mtproxy",
        "upstream_enabled": True,
        "upstream_host": "",
        "upstream_port": DEFAULT_TG_PROXY_UPSTREAM_PORT,
        "upstream_preset_id": "",
        "upstream_mode": "fallback",
        "upstream_udp_enabled": False,
        "upstream_user": "",
        "upstream_pass": "",
        "cloudflare_enabled": False,
        "cloudflare_domains": [],
        "cloudflare_worker_enabled": False,
        "cloudflare_worker_domains": [],
        "mtproxy_secret": "",
        "dc_ip": [],
        "pool_size": 4,
        "buffer_kb": 256,
        "fake_tls_domain": "",
        "proxy_protocol": False,
    }


def default_dns() -> dict[str, Any]:
    return {
        "force_dns_enabled": False,
        "dns_crash_count": 0,
        "custom_servers": [],
    }


def default_hosts() -> dict[str, Any]:
    return {
        "bootstrap_signature": None,
        "active_domains": [],
        "selection": {},
    }


def default_ui_state() -> dict[str, Any]:
    return {
        "sidebar_expanded": True,
        # Простой интерфейс по умолчанию: в сайдбаре только главная и
        # оформление, остальное открывается кнопкой «Расширенные настройки».
        "advanced_mode": False,
        # Мастер первого запуска ещё не пройден.
        "wizard_completed": False,
        # Что пользователь отметил в мастере. Пустой список — не спрашивали.
        "wizard_services": [],
        # Автоподбор стратегии при запуске. Выключен по умолчанию: он
        # идёт минутами и на время проверки каждой стратегии прерывает
        # защиту. Такое не включают за человека.
        # С какой стороны выезжает панель расширенного режима.
        # Слева — как было всегда: смена умолчания переучивала бы всех,
        # кто уже пользуется программой.
        "advanced_panel_side": "left",
        "autotune_enabled": False,
        # Провайдер, выбранный при первом запуске. Пустая строка — не
        # спрашивали. Это подсказка для стартового пресета, не более.
        "provider_key": "",
        # Какая версия умолчаний hosts уже применена. Не bool, а число:
        # первая версия включала подмену DNS и ломала доступ к сайтам,
        # её пришлось переписать у всех, кто успел установить.
        "hosts_defaults_version": 0,
    }


def default_profile_strategy_state() -> dict[str, Any]:
    return {
        "version": 1,
        "profiles": {},
    }


def default_user_profiles() -> dict[str, Any]:
    return {
        "version": 1,
        "profiles": {},
    }


def default_updater() -> dict[str, Any]:
    return {
        "release_cache": {},
        "rate_limit": {},
        "github_cache": {},
        "github_rate_limit_reset": None,
        "server_pool": {
            "stats": {},
            "selected_server_id": None,
            "selected_at": None,
        },
        "release_manager": {
            "vps_block_until": 0,
            "server_stats": {},
        },
    }


def default_blockcheck() -> dict[str, Any]:
    return {
        "user_domains": [],
        "scan_resume": {"domains": {}},
    }


def default_folders() -> dict[str, Any]:
    from folders.defaults import build_default_preset_folders, build_default_profile_folders

    return {
        "version": 1,
        "presets": {
            "winws2": build_default_preset_folders("winws2"),
            "winws1": build_default_preset_folders("winws1"),
        },
        "profiles": build_default_profile_folders(),
    }


def default_profile_identity() -> dict[str, Any]:
    return {
        "winws2": {},
        "winws1": {},
    }


def build_default_settings() -> dict[str, Any]:
    return {
        "version": SETTINGS_VERSION,
        "program": default_program(),
        "window": default_window(),
        "appearance": default_appearance(),
        "warnings": default_warnings(),
        "telegram_proxy": default_telegram_proxy(),
        "dns": default_dns(),
        "hosts": default_hosts(),
        "ui_state": default_ui_state(),
        "profile_strategy_state": default_profile_strategy_state(),
        "user_profiles": default_user_profiles(),
        "updater": default_updater(),
        "blockcheck": default_blockcheck(),
        "folders": default_folders(),
        "profile_identity": default_profile_identity(),
    }
