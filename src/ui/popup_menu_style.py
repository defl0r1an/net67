from __future__ import annotations

import sys


_ROUND_MENU_HAIRLINE_BEGIN = "/* zapretgui-round-menu-hairline-begin */"
_ROUND_MENU_HAIRLINE_END = "/* zapretgui-round-menu-hairline-end */"

# DWM на Windows 11 рисует нативную 1px-рамку вокруг popup-окон, у которых
# включён non-client rendering (addMenuShadowEffect в qframelesswindow).
# Эта рамка компонуется DWM поверх Qt и недосягаема для QSS — убирается
# только атрибутом DWMWA_BORDER_COLOR со значением COLOR_NONE.
_DWMWA_BORDER_COLOR = 34
_DWMWA_COLOR_NONE = 0xFFFFFFFE


def _is_windows_11_or_newer() -> bool:
    try:
        return sys.platform == "win32" and sys.getwindowsversion().build >= 22000
    except Exception:
        return False


def _round_menu_hairline_border_qss() -> str:
    try:
        from qfluentwidgets import isDarkTheme

        is_light = not isDarkTheme()
    except Exception:
        is_light = False

    if is_light:
        return "MenuActionListWidget { border-color: rgba(0, 0, 0, 0.06); }"

    return "MenuActionListWidget { border-color: rgba(255, 255, 255, 0.00); }"


def _marked_round_menu_hairline_qss() -> str:
    return "\n".join(
        (
            _ROUND_MENU_HAIRLINE_BEGIN,
            _round_menu_hairline_border_qss(),
            _ROUND_MENU_HAIRLINE_END,
        )
    )


def _strip_marked_round_menu_hairline_qss(style_sheet: str) -> str:
    source = str(style_sheet or "")
    begin = source.find(_ROUND_MENU_HAIRLINE_BEGIN)
    if begin < 0:
        return source.strip()

    end = source.find(_ROUND_MENU_HAIRLINE_END, begin)
    if end < 0:
        return source.replace(_ROUND_MENU_HAIRLINE_BEGIN, "").strip()

    end += len(_ROUND_MENU_HAIRLINE_END)
    before = source[:begin].rstrip()
    after = source[end:].lstrip()
    return "\n".join(part for part in (before, after) if part).strip()


def _with_round_menu_hairline_qss(style_sheet: str) -> str:
    base = _strip_marked_round_menu_hairline_qss(style_sheet)
    fix = _marked_round_menu_hairline_qss()
    if not base:
        return fix
    return f"{base}\n{fix}"


def _apply_round_menu_hairline_qss(menu) -> None:
    if menu is None:
        return
    if not _is_windows_11_or_newer():
        return

    try:
        current = str(menu.styleSheet() or "")
        updated = _with_round_menu_hairline_qss(current)
        if updated != current:
            menu.setStyleSheet(updated)
    except Exception:
        pass


def _remove_native_menu_border(window) -> None:
    """Убирает нативную DWM-рамку popup-окна меню (Windows 11)."""
    if window is None or not _is_windows_11_or_newer():
        return

    try:
        import ctypes

        hwnd = int(window.winId())
        if hwnd == 0:
            return
        color = ctypes.c_uint(_DWMWA_COLOR_NONE)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint(_DWMWA_BORDER_COLOR),
            ctypes.byref(color),
            ctypes.sizeof(color),
        )
    except Exception:
        pass


def _install_native_border_removal(widget) -> None:
    """Ставит Show-фильтр, снимающий DWM-рамку при каждом показе меню."""
    if widget is None or not _is_windows_11_or_newer():
        return
    if bool(getattr(widget, "_zapretgui_menu_border_filter_installed", False)):
        return

    try:
        from PyQt6.QtCore import QEvent, QObject

        class _MenuBorderFilter(QObject):
            def eventFilter(self, watched, event):
                if event.type() == QEvent.Type.Show:
                    try:
                        _remove_native_menu_border(watched.window())
                    except Exception:
                        pass
                return False

        border_filter = _MenuBorderFilter(widget)
        widget.installEventFilter(border_filter)
        widget._zapretgui_menu_border_filter_installed = True
    except Exception:
        pass


def _source_contains_round_menu_style(source) -> bool:
    try:
        from qfluentwidgets import FluentStyleSheet

        if source is FluentStyleSheet.MENU:
            return True
    except Exception:
        pass

    for child in getattr(source, "sources", []) or ():
        if _source_contains_round_menu_style(child):
            return True
    return False


def install_global_round_menu_hairline_fix(app=None) -> None:
    """Один раз подключает Win11-фикс для всех qfluentwidgets RoundMenu."""

    if not _is_windows_11_or_newer():
        return

    try:
        import qfluentwidgets.common.style_sheet as fluent_style_sheet
    except Exception:
        return
    _ = app

    current_set_style_sheet = fluent_style_sheet.setStyleSheet
    if bool(getattr(current_set_style_sheet, "_zapretgui_round_menu_hairline_patch_installed", False)):
        return

    original_set_style_sheet = current_set_style_sheet

    def _zapretgui_set_style_sheet(widget, source, *args, **kwargs):
        result = original_set_style_sheet(widget, source, *args, **kwargs)
        if _source_contains_round_menu_style(source):
            _apply_round_menu_hairline_qss(widget)
            _install_native_border_removal(widget)
        return result

    setattr(_zapretgui_set_style_sheet, "_zapretgui_round_menu_hairline_patch_installed", True)
    setattr(_zapretgui_set_style_sheet, "_zapretgui_round_menu_hairline_original", original_set_style_sheet)
    fluent_style_sheet.setStyleSheet = _zapretgui_set_style_sheet


def suppress_round_menu_hairline(menu) -> None:
    """Совместимость для старых вызовов: сам фикс теперь ставится глобально."""

    _apply_round_menu_hairline_qss(menu)
    _install_native_border_removal(menu)


__all__ = ["install_global_round_menu_hairline_fix", "suppress_round_menu_hairline"]
