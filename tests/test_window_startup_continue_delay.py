from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class WindowStartupContinueDelayTests(unittest.TestCase):
    def test_continue_after_ui_ready_has_no_fixed_timer_delay(self) -> None:
        from main import window_startup

        self.assertEqual(window_startup.STARTUP_CONTINUE_AFTER_UI_READY_MS, 0)


if __name__ == "__main__":
    unittest.main()
