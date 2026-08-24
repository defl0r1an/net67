"""Надёжная проверка прав администратора.

`shell32.IsUserAnAdmin()` — старая функция, и на неё нельзя полагаться
одну. Она смотрит на членство в группе администраторов у текущего токена
потока, а не на то, повышен ли процесс. В части сборок и конфигураций
Windows она возвращает 0 у процесса, который на самом деле запущен с
повышением. Именно из-за этого отключение Windows Defender у людей
упиралось в «Требуются права администратора», хотя движок обхода —
которому права нужны не меньше — работал.

Здесь права проверяются по токену процесса: `TokenElevation` отвечает
ровно на нужный вопрос — повышен процесс или нет. Старый вызов оставлен
запасным: если он говорит «админ», значит админ, даже когда токен
прочитать не удалось.
"""

from __future__ import annotations

from log.log import log


def _elevation_from_token() -> bool | None:
    """Повышен ли процесс, по данным его токена.

    None — определить не удалось (не Windows, отказ API). Тогда решает
    запасная проверка, а не этот ответ.
    """
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return None

    if not hasattr(ctypes, "windll"):
        return None

    TOKEN_QUERY = 0x0008
    TOKEN_ELEVATION = 20  # TokenElevation в TOKEN_INFORMATION_CLASS

    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        TOKEN_QUERY,
        ctypes.byref(token),
    ):
        return None

    try:
        elevation = wintypes.DWORD()
        returned = wintypes.DWORD()
        ok = advapi32.GetTokenInformation(
            token,
            TOKEN_ELEVATION,
            ctypes.byref(elevation),
            ctypes.sizeof(elevation),
            ctypes.byref(returned),
        )
        if not ok:
            return None
        return elevation.value != 0
    except Exception:
        return None
    finally:
        try:
            kernel32.CloseHandle(token)
        except Exception:
            pass


def _is_user_an_admin() -> bool | None:
    """Старая проверка членства в группе администраторов."""
    try:
        import ctypes
    except Exception:
        return None
    if not hasattr(ctypes, "windll"):
        return None
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return None


def is_admin() -> bool:
    """Запущен ли процесс с правами администратора.

    Токен — основной источник. Старый вызов — запасной и только на
    повышение: «да» от любого из двух считаем «да», потому что ложное
    «нет» здесь дороже — из-за него функции блокировались у тех, у кого
    права на самом деле были.
    """
    by_token = _elevation_from_token()
    if by_token is not None:
        if by_token:
            return True
        # Токен говорит «не повышен». Доверяем, но старой проверке даём
        # последнее слово на случай нестандартной конфигурации.
        legacy = _is_user_an_admin()
        return bool(legacy)

    legacy = _is_user_an_admin()
    if legacy is None:
        log("Права администратора определить не удалось", "DEBUG")
        return False
    return bool(legacy)


__all__ = ["is_admin"]
