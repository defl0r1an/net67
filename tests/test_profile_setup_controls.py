from __future__ import annotations

import unittest

from profile.ui.profile_setup_controls import set_combo_by_data, sync_range_value_enabled


class Combo:
    def __init__(self, mode: str, *, items: tuple[str, ...] | None = None, current_index: int = 0) -> None:
        self.mode = mode
        self.items = tuple(items or (mode,))
        self.index = int(current_index)
        self.current_index_calls: list[int] = []

    def count(self) -> int:
        return len(self.items)

    def currentIndex(self) -> int:  # noqa: N802
        return self.index

    def itemData(self, index: int):
        return self.items[index]

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        value = int(index)
        self.current_index_calls.append(value)
        self.index = value


class ValueEdit:
    def __init__(self, *, enabled: bool = True, text: str = "8", placeholder: str = "") -> None:
        self.enabled = bool(enabled)
        self._text = str(text)
        self.placeholder = str(placeholder)
        self.enabled_calls: list[bool] = []
        self.clear_calls = 0
        self.text_calls: list[str] = []
        self.placeholder_calls: list[str] = []

    def isEnabled(self) -> bool:  # noqa: N802
        return self.enabled

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        value = bool(enabled)
        self.enabled_calls.append(value)
        self.enabled = value

    def text(self) -> str:
        return self._text

    def clear(self) -> None:
        self.clear_calls += 1
        self._text = ""

    def setText(self, text: str) -> None:  # noqa: N802
        value = str(text)
        self.text_calls.append(value)
        self._text = value

    def placeholderText(self) -> str:  # noqa: N802
        return self.placeholder

    def setPlaceholderText(self, text: str) -> None:  # noqa: N802
        value = str(text)
        self.placeholder_calls.append(value)
        self.placeholder = value


class ProfileSetupControlsTests(unittest.TestCase):
    def test_range_value_placeholder_does_not_show_fake_default_8(self) -> None:
        for mode in ("a", "x", "n", "d"):
            edit = ValueEdit()
            sync_range_value_enabled(Combo(mode), edit)
            self.assertNotEqual(edit.placeholder, "8")

    def test_set_combo_by_data_skips_already_selected_item(self) -> None:
        combo = Combo("ipset", items=("hostlist", "ipset"), current_index=1)

        set_combo_by_data(combo, "ipset")

        self.assertEqual(combo.current_index_calls, [])

    def test_range_value_sync_skips_duplicate_disabled_empty_state(self) -> None:
        edit = ValueEdit(enabled=False, text="", placeholder="")

        sync_range_value_enabled(Combo("a"), edit)

        self.assertEqual(edit.enabled_calls, [])
        self.assertEqual(edit.clear_calls, 0)
        self.assertEqual(edit.placeholder_calls, [])


if __name__ == "__main__":
    unittest.main()
