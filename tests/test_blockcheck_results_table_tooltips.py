"""Таблица результатов BlockCheck: подсказки и текст для диктора.

На таблице стоит перехватчик фирменных подсказок, а он читает свою роль
данных. Ячейки получали текст через setToolTip — в стандартную роль, —
и перехватчик, не найдя ничего, гасил событие: подсказки в результатах
не показывались вовсе. Диктор же читал ячейку саму по себе и на «Не
открылся» не говорил, какой сайт.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class BlockcheckResultsTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _table(self):
        from blockcheck.ui.check_results import BlockcheckSitesTable

        table = BlockcheckSitesTable()
        self.addCleanup(table.deleteLater)
        table._add_row("YouTube", "error", "Не открылся", "TLS сброшен", "Соединение сброшено после ClientHello")
        return table

    def test_tooltip_lands_in_the_role_the_fluent_filter_reads(self) -> None:
        from ui.widgets.fluent_item_tooltip import FLUENT_ITEM_TOOLTIP_ROLE

        table = self._table()
        for column in range(3):
            item = table.item(0, column)
            with self.subTest(column=column):
                self.assertEqual(item.data(FLUENT_ITEM_TOOLTIP_ROLE), "Соединение сброшено после ClientHello")
                # Системной подсказки нет: перехватчик её всё равно погасил бы.
                self.assertEqual(item.toolTip(), "")

    def test_every_cell_speaks_the_whole_row(self) -> None:
        from PyQt6.QtCore import Qt

        table = self._table()
        for column in range(3):
            spoken = table.item(0, column).data(Qt.ItemDataRole.AccessibleTextRole)
            with self.subTest(column=column):
                self.assertIn("YouTube", spoken)
                self.assertIn("Не открылся", spoken)


if __name__ == "__main__":
    unittest.main()
