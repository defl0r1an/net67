from __future__ import annotations

import time

from PyQt6.QtCore import QThread, pyqtSignal

from log.log import log
from profile.list_apply_signature import profile_payload_apply_signature_base
from ui.performance_metrics import log_ui_timing_since


class ProfileListLoadResult:
    def __init__(self, *, payload, view_state=None, apply_signature_base=None) -> None:
        self.payload = payload
        self.view_state = view_state
        self.apply_signature_base = (
            tuple(apply_signature_base)
            if apply_signature_base is not None
            else profile_payload_apply_signature_base(payload, view_state=view_state)
        )


class ProfileListLoadWorker(QThread):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id: int, load_profiles, build_view_state=None, parent=None):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._load_profiles = load_profiles
        self._build_view_state = build_view_state

    def run(self) -> None:
        started_at = time.perf_counter()
        try:
            payload = self._load_profiles()
        except Exception as exc:
            log(f"ProfileListLoadWorker: не удалось загрузить profile payload: {exc}", "ERROR")
            self.failed.emit(self._request_id, str(exc))
            return
        if isinstance(payload, ProfileListLoadResult):
            log_ui_timing_since(
                "worker",
                "profile_list",
                "profile_feature.worker.list_profiles.total",
                started_at,
                important=True,
            )
            self.loaded.emit(self._request_id, payload)
            return
        view_state = None
        if callable(self._build_view_state):
            try:
                view_state = self._build_view_state(tuple(getattr(payload, "items", ()) or ()))
            except Exception as exc:
                log(f"ProfileListLoadWorker: не удалось подготовить view state profile: {exc}", "ERROR")
                self.failed.emit(self._request_id, str(exc))
                return
        log_ui_timing_since(
            "worker",
            "profile_list",
            "profile_feature.worker.list_profiles.total",
            started_at,
            important=True,
        )
        self.loaded.emit(self._request_id, ProfileListLoadResult(payload=payload, view_state=view_state))
