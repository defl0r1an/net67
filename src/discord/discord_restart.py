from settings.store import get_discord_restart_enabled, set_discord_restart_enabled

# ----------------------------------------------------------------------
# 1.  Чтение / запись настройки в реестре
# ----------------------------------------------------------------------
def get_discord_restart_setting(default: bool = True) -> bool:
    """
    Возвращает текущее значение AutoRestartDiscord.
    Если параметра нет – отдаёт default (по-умолчанию True).
    """
    try:
        return bool(get_discord_restart_enabled())
    except Exception:
        return bool(default)


def set_discord_restart_setting(enabled: bool) -> bool:
    """
    Записывает AutoRestartDiscord = 1/0.
    Возвращает True при успехе.
    """
    return bool(set_discord_restart_enabled(bool(enabled)))
