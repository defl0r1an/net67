from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WindowStateActions:
    window: Any
    ui_state_store: Any

    def set_window_opacity(self, value: int) -> None:
        try:
            from ui.window_appearance_state import apply_window_opacity_value

            self.ui_state_store.set_window_opacity_value(value)
            apply_window_opacity_value(self.window, value)
        except Exception as exc:
            from log.log import log

            log(f"❌ Ошибка при установке прозрачности окна: {exc}", "ERROR")


__all__ = ["WindowStateActions"]
