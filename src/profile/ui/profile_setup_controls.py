"""Workflow полей редактируемых настроек profile."""

from __future__ import annotations

import re


_SIMPLE_RANGE_RE = re.compile(r"^-?(?P<mode>[nd])(?P<value>\d+)$", re.IGNORECASE)


def set_combo_by_data(combo, value: str) -> None:
    wanted = str(value or "").strip()
    for index in range(combo.count()):
        if str(combo.itemData(index) or "") == wanted:
            try:
                if int(combo.currentIndex()) == index:
                    return
            except Exception:
                pass
            combo.setCurrentIndex(index)
            return


def _set_enabled_if_changed(widget, enabled: bool) -> None:
    value = bool(enabled)
    try:
        if bool(widget.isEnabled()) == value:
            return
    except Exception:
        pass
    widget.setEnabled(value)


def _set_text_if_changed(widget, text: str) -> None:
    value = str(text or "")
    try:
        if str(widget.text()) == value:
            return
    except Exception:
        pass
    widget.setText(value)


def _clear_text_if_needed(widget) -> None:
    try:
        if str(widget.text()) == "":
            return
    except Exception:
        pass
    widget.clear()


def _set_placeholder_if_changed(widget, text: str) -> None:
    value = str(text or "")
    try:
        if str(widget.placeholderText()) == value:
            return
    except Exception:
        pass
    widget.setPlaceholderText(value)


def sync_range_value_enabled(combo, value_edit) -> None:
    mode = str(combo.itemData(combo.currentIndex()) or "").strip()
    _set_enabled_if_changed(value_edit, mode not in {"a", "x"})
    if mode in {"a", "x"}:
        _clear_text_if_needed(value_edit)
    if mode == "custom":
        _set_placeholder_if_changed(value_edit, "s1<d1")
    elif mode in {"n", "d"}:
        _set_placeholder_if_changed(value_edit, "номер")
    else:
        _set_placeholder_if_changed(value_edit, "")


def set_range_controls(combo, value_edit, expression: str) -> None:
    expr = str(expression or "").strip().lower()
    if expr in {"a", "x"}:
        set_combo_by_data(combo, expr)
        _clear_text_if_needed(value_edit)
        sync_range_value_enabled(combo, value_edit)
        return

    match = _SIMPLE_RANGE_RE.match(expr)
    if match:
        set_combo_by_data(combo, match.group("mode").lower())
        _set_text_if_changed(value_edit, match.group("value"))
        sync_range_value_enabled(combo, value_edit)
        return

    set_combo_by_data(combo, "custom")
    _set_text_if_changed(value_edit, expr)
    sync_range_value_enabled(combo, value_edit)


def range_expression_from_controls(combo, value_edit, *, default: str) -> str:
    mode = str(combo.itemData(combo.currentIndex()) or "").strip().lower()
    value = value_edit.text().strip()
    if mode in {"a", "x"}:
        return mode
    if mode in {"n", "d"}:
        return f"-{mode}{value}" if value.isdigit() else default
    if mode == "custom":
        return value or default
    return default
