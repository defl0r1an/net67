from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True)
class AutoDpiUpdateResult:
    enabled: bool
    message: str
    title: str


@dataclass(slots=True)
class ProgramSettingActionResult:
    level: str
    title: str
    content: str
    revert_checked: bool | None
    final_status: str


def is_user_admin() -> bool:
    # Через токен процесса, а не через IsUserAnAdmin: старый вызов
    # возвращал 0 у повышенного процесса, и отключение Windows Defender
    # упиралось в «Требуются права администратора» всегда. См.
    # startup/admin_rights.py.
    from startup.admin_rights import is_admin

    return bool(is_admin())


def is_auto_dpi_enabled() -> bool:
    try:
        from settings.store import get_dpi_autostart

        return bool(get_dpi_autostart())
    except Exception:
        return False


def set_auto_dpi_enabled(
    enabled: bool,
    *,
    status_callback: Callable[[str], None] | None = None,
) -> AutoDpiUpdateResult:
    _ = status_callback
    try:
        from settings.store import set_dpi_autostart

        set_dpi_autostart(bool(enabled))
    except Exception:
        pass

    message = (
        "DPI будет запускаться автоматически после старта net67"
        if enabled
        else "Автозапуск обхода после старта программы отключён"
    )
    return AutoDpiUpdateResult(
        enabled=bool(enabled),
        message=message,
        title="Автозапуск обхода после старта программы",
    )


def set_gui_autostart_enabled(
    enabled: bool,
    *,
    status_callback: Callable[[str], None] | None = None,
) -> ProgramSettingActionResult:
    try:
        from autostart import public as autostart_public

        if enabled:
            result = autostart_public.enable_gui_autostart(status_cb=status_callback)
            if getattr(result, "success", False):
                autostart_public.save_gui_autostart_enabled(True)
                return ProgramSettingActionResult(
                    level="success",
                    title="Автозапуск включён",
                    content="net67 будет запускаться в трее при входе в Windows.",
                    revert_checked=None,
                    final_status="Готово",
                )
            message = str(getattr(result, "message", "") or "Не удалось включить автозапуск.")
            return ProgramSettingActionResult(
                level="warning" if getattr(result, "restart_requested", False) else "error",
                title="Автозапуск не включён",
                content=message,
                revert_checked=False,
                final_status="",
            )

        result = autostart_public.disable_gui_autostart()
        if getattr(result, "success", False):
            autostart_public.save_gui_autostart_enabled(False)
            return ProgramSettingActionResult(
                level="success",
                title="Автозапуск отключён",
                content="net67 больше не будет запускаться вместе с Windows.",
                revert_checked=None,
                final_status="Готово",
            )
        return ProgramSettingActionResult(
            level="error",
            title="Автозапуск не отключён",
            content=str(getattr(result, "message", "") or "Не удалось отключить автозапуск."),
            revert_checked=True,
            final_status="",
        )
    except Exception as e:
        return ProgramSettingActionResult(
            level="error",
            title="Ошибка автозапуска",
            content=f"Не удалось изменить автозапуск: {e}",
            revert_checked=None,
            final_status="",
        )


def ensure_gui_autostart_migrated() -> bool:
    from autostart.public import ensure_gui_autostart_migrated as migrate_gui_autostart

    return bool(migrate_gui_autostart())


def set_tray_close_mode(mode: str) -> str:
    from settings.store import get_tray_close_mode, set_tray_close_mode

    set_tray_close_mode(str(mode or "normal"))
    return get_tray_close_mode()


def save_ui_state_settings(values: dict) -> dict:
    from settings.store import set_ui_state_settings

    return set_ui_state_settings(dict(values or {}))


def set_defender_disabled(
    disable: bool,
    *,
    status_callback: Callable[[str], None] | None = None,
) -> ProgramSettingActionResult:
    try:
        from windows_features.defender_manager import WindowsDefenderManager
        from windows_features.defender_manager import set_defender_disabled as remember_defender_disabled

        manager = WindowsDefenderManager(status_callback=status_callback)

        if disable:
            # Пока включена защита от подделки, Windows не даёт отключить
            # Defender из программы — записи в реестр возвращают «Отказано
            # в доступе». Снять её может только сам человек в «Безопасности
            # Windows»; обходить её программа не будет. Поэтому не делаем
            # вид, что сработало, а ведём человека снять защиту.
            if manager.is_tamper_protection_enabled() is True:
                manager.open_tamper_protection_settings()
                return ProgramSettingActionResult(
                    level="warning",
                    title="Сначала снимите защиту от подделки",
                    content=(
                        "Windows не даёт отключить Defender, пока включена «Защита от подделки».\n\n"
                        "Открылось окно «Безопасность Windows». Выключите там «Защита от подделки» "
                        "(Tamper Protection), вернитесь и снова включите этот переключатель."
                    ),
                    revert_checked=False,
                    final_status="Готово",
                )

            success, count = manager.disable_defender()
            if success:
                remember_defender_disabled(True)
                return ProgramSettingActionResult(
                    level="success",
                    title="Windows Defender отключен",
                    content=(
                        "Windows Defender успешно отключен. "
                        f"Применено {count} настроек. Может потребоваться перезагрузка."
                    ),
                    revert_checked=None,
                    final_status="Готово",
                )
            # Не отключился. Чаще всего защиту от подделки включили заново
            # посреди операции — снова ведём к ней, а не пишем глухое «ошибка».
            if manager.is_tamper_protection_enabled() is True:
                manager.open_tamper_protection_settings()
                return ProgramSettingActionResult(
                    level="warning",
                    title="Сначала снимите защиту от подделки",
                    content=(
                        "Defender не отключился: включена «Защита от подделки».\n\n"
                        "Выключите её в открывшемся окне «Безопасность Windows» и попробуйте снова."
                    ),
                    revert_checked=False,
                    final_status="Готово",
                )
            return ProgramSettingActionResult(
                level="error",
                title="Не удалось отключить Windows Defender",
                content=(
                    "Часть настроек заблокирована системой. Проверьте, что выключена "
                    "«Защита от подделки» в «Безопасности Windows», и попробуйте снова."
                ),
                revert_checked=False,
                final_status="Готово",
            )

        success, _count = manager.enable_defender()
        if success:
            remember_defender_disabled(False)
            return ProgramSettingActionResult(
                level="success",
                title="Windows Defender включен",
                content=(
                    "Windows Defender успешно включен. "
                    "Защита вашего компьютера восстановлена."
                ),
                revert_checked=None,
                final_status="Готово",
            )
        return ProgramSettingActionResult(
            level="warning",
            title="Частичный успех",
            content=(
                "Windows Defender включен частично. "
                "Некоторые настройки могут потребовать ручного исправления."
            ),
            revert_checked=None,
            final_status="Готово",
        )
    except Exception as e:
        return ProgramSettingActionResult(
            level="error",
            title="Ошибка",
            content=f"Произошла ошибка при изменении настроек Windows Defender: {e}",
            revert_checked=None,
            final_status="",
        )


def set_max_block_enabled(
    enable: bool,
    *,
    status_callback: Callable[[str], None] | None = None,
) -> ProgramSettingActionResult:
    try:
        from windows_features.max_blocker import MaxBlockerManager

        manager = MaxBlockerManager(status_callback=status_callback)

        if enable:
            success, message = manager.enable_blocking()
            if success:
                return ProgramSettingActionResult(
                    level="success",
                    title="Блокировка включена",
                    content=message,
                    revert_checked=None,
                    final_status="Готово",
                )
            return ProgramSettingActionResult(
                level="warning",
                title="Ошибка",
                content=f"Не удалось полностью включить блокировку: {message}",
                revert_checked=False,
                final_status="Готово",
            )

        success, message = manager.disable_blocking()
        if success:
            return ProgramSettingActionResult(
                level="success",
                title="Блокировка отключена",
                content=message,
                revert_checked=None,
                final_status="Готово",
            )
        return ProgramSettingActionResult(
            level="warning",
            title="Ошибка",
            content=f"Не удалось полностью отключить блокировку: {message}",
            revert_checked=None,
            final_status="Готово",
        )
    except Exception as e:
        return ProgramSettingActionResult(
            level="error",
            title="Ошибка",
            content=f"Ошибка при переключении блокировки MAX: {e}",
            revert_checked=None,
            final_status="",
        )


def set_state_media_block_enabled(
    enable: bool,
    *,
    status_callback: Callable[[str], None] | None = None,
) -> ProgramSettingActionResult:
    try:
        from windows_features.state_media_blocker import RussianStateMediaBlockerManager

        manager = RussianStateMediaBlockerManager(status_callback=status_callback)

        if enable:
            success, message = manager.enable_blocking()
            if success:
                return ProgramSettingActionResult(
                    level="success",
                    title="Блокировка включена",
                    content=message,
                    revert_checked=None,
                    final_status="Готово",
                )
            return ProgramSettingActionResult(
                level="warning",
                title="Блокировка не включена",
                content=message,
                revert_checked=False,
                final_status="Готово",
            )

        success, message = manager.disable_blocking()
        if success:
            return ProgramSettingActionResult(
                level="success",
                title="Блокировка отключена",
                content=message,
                revert_checked=None,
                final_status="Готово",
            )
        return ProgramSettingActionResult(
            level="warning",
            title="Блокировка не отключена",
            content=message,
            revert_checked=True,
            final_status="Готово",
        )
    except Exception as e:
        return ProgramSettingActionResult(
            level="error",
            title="Ошибка",
            content=f"Ошибка при переключении блокировки государственных СМИ РФ: {e}",
            revert_checked=None,
            final_status="",
        )
