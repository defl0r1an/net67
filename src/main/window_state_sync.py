from __future__ import annotations

from app.initial_ui_state import build_initial_ui_state
from app.state_store import AppUiState


class WindowStateSyncMixin:
    @staticmethod
    def _build_initial_ui_state() -> AppUiState:
        return build_initial_ui_state()
