from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from winws_runtime.engine.driver import DriverPreflight
import winws_runtime.runtime.start_flow as start_flow


class _Owner:
    def __init__(self) -> None:
        self._dpi_start_thread = None
        self._pending_launch_warnings = None
        self.failed_with: str | None = None

    def _mark_runtime_failed(self, text: str) -> None:
        self.failed_with = text


class DriverPreflightStartFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = (
            start_flow.set_runtime_owner_status,
            start_flow.show_launch_error_top,
            start_flow.handle_conflicting_processes_before_start,
        )
        start_flow.set_runtime_owner_status = lambda *a, **k: None
        start_flow.show_launch_error_top = lambda *a, **k: None
        start_flow.handle_conflicting_processes_before_start = lambda *a, **k: True
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        (
            start_flow.set_runtime_owner_status,
            start_flow.show_launch_error_top,
            start_flow.handle_conflicting_processes_before_start,
        ) = self._saved

    def test_when_driver_not_startable_recovers_automatically(self) -> None:
        owner = _Owner()
        not_ok = DriverPreflight(ok=False, message="Служба зависла в stop_pending")
        mock_recover = Mock(return_value=True)

        with patch("winws_runtime.runtime.system_ops.ensure_windivert_driver_startable_runtime", return_value=not_ok):
            with patch("winws_runtime.runtime.system_ops.recover_windivert_runtime", mock_recover):
                accepted = start_flow.prepare_start_preflight(owner, selected_mode="test", launch_method="winws2")

        self.assertTrue(accepted)
        mock_recover.assert_called_once()
