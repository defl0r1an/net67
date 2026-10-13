"""Список серверов VPN: группа сворачивается движением, а не за кадр.

Список пересобирался на каждое сворачивание группы: серверы пропадали
мгновенно, нижние строки прыгали вверх. Теперь строки гаснут и
сжимаются волной, а при раскрытии вырастают; при выключенных анимациях —
как раньше, сразу.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtWidgets import QApplication, QListWidget  # noqa: E402


def _wait(seconds: float, probe=None) -> list:
    samples = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if probe is not None:
            samples.append(probe())
        time.sleep(0.005)
    return samples


class ServerListMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _list(self, animations: bool = True):
        from vpn.ui.server_list_motion import attach_server_list_motion

        switch = patch("vpn.ui.server_list_motion.are_animations_enabled", return_value=animations)
        switch.start()
        self.addCleanup(switch.stop)
        view = QListWidget()
        for text in ("Подписка", "Германия", "Нидерланды", "Финляндия"):
            view.addItem(text)
        view.resize(300, 300)
        view.show()
        self.addCleanup(view.deleteLater)
        QApplication.processEvents()
        return view, attach_server_list_motion(view)

    def test_leaving_rows_shrink_through_intermediate_heights_then_finish(self) -> None:
        from vpn.ui.server_list_motion import ROW_LEAVE_MS, ROW_STAGGER_MS

        view, motion = self._list()
        full = view.visualItemRect(view.item(1)).height()
        finished: list[int] = []

        self.assertTrue(motion.leave([1, 2, 3], on_finished=lambda: finished.append(1)))
        heights = _wait((ROW_LEAVE_MS + 3 * ROW_STAGGER_MS) / 1000 + 0.2,
                        probe=lambda: view.visualItemRect(view.item(1)).height())

        self.assertEqual(finished, [1])
        self.assertTrue(any(0 < h < full for h in heights), heights)
        self.assertEqual(heights, sorted(heights, reverse=True))
        self.assertEqual(motion.progress(1), 0.0)
        # Заголовок не трогали.
        self.assertEqual(motion.progress(0), 1.0)

    def test_appearing_rows_grow_from_zero(self) -> None:
        view, motion = self._list()
        self.assertTrue(motion.appear([1, 2]))
        self.assertLess(motion.progress(2), 1.0)
        _wait(0.5)
        self.assertEqual(motion.progress(1), 1.0)
        self.assertFalse(motion.busy())

    def test_without_animations_caller_does_it_at_once(self) -> None:
        _view, motion = self._list(animations=False)
        self.assertFalse(motion.leave([1], on_finished=lambda: None))
        self.assertFalse(motion.appear([1]))

    def test_interrupted_leave_continues_from_current_value(self) -> None:
        view, motion = self._list()
        motion.leave([1], on_finished=lambda: None)
        _wait(0.08)
        caught = motion.progress(1)
        self.assertTrue(0.0 < caught < 1.0, caught)
        motion.appear([1])
        self.assertAlmostEqual(motion.progress(1), caught, delta=0.08)


class VpnPageGroupCollapseTests(unittest.TestCase):
    def test_collapse_click_animates_then_rebuilds_with_group_closed(self) -> None:
        from vpn.ui.page import _GROUP_KEY_ROLE

        app = QApplication.instance() or QApplication([])
        _ = app
        from types import SimpleNamespace

        page = SimpleNamespace()
        view, _motion = ServerListMotionTests._list(self, animations=True)
        header = view.item(0)
        header.setData(_GROUP_KEY_ROLE, "sub")
        header.setText("▾   Подписка")
        rebuilt: list[int] = []

        from vpn.ui.page import VpnPage

        page.profile_list = view
        page._row_profiles = [-1, 0, 1, 2]
        page._collapsed_groups = set()
        page._list_motion = _motion
        page._refill_combo = lambda: rebuilt.append(1)
        page._group_member_rows = lambda row: VpnPage._group_member_rows(page, row)
        page._group_header_row = lambda key: VpnPage._group_header_row(page, key)

        VpnPage._on_list_item_clicked(page, header)

        self.assertEqual(page._collapsed_groups, {"sub"})
        self.assertTrue(header.text().startswith("▸"))
        self.assertEqual(rebuilt, [])  # пересборка — после ухода строк, не сразу
        _wait(0.6)
        self.assertEqual(rebuilt, [1])


if __name__ == "__main__":
    unittest.main()
