"""Значок программы на карточках проверок стоит вровень с текстом.

Виджет значка выше самого значка — над ним запас на прыжок. Прижатый
раскладкой к верху карточки, значок висел ниже заголовка на этот запас:
17 пикселей при значке в 44. Владелец: «сделай повыше и поровнее с
текстом».
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


class MascotLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _settle(self, panel) -> None:
        panel.resize(900, 10)
        panel.show()
        self.addCleanup(panel.deleteLater)
        for _ in range(3):
            self.app.processEvents()
        panel._sync_min_height()
        panel.resize(900, panel.minimumHeight())
        for _ in range(3):
            self.app.processEvents()

    def _tops(self, panel, title) -> tuple[int, int]:
        mascot = panel.mascot
        icon_top = mascot.mapTo(panel, QPoint(0, 0)).y() + mascot.headroom()
        return icon_top, title.mapTo(panel, QPoint(0, 0)).y()

    def test_dns_card(self) -> None:
        from dns.ui.dns_check_widgets import DnsSummaryPanel

        panel = DnsSummaryPanel()
        self._settle(panel)
        icon_top, title_top = self._tops(panel, panel._icon)
        self.assertEqual(icon_top, title_top)

    def test_blockcheck_card(self) -> None:
        from blockcheck.ui.check_results import BlockcheckSummaryPanel

        panel = BlockcheckSummaryPanel()
        self._settle(panel)
        icon_top, title_top = self._tops(panel, panel._icon)
        self.assertEqual(icon_top, title_top)

    def test_strategy_scan_card(self) -> None:
        from blockcheck.ui.strategy_scan_widgets import ScanProgressPanel

        panel = ScanProgressPanel()
        self._settle(panel)
        icon_top, title_top = self._tops(panel, panel.title_label)
        self.assertEqual(icon_top, title_top)

    def test_jump_room_stays_inside_the_card(self) -> None:
        """Выше края карточки значок не поднят: она обрезала бы прыжок."""
        from dns.ui.dns_check_widgets import DnsSummaryPanel

        panel = DnsSummaryPanel()
        self._settle(panel)
        self.assertGreaterEqual(panel.mascot.mapTo(panel, QPoint(0, 0)).y(), 0)

    def test_text_keeps_to_the_top_in_a_taller_card(self) -> None:
        from dns.ui.dns_check_widgets import DnsSummaryPanel

        panel = DnsSummaryPanel()
        self._settle(panel)
        panel.resize(900, panel.minimumHeight() + 80)
        for _ in range(3):
            self.app.processEvents()
        icon_top, title_top = self._tops(panel, panel._icon)
        self.assertEqual(icon_top, title_top)


if __name__ == "__main__":
    unittest.main()
