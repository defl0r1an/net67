from __future__ import annotations

import unittest
from types import SimpleNamespace

from profile.ui.profile_setup_page import CompactDisplayComboBox


class ProfileCompactDisplayComboTests(unittest.TestCase):
    def test_sync_compact_text_skips_duplicate_text(self) -> None:
        text_calls: list[str] = []
        combo = SimpleNamespace(
            _compact_text_by_data={"n": "n"},
            currentIndex=lambda: 0,
            itemData=lambda _index: "n",
            text=lambda: "n",
            setText=text_calls.append,
        )

        CompactDisplayComboBox._sync_compact_text(combo)

        self.assertEqual(text_calls, [])


if __name__ == "__main__":
    unittest.main()
