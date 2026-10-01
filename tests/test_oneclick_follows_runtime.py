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
        button._runtime_phase = ""
        button._get_runtime_phase = None
        button._get_runtime_feature = None
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

    def test_button_catches_up_when_its_own_steps_end(self) -> None:
        """Выключили кругом, обход тут же подняли заново — кнопка стояла на «выключен».

        Фаза «работает» пришла, пока кнопка была занята своими шагами, и
        пропала: после них кнопку никто не догонял. Метка в заголовке
        писала «Работает», круг — «Обход выключен».
        """
        from oneclick.state import OneClickState

        worker = _Worker(True)
        button = self._button("PREPARING", worker=worker)
        button._get_runtime_phase = None
        button._get_runtime_feature = None
        button.follow_runtime_phase("running")
        self.assertEqual(button._applied, [])

        # Шаги кончились итогом «выключено».
        button._state = OneClickState.OFF
        worker._running = False
        button.deleteLater = lambda: None
        worker.deleteLater = lambda: None
        button._on_worker_done(worker)
        self.assertIs(button._state, OneClickState.RUNNING)

    def test_catch_up_asks_the_engine_when_the_store_is_silent(self) -> None:
        """Обход запустили плашкой до первого показа главной — круг не знал.

        Хранилище при показе ещё не привязано (фаза пустая), и круг стоял
        на «Обход выключен». Теперь он спрашивает сам движок.
        """
        from oneclick.state import OneClickState

        class _Feature:
            def is_any_running(self, *, silent=False):
                return True

        button = self._button("OFF")
        button._runtime_phase = ""
        button._get_runtime_phase = lambda: ""        # хранилище молчит
        button._get_runtime_feature = lambda: _Feature()
        button._catch_up_with_runtime()
        self.assertIs(button._state, OneClickState.RUNNING)

    def test_catch_up_reads_the_live_phase(self) -> None:
        """Живое состояние главнее последней доставленной фазы."""
        from oneclick.state import OneClickState

        button = self._button("RUNNING")
        button._runtime_phase = "running"
        button._get_runtime_phase = lambda: "stopped"
        button._catch_up_with_runtime()
        self.assertIs(button._state, OneClickState.OFF)

    def test_error_is_kept_when_bypass_is_really_stopped(self) -> None:
        from oneclick.state import OneClickState

        button = self._button("ERROR")
        button._get_runtime_phase = lambda: "stopped"
        button._catch_up_with_runtime()
        self.assertIs(button._state, OneClickState.ERROR)

    def test_transitional_phases_change_nothing(self) -> None:
        for phase in ("starting", "stopping", "autostart_pending", ""):
            with self.subTest(phase=phase):
                button = self._button("OFF")
                button.follow_runtime_phase(phase)
                self.assertEqual(button._applied, [])


if __name__ == "__main__":
    unittest.main()
