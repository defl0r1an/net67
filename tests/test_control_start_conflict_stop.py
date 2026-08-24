import unittest
from unittest.mock import Mock, patch

from presets.ui.control.control_page_shared import ControlPageActionMixin


class ControlStartConflictStopTests(unittest.TestCase):
    def test_manual_start_waits_until_blockcheck_conflict_stops(self) -> None:
        from presets.ui.control import control_page_shared

        class Page(ControlPageActionMixin):
            def __init__(self) -> None:
                self._runtime_actions = Mock()
                self._runtime_actions.is_available.return_value = True
                self._runtime_actions.start = Mock()
                self.status_calls: list[str] = []
                self.loading_calls: list[tuple[bool, str]] = []

            def window(self):
                return object()

            def _set_status(self, message: str) -> None:
                self.status_calls.append(str(message or ""))

            def set_loading(self, loading: bool, text: str = "") -> None:
                self.loading_calls.append((bool(loading), str(text or "")))

        page = Page()
        scheduled: list[object] = []

        with (
            patch.object(
                control_page_shared.QTimer,
                "singleShot",
                side_effect=lambda _delay_ms, callback: scheduled.append(callback),
            ),
            patch(
                "ui.window_adapter.send_page_command",
                side_effect=[True, False],
            ) as send_page_command,
        ):
            page._start_dpi()
            page._runtime_actions.start.assert_not_called()
            self.assertEqual(len(scheduled), 1)

            scheduled.pop(0)()

        page._runtime_actions.start.assert_called_once_with()
        self.assertEqual(send_page_command.call_count, 2)
        self.assertIn(
            "Останавливаем подбор стратегии перед запуском net67...",
            page.status_calls,
        )
        self.assertIn(
            (True, "Останавливаем подбор стратегии перед запуском net67..."),
            page.loading_calls,
        )


if __name__ == "__main__":
    unittest.main()
