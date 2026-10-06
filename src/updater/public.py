from __future__ import annotations

from updater.commands import (
    is_auto_update_enabled,
    open_update_channel,
    pending_whats_new,
    prepare_server_full_check,
    remember_skipped_update,
    remember_whats_new,
    restart_dpi_after_update,
    retry_server_check_without_dpi,
    run_startup_update_check,
    set_auto_update_enabled,
    stop_dpi_for_download,
    stop_dpi_for_update,
)

# Фасад обновлятора (app/feature_facades/updater.py) берёт команды только
# отсюда. В 0.14.67 три команды окна обновления — «Пропустить версию»,
# сохранение «Что нового» перед установкой и показ его после — были в
# updater/commands.py, но не здесь: AttributeError ловился, и кнопка
# «Установить» в окне при запуске молча ничего не делала. Сверку фасадов с
# их модулями держит tests/test_feature_facade_command_exports.py.
__all__ = [
    "is_auto_update_enabled",
    "open_update_channel",
    "pending_whats_new",
    "prepare_server_full_check",
    "remember_skipped_update",
    "remember_whats_new",
    "restart_dpi_after_update",
    "retry_server_check_without_dpi",
    "run_startup_update_check",
    "set_auto_update_enabled",
    "stop_dpi_for_download",
    "stop_dpi_for_update",
]
