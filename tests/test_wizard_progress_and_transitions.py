"""Мастер первого запуска: смена экранов и проценты в углу.

Два разных требования из одного сообщения. Первое: «при нажатии далее
следующее окно выбора откуда-то бы выезжало». Второе: «на первом запуске
где-то в уголке блеклым шрифтом проценты окончания проверок и первой
настройки».

Проценты считает чистая функция в wizard/plans.py, и её проверяем без
Qt: там вся арифметика, из-за которой надпись может соврать.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DIALOG = PROJECT_SRC / "wizard" / "ui" / "dialog.py"


class ProgressMathTests(unittest.TestCase):
    def _percent(self, current: int, **kwargs) -> int:
        from wizard.plans import wizard_progress_percent

        return wizard_progress_percent(current, **kwargs)

    def test_first_screen_is_not_zero_forever(self) -> None:
        from wizard.plans import WIZARD_STEPS

        self.assertEqual(self._percent(0), 0)
        self.assertGreater(self._percent(1), 0)
        self.assertGreater(self._percent(len(WIZARD_STEPS) - 1), self._percent(1))

    def test_progress_never_goes_backwards(self) -> None:
        from wizard.plans import WIZARD_STEPS

        values = [self._percent(step) for step in range(len(WIZARD_STEPS))]

        self.assertEqual(values, sorted(values))

    def test_hundred_is_never_shown_before_the_end(self) -> None:
        """«100%» там, где ещё нажимать «Готово», — это обман."""
        from wizard.plans import WIZARD_STEPS

        last = len(WIZARD_STEPS) - 1

        self.assertLess(self._percent(last, checked=9, to_check=9), 100)

    def test_checked_domains_move_the_number(self) -> None:
        """Иначе надпись замирает на самом долгом месте мастера."""
        start = self._percent(1, checked=0, to_check=8)
        middle = self._percent(1, checked=4, to_check=8)
        end = self._percent(1, checked=8, to_check=8)

        self.assertLess(start, middle)
        self.assertLess(middle, end)

    def test_unknown_domain_count_does_not_break_it(self) -> None:
        """Сеть могла не ответить, и списка доменов просто нет."""
        self.assertEqual(self._percent(1, checked=0, to_check=0), self._percent(1))

    def test_out_of_range_step_is_clamped(self) -> None:
        self.assertEqual(self._percent(-5), self._percent(0))
        self.assertEqual(self._percent(99), self._percent(2))


class WiringTests(unittest.TestCase):
    """Проверки по исходнику: диалог модальный, поднимать его в тестах дорого."""

    def setUp(self) -> None:
        self.source = DIALOG.read_text(encoding="utf-8")

    def test_progress_label_exists_and_is_dim(self) -> None:
        self.assertIn("self.progress_hint", self.source)
        self.assertIn("fg_muted", self.source)

    def test_progress_updates_on_every_step(self) -> None:
        block = self.source[self.source.index("def _apply_step") :]
        block = block[: block.index("def _refresh_progress_hint")]

        self.assertIn("_refresh_progress_hint", block)

    def test_progress_counts_checked_domains(self) -> None:
        self.assertIn("_on_domain_started", self.source)
        self.assertIn("worker.progress.connect(self._on_domain_started)", self.source)

    def test_both_directions_are_animated(self) -> None:
        """Вперёд и назад должны отличаться, иначе переход ничего не сообщает."""
        for call in ("self._animate_step(forward=True)", "self._animate_step(forward=False)"):
            with self.subTest(call=call):
                self.assertIn(call, self.source)

    def test_transition_respects_the_animation_switch(self) -> None:
        """Человек мог выключить анимации в оформлении — это его право."""
        self.assertIn("start_managed_animation", self.source)

    def test_transition_moves_margins_not_the_widget(self) -> None:
        """Позицию виджета в раскладке сбросит первый же её пересчёт.

        Это не догадка: страницы мастера лежат в QVBoxLayout, и пересчёт
        случается от чего угодно — вплоть до смены текста кнопки «Далее»,
        которая как раз меняется на каждом шаге.
        """
        block = self.source[self.source.index("def _animate_step") :]
        block = block[: block.index("\n    def ", 10)]

        self.assertIn("setContentsMargins", block)
        self.assertNotIn(".move(", block)

    def test_opacity_effect_is_removed_afterwards(self) -> None:
        """Эффект держит отдельный слой отрисовки и дорого стоит потом."""
        self.assertIn("setGraphicsEffect(None)", self.source)


if __name__ == "__main__":
    unittest.main()
