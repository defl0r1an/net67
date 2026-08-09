from __future__ import annotations

import unittest

from qfluentwidgets import FluentIcon

from presets.ui.common.user_presets_actions_workflow import show_reset_all_result


class _Button:
    def __init__(self) -> None:
        self.text = ""
        self.icon = None
        self.text_calls: list[str] = []
        self.icon_calls: list[object] = []

    def setText(self, value: str) -> None:
        self.text_calls.append(str(value))
        self.text = value

    def setIcon(self, value) -> None:
        self.icon_calls.append(value)
        self.icon = value


class UserPresetsResetResultTests(unittest.TestCase):
    def _show_result(self, *, success_count: int, total_count: int, failed_count: int = 0) -> _Button:
        button = _Button()

        show_reset_all_result(
            cleanup_in_progress=False,
            success_count=success_count,
            total_count=total_count,
            failed_count=failed_count,
            reset_all_btn=button,
            single_shot_fn=lambda _delay, callback: None,
            restore_label_fn=lambda: None,
        )
        return button

    def test_reset_result_shows_changed_count_without_total(self) -> None:
        button = self._show_result(success_count=3, total_count=83)

        self.assertEqual(button.text, "Сброшено: 3")
        self.assertEqual(button.icon, FluentIcon.ACCEPT)

    def test_reset_result_shows_nothing_to_change_as_success(self) -> None:
        button = self._show_result(success_count=0, total_count=83)

        self.assertEqual(button.text, "Нечего менять")
        self.assertEqual(button.icon, FluentIcon.ACCEPT)

    def test_reset_result_shows_failed_count_as_warning(self) -> None:
        button = self._show_result(success_count=3, total_count=83, failed_count=2)

        self.assertEqual(button.text, "Ошибки: 2")
        self.assertEqual(button.icon, FluentIcon.INFO)

    def test_reset_result_skips_duplicate_button_render(self) -> None:
        button = _Button()

        show_reset_all_result(
            cleanup_in_progress=False,
            success_count=3,
            total_count=83,
            failed_count=0,
            reset_all_btn=button,
            single_shot_fn=lambda _delay, callback: None,
            restore_label_fn=lambda: None,
        )
        button.text_calls.clear()
        button.icon_calls.clear()
        show_reset_all_result(
            cleanup_in_progress=False,
            success_count=3,
            total_count=83,
            failed_count=0,
            reset_all_btn=button,
            single_shot_fn=lambda _delay, callback: None,
            restore_label_fn=lambda: None,
        )

        self.assertEqual(button.text_calls, [])
        self.assertEqual(button.icon_calls, [])


if __name__ == "__main__":
    unittest.main()
