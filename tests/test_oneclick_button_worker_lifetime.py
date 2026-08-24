"""Опоздавший поток не должен убивать текущий.

Симптом: «Включить, Выключить, Включить» — и кнопка навсегда осталась
неактивной. В crashes.log при этом Qt-фатал «QThread: Destroyed while
thread '' is still running».

Причина одна на оба. Обработчик завершения брал self._worker вслепую:
«завершился какой-то поток — чистим то, что лежит в поле». Между кликами
это разные объекты. Поток выключения завершался уже после того, как
стартовал третий поток, и его finished удалял ЭТОТ, работающий, поток.
Дальше поток умирал молча, finished_with не приходил, и состояние
навсегда оставалось PREPARING — то есть кнопка выключенной.
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _FakeWorker:
    def __init__(self, name: str) -> None:
        self.name = name
        self.deleted = False

    def deleteLater(self) -> None:  # noqa: N802 (Qt API)
        self.deleted = True

    def __repr__(self) -> str:
        return f"<worker {self.name}>"


class WorkerLifetimeTests(unittest.TestCase):
    def _button(self):
        """Кнопка без Qt: проверяется логика владения потоком."""
        from oneclick.state import OneClickState
        from oneclick.ui.button import OneClickButton

        button = OneClickButton.__new__(OneClickButton)
        button._worker = None
        button._state = OneClickState.OFF
        button._applied = []
        button._apply_state = lambda state, detail: (
            button._applied.append((state, detail)),
            setattr(button, "_state", state),
        )
        return button

    def test_late_worker_does_not_clear_the_current_one(self) -> None:
        button = self._button()
        old = _FakeWorker("выключение")
        current = _FakeWorker("включение")
        button._worker = current

        # Опоздавший finished от предыдущего потока.
        button._on_worker_done(old)

        self.assertIs(button._worker, current, "текущий поток потерян")
        self.assertTrue(old.deleted, "старый поток не убран")
        self.assertFalse(current.deleted, "удалён работающий поток")

    def test_current_worker_is_cleared_when_it_finishes(self) -> None:
        button = self._button()
        current = _FakeWorker("включение")
        button._worker = current

        button._on_worker_done(current)

        self.assertIsNone(button._worker)
        self.assertTrue(current.deleted)

    def test_silent_death_unblocks_the_button(self) -> None:
        """Поток умер, не сообщив результата — кнопку надо разблокировать."""
        from oneclick.state import OneClickState

        button = self._button()
        worker = _FakeWorker("включение")
        button._worker = worker
        button._state = OneClickState.PREPARING

        button._on_worker_done(worker)

        self.assertTrue(button._applied, "состояние не изменилось")
        state, detail = button._applied[-1]
        self.assertIs(state, OneClickState.ERROR)
        self.assertIn("ещё раз", detail)

    def test_normal_finish_is_not_overwritten_by_an_error(self) -> None:
        """После обычного завершения состояние трогать нельзя."""
        from oneclick.state import OneClickState

        button = self._button()
        worker = _FakeWorker("включение")
        button._worker = worker
        button._state = OneClickState.RUNNING

        button._on_worker_done(worker)

        self.assertEqual(button._applied, [], "состояние переписали поверх результата")

    def test_handler_takes_the_worker_as_an_argument(self) -> None:
        """Фиксируем причину поломки: раньше аргумента не было."""
        from oneclick.ui.button import OneClickButton

        signature = inspect.signature(OneClickButton._on_worker_done)

        self.assertIn("worker", signature.parameters)

        source = inspect.getsource(OneClickButton._on_clicked)
        self.assertIn("lambda finished=worker", source)


if __name__ == "__main__":
    unittest.main()
