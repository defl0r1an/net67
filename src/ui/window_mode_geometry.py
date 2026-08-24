"""Размер окна под простой и расширенный вид.

В простом виде в боковой панели два пункта, а на странице — кнопка
«Включить», статус и настройки программы. В окне расширенного режима под
этим оставалась половина экрана пустоты.

Модуль меняет только размер: ничего в интерфейс не добавляется.
"""

from __future__ import annotations

from config.window_metrics import get_min_size_for_mode, get_window_size_for_mode
from log.log import log


def apply_window_size_for_mode(window, advanced: bool, *, resize: bool = True) -> None:
    """Ставит минимальный и текущий размер окна под режим.

    resize=False на старте: там размер восстанавливает
    WindowGeometryRuntime из сохранённой геометрии, и перебивать его
    сразу после запуска — значит терять размер, который пользователь
    выставил руками.
    """
    if window is None:
        return

    advanced = bool(advanced)
    min_width, min_height = get_min_size_for_mode(advanced)

    try:
        window.setMinimumSize(min_width, min_height)
    except Exception as exc:
        log(f"[WINDOW] не удалось задать минимальный размер: {exc}", "DEBUG")
        return

    if not resize:
        return

    # Развёрнутое окно не трогаем: пользователь сам его развернул.
    try:
        if bool(window.isMaximized()) or bool(window.isFullScreen()):
            return
    except Exception:
        pass

    width, height = get_window_size_for_mode(advanced)
    try:
        window.resize(width, height)
        log(f"[WINDOW] размер под режим advanced={advanced}: {width}x{height}", "DEBUG")
    except Exception as exc:
        log(f"[WINDOW] не удалось изменить размер окна: {exc}", "DEBUG")


__all__ = ["apply_window_size_for_mode"]
