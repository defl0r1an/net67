"""Системный прокси Windows: включить, выключить, вернуть как было.

Ядро Xray поднимает локальный прокси и больше ничего не делает — само
по себе оно трафик не заворачивает. Человек это видит так: «Подключено»
на экране, а сайт проверки показывает прежний адрес и «Прокси: не
используется». Формально всё верно, по сути — не работает.

Здесь второй, недостающий шаг: сказать Windows ходить через
`127.0.0.1:10808`. Настройка та же самая, что в «Параметры → Сеть и
Интернет → Прокси», только руками её выставлять не надо.

## Что именно правится

Ветка реестра текущего пользователя:

    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings
        ProxyEnable   1
        ProxyServer   socks=127.0.0.1:10808
        ProxyOverride <local>;127.0.0.1;...

Права администратора не нужны: ветка пользовательская. Браузеры на
Chromium и Edge читают её же, Firefox — нет, у него свои настройки.

## Про восстановление

Прежние значения запоминаются перед включением и возвращаются при
выключении. Без этого выход из программы оставил бы систему с прокси,
которого больше нет, — то есть без интернета вообще. Поэтому же
восстановление вызывается и при закрытии приложения.
"""

from __future__ import annotations


#: Ветка настроек прокси текущего пользователя.
_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

#: Адреса, которые ходят напрямую, минуя прокси. Без этого локальные
#: службы и сама проверка «жив ли прокси» пошли бы через него же.
BYPASS = "<local>;127.0.0.1;localhost;192.168.*;10.*;172.16.*"

#: Что было до нас. Заполняется при включении, читается при выключении.
_SAVED: dict | None = None


def is_supported() -> bool:
    """Умеем ли мы править системный прокси на этой машине.

    Смотрим на платформу, а не только на импорт winreg. Модуль с таким
    именем нашёлся и на Linux — заглушкой, без нужных имён, — и проверка
    отвечала «умеем», а следом всё падало на KEY_WRITE.
    """
    import sys

    if sys.platform != "win32":
        return False

    try:
        import winreg  # noqa: F401
    except Exception:
        return False
    return True


def _open_key(write: bool = False):
    import winreg

    access = winreg.KEY_READ | (winreg.KEY_WRITE if write else 0)
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_PATH, 0, access)


def _read_current() -> dict:
    import winreg

    values: dict = {"enable": 0, "server": "", "override": ""}
    try:
        with _open_key() as key:
            for name, field in (("ProxyEnable", "enable"), ("ProxyServer", "server"), ("ProxyOverride", "override")):
                try:
                    values[field] = winreg.QueryValueEx(key, name)[0]
                except FileNotFoundError:
                    pass
    except Exception:
        pass
    return values


def _apply(*, enable: int, server: str, override: str) -> None:
    import winreg

    with _open_key(write=True) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, int(enable))
        if server:
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, str(server))
        if override:
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, str(override))

    _notify_windows()


def _notify_windows() -> None:
    """Просит Windows перечитать настройки.

    Без этого уже запущенный браузер продолжает ходить напрямую: он
    узнаёт о смене только по этому уведомлению, а не по самой записи в
    реестре.
    """
    try:
        import ctypes

        internet = ctypes.windll.Wininet
        # 39 — INTERNET_OPTION_SETTINGS_CHANGED, 37 — REFRESH.
        internet.InternetSetOptionW(0, 39, 0, 0)
        internet.InternetSetOptionW(0, 37, 0, 0)
    except Exception:
        pass


def enable(address: str) -> tuple[bool, str]:
    """Включает системный прокси на переданный адрес."""
    global _SAVED

    if not is_supported():
        return (False, "Системный прокси настраивается только на Windows")

    try:
        if _SAVED is None:
            _SAVED = _read_current()
        _apply(enable=1, server=f"socks={address}", override=BYPASS)
    except Exception as exc:
        return (False, f"Не удалось включить системный прокси: {exc}")

    return (True, "")


def disable() -> tuple[bool, str]:
    """Возвращает настройки прокси в прежний вид."""
    global _SAVED

    if not is_supported():
        return (True, "")

    saved = _SAVED or {"enable": 0, "server": "", "override": ""}
    try:
        _apply(
            enable=int(saved.get("enable") or 0),
            server=str(saved.get("server") or ""),
            override=str(saved.get("override") or ""),
        )
    except Exception as exc:
        return (False, f"Не удалось вернуть настройки прокси: {exc}")

    _SAVED = None
    return (True, "")


def is_enabled_for(address: str) -> bool:
    """Ходит ли система именно через наш прокси."""
    current = _read_current()
    return bool(current.get("enable")) and str(address) in str(current.get("server") or "")


def clear_stale(address: str) -> bool:
    """Снимает нашу настройку прокси, если ядра за ней уже нет.

    Нужна при запуске. Приложение можно закрыть не по-людски — снять
    задачу, обесточить машину, — и тогда в реестре остаётся указание
    ходить через порт, которого больше нет. Windows слушается: браузер
    перестаёт открывать сайты, и виноватым выглядит net67.

    Возвращает True, если настройку пришлось снять.
    """
    if not is_supported():
        return False

    if not is_enabled_for(address):
        return False

    from vpn.xray import is_port_open

    host, _, port = str(address).partition(":")
    try:
        if is_port_open(int(port or 0), host=host or "127.0.0.1"):
            # Порт слушают — значит ядро живо, настройка при деле.
            return False
    except Exception:
        pass

    _apply(enable=0, server="", override="")
    return True


__all__ = ["BYPASS", "disable", "enable", "is_enabled_for", "is_supported"]
