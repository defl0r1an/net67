"""Оркестратор «одной кнопки».

Простой интерфейс сводит всё к одной кнопке «Включить». За ней стоит
последовательность шагов, описанная в oneclick/plans.py, и исполнитель
в oneclick/runner.py.
"""

from oneclick.state import OneClickState, StepKey

__all__ = ["OneClickState", "StepKey"]
