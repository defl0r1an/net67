"""«Одна кнопка» показывает обход, включённый или выключенный не ею.

Кнопка смотрела на обход один раз, при сборке страницы. Автозапуск
поднимал обход секундой позже, и кнопка стояла на «Обход выключен», а
метка в заголовке — на «Работает»: два противоречащих ответа на одном
экране. Выключение из метки кнопка тоже не замечала.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _Worker:
    def __init__(self, running: bool) -> None:
        self._running = running

    def isRunning(self) -> bool:  # noqa: N802 (Qt API)
        return self._running


class FollowRuntimeTests(unittest.TestCase):
    def _button(self, state_name: str = "OFF", worker=None):
        from oneclick.state import OneClickState
        from oneclick.ui.button import OneClickButton

        button = OneClickButton.__new__(OneClickButton)
        button._worker = worker
        button._state = getattr(OneClickState, state_name)
        button._applied = []
        button._apply_state = lambda state, detail: (
            button._applied.append(state),
            setattr(button, "_state", state),
        )
        return button

    def test_autostarted_bypass_turns_the_button_on(self) -> None:
        from oneclick.state import OneClickState

        button = self._button("OFF")
        button.follow_runtime_phase("running")
        self.assertIs(button._state, OneClickState.RUNNING)

    def test_bypass_stopped_elsewhere_turns_the_button_off(self) -> None:
        from oneclick.state import OneClickState

        button = self._button("RUNNING")
        button.follow_runtime_phase("stopped")
        self.assertIs(button._state, OneClickState.OFF)

    def test_own_steps_are_not_interrupted(self) -> None:
        """Пока кнопка сама включает (hosts, DNS, проверка), итог покажет она."""
        for state in ("PREPARING", "CHECKING"):
            with self.subTest(state=state):
                button = self._button(state)
                button.follow_runtime_phase("running")
                self.assertEqual(button._applied, [])
        button = self._button("OFF", worker=_Worker(True))
        button.follow_runtime_phase("running")
        self.assertEqual(button._applied, [])

    def test_transitional_phases_change_nothing(self) -> None:
        for phase in ("starting", "stopping", "autostart_pending", ""):
            with self.subTest(phase=phase):
                button = self._button("OFF")
                button.follow_runtime_phase(phase)
                self.assertEqual(button._applied, [])


if __name__ == "__main__":
    unittest.main()
