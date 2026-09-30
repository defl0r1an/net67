from __future__ import annotations

import inspect
import unittest

import presets.ui.control.zapret2.sections_build as zapret2_sections
from presets.ui.control.windows_features.runtime import ControlPageWindowsFeatureMixin


class ControlInternetCleanupButtonTests(unittest.TestCase):

    def test_windows_feature_mixin_waits_for_internet_cleanup_worker_on_cleanup(self) -> None:
        source = inspect.getsource(ControlPageWindowsFeatureMixin._stop_internet_cleanup_worker)

        self.assertIn("blocking=True", source)
        self.assertIn("wait_timeout_ms=45000", source)
        self.assertIn("Internet cleanup worker", source)


if __name__ == "__main__":
    unittest.main()
