"""Значки DNS-профилей на плитке hosts стоят подряд, без дыр.

Место значка совпадало с номером профиля в каталоге, и профиль, которого
у сервиса нет, оставлял пустое место. После добавления AstraCat у AMD,
Dyson и Posthog посреди ряда зияли дыры — владелец попросил ставить
значки по порядку.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from PyQt6.QtCore import QRect  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

from hosts.ui.services_tiles import HostsChoice, HostsTile, HostsTilesGrid  # noqa: E402


def _choice(profile_id: str, available: bool = True) -> HostsChoice:
    return HostsChoice(profile_id, profile_id, "fa5s.circle", "#888888", available=available)


class PackedChoicesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = HostsTilesGrid()
        self.grid.resize(1200, 400)
        self.addCleanup(self.grid.deleteLater)
        self.tile = HostsTile(
            kind="tile",
            title="AMD",
            key="AMD",
            choices=(_choice("p1"), _choice("p2", available=False), _choice("p3"), _choice("p4", available=False), _choice("p5")),
        )
        self.grid.set_tiles([self.tile])
        QApplication.processEvents()
        self.rect = self.grid.tile_rect("AMD")

    def test_available_profiles_take_places_in_a_row(self) -> None:
        self.assertEqual(self.grid._placed_choices(self.tile, self.rect), [(0, 0), (2, 1), (4, 2)])
        self.assertEqual(self.grid.choice_rect("AMD", "p3"), self.grid._choice_rect(self.rect, 1))
        self.assertEqual(self.grid.choice_rect("AMD", "p5"), self.grid._choice_rect(self.rect, 2))
        self.assertTrue(self.grid.choice_rect("AMD", "p2").isNull())

    def test_click_on_a_place_picks_the_profile_standing_there(self) -> None:
        chosen = []
        self.grid.profile_chosen.connect(lambda key, profile: chosen.append((key, profile)))
        index = self.grid._index_of("AMD")
        point = self.grid._choice_rect(self.rect, 1).center()
        self.assertEqual(self.grid._choice_at(index, point), 2)
        # Четвёртого места нет: там пусто, а не скрытый профиль.
        self.assertEqual(self.grid._choice_at(index, self.grid._choice_rect(self.rect, 3).center()), -1)

    def test_places_never_exceed_the_tile_width(self) -> None:
        narrow = QRect(self.rect.left(), self.rect.top(), 130, self.rect.height())
        many = HostsTile(kind="tile", title="X", key="X", choices=tuple(_choice(f"p{i}") for i in range(10)))
        placed = self.grid._placed_choices(many, narrow)
        self.assertEqual(len(placed), self.grid._visible_slots(narrow))


if __name__ == "__main__":
    unittest.main()
