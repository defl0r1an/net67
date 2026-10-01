"""Мастер первого запуска: смена экранов и проценты в углу.

Два разных требования из одного сообщения. Первое: «при нажатии далее
следующее окно выбора откуда-то бы выезжало». Второе: «на первом запуске
где-то в уголке блеклым шрифтом проценты окончания проверок и первой
настройки».

Проценты считает чистая функция в wizard/plans.py, и её проверяем без
Qt: там вся арифметика, из-за которой надпись может соврать. Окна мастера
больше нет — вопросы на карточках обучающего тура, у которого свой счётчик
шагов и полоска прогресса, — поэтому проверки по исходнику диалога ушли.
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
        from wizard.plans import WIZARD_STEPS

        # Последний шаг — по длине списка: шагов стало четыре, когда
        # добавили вопрос про сайты без VPN, и число здесь устарело.
        self.assertEqual(self._percent(-5), self._percent(0))
        self.assertEqual(self._percent(99), self._percent(len(WIZARD_STEPS) - 1))


if __name__ == "__main__":
    unittest.main()
