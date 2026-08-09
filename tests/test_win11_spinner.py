from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock


class _Timer:
    def __init__(self, active: bool = False) -> None:
        self._active = bool(active)
        self.start_calls: list[int] = []
        self.stop_calls = 0

    def isActive(self) -> bool:  # noqa: N802
        return self._active

    def start(self, interval_ms: int) -> None:
        self.start_calls.append(int(interval_ms))
        self._active = True

    def stop(self) -> None:
        self.stop_calls += 1
        self._active = False


class Win11SpinnerTests(unittest.TestCase):
    def test_start_skips_restarting_active_timer(self) -> None:
        from ui.widgets.win11_spinner import Win11Spinner

        timer = _Timer(active=False)
        spinner = SimpleNamespace(_timer=timer, show=Mock())

        Win11Spinner.start(spinner)
        Win11Spinner.start(spinner)

        self.assertEqual(timer.start_calls, [16])
        self.assertEqual(spinner.show.call_count, 1)

    def test_stop_skips_stopping_inactive_timer(self) -> None:
        from ui.widgets.win11_spinner import Win11Spinner

        timer = _Timer(active=True)
        spinner = SimpleNamespace(_timer=timer, hide=Mock())

        Win11Spinner.stop(spinner)
        Win11Spinner.stop(spinner)

        self.assertEqual(timer.stop_calls, 1)
        self.assertEqual(spinner.hide.call_count, 1)


if __name__ == "__main__":
    unittest.main()
