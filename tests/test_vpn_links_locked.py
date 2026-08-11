"""Раздел подключения по ссылке закрыт до конца доработки.

Просьба была такая: вкладку «VPN» сделать неактивной и писать, что она
в разработке, но если нажать десять раз — открывать.

Отсюда два требования, которые легко потерять.

Вкладка обязана оставаться нажимаемой. Отключённая кнопка нажатий не
получает, и считать было бы нечего — поэтому «неактивная» здесь значит
«не пускает», а не «disabled».

Подсветка должна возвращаться на открытую вкладку. Иначе она горит на
разделе, который так и не открылся, и человек думает, что уже там.
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class RuleTests(unittest.TestCase):
    """Правило проверяется без Qt: оно не про интерфейс."""

    def test_ten_clicks_open_the_section(self) -> None:
        from vpn.tabs import LINKS_UNLOCK_CLICKS, locked_click_feedback

        self.assertEqual(LINKS_UNLOCK_CLICKS, 10)

        opened, _message = locked_click_feedback(LINKS_UNLOCK_CLICKS)

        self.assertTrue(opened)

    def test_nine_clicks_are_not_enough(self) -> None:
        from vpn.tabs import locked_click_feedback

        for clicks in range(1, 10):
            with self.subTest(clicks=clicks):
                opened, _message = locked_click_feedback(clicks)
                self.assertFalse(opened)

    def test_first_clicks_say_it_is_in_progress(self) -> None:
        from vpn.tabs import LINKS_LOCKED_MESSAGE, locked_click_feedback

        _opened, message = locked_click_feedback(1)

        self.assertEqual(message, LINKS_LOCKED_MESSAGE)

    def test_the_second_half_counts_down(self) -> None:
        """Иначе первые нажатия читаются как «кнопка не работает»."""
        from vpn.tabs import locked_click_feedback

        _opened, message = locked_click_feedback(9)

        self.assertIn("Осталось нажатий: 1", message)

    def test_extra_clicks_keep_it_open(self) -> None:
        from vpn.tabs import locked_click_feedback

        opened, _message = locked_click_feedback(25)

        self.assertTrue(opened)

    def test_nonsense_input_does_not_open_it(self) -> None:
        from vpn.tabs import locked_click_feedback

        for clicks in (0, -5):
            with self.subTest(clicks=clicks):
                opened, _message = locked_click_feedback(clicks)
                self.assertFalse(opened)


class PageWiringTests(unittest.TestCase):
    def test_page_counts_clicks_and_refuses_to_switch(self) -> None:
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._on_tab_changed)

        self.assertIn("_links_unlocked", source)
        self.assertIn("locked_click_feedback", source)
        # Возврат подсветки на открытую вкладку.
        self.assertIn("setCurrentItem(self._tab)", source)
        # Отказ происходит до присвоения новой вкладки.
        self.assertLess(source.index("locked_click_feedback"), source.index("self._tab = tab"))

    def test_tab_is_not_disabled(self) -> None:
        """Отключённая кнопка не получает нажатий — считать было бы нечего."""
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._build_ui)

        self.assertNotIn("setEnabled(False)", source)

    def test_the_lock_is_currently_off(self) -> None:
        """Замок снят: раздел открыт сразу.

        Пока он стоял, вкладка не переключалась — и со стороны это
        неотличимо от поломки. Правило и его проверки выше остались:
        понадобится закрыть снова, достаточно вернуть False.
        """
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage.__init__)

        self.assertIn("self._links_unlocked = True", source)


if __name__ == "__main__":
    unittest.main()
