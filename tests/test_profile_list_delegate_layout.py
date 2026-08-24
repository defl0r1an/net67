import unittest

from PyQt6.QtCore import QRect

from profile.ui.profile_list_delegate import _profile_row_layout


class ProfileListDelegateLayoutTests(unittest.TestCase):
    def test_status_dot_stays_next_to_short_strategy_text(self) -> None:
        layout = _profile_row_layout(
            QRect(8, 2, 404, 40),
            strategy_text_width=48,
            feedback_text_width=0,
            badge_width=0,
        )

        self.assertTrue(layout.strategy_rect.isValid())
        self.assertEqual(layout.strategy_rect.left() - layout.dot_rect.right(), 4)
        self.assertEqual(layout.strategy_rect.width(), 48)


if __name__ == "__main__":
    unittest.main()
