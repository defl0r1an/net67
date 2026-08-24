# winws_runtime/runners/runner_factory.py
"""
Factory module for strategy runners.

Движок остался один — winws2. Раньше здесь выбирали между ним и
winws1 по имени exe-файла; winws1 вырезан, и выбирать больше не из
чего. Модуль оставлен: он держит единственный экземпляр и следит за
сменой пути к exe, а это нужно по-прежнему.
"""

from typing import Optional
from log.log import log

from .zapret2_runner import Winws2StrategyRunner
from .runner_base import StrategyRunnerBase

_strategy_runner_instance: Optional[StrategyRunnerBase] = None


def get_strategy_runner(winws_exe_path: str) -> StrategyRunnerBase:
    """Получает или создаёт экземпляр runner'а."""
    global _strategy_runner_instance

    runner_class = Winws2StrategyRunner

    # Пересоздаём если exe или класс изменился
    if _strategy_runner_instance is not None:
        exe_changed = _strategy_runner_instance.winws_exe != winws_exe_path
        class_changed = not isinstance(_strategy_runner_instance, runner_class)

        if exe_changed or class_changed:
            log(f"Смена runner: {type(_strategy_runner_instance).__name__} → {runner_class.__name__}", "INFO")
            _strategy_runner_instance.stop_background_watchers()
            _strategy_runner_instance = None

    if _strategy_runner_instance is None:
        _strategy_runner_instance = runner_class(winws_exe_path)
        log(f"Создан {runner_class.__name__} для {winws_exe_path}", "DEBUG")

    return _strategy_runner_instance


def reset_strategy_runner():
    """Синхронный сброс runner'а"""
    global _strategy_runner_instance
    if _strategy_runner_instance:
        _strategy_runner_instance.stop()
        _strategy_runner_instance = None


def invalidate_strategy_runner():
    """Асинхронная инвалидация runner'а"""
    global _strategy_runner_instance
    if _strategy_runner_instance:
        _strategy_runner_instance.stop_background_watchers()
        _strategy_runner_instance = None


def get_current_runner() -> Optional[StrategyRunnerBase]:
    """Возвращает текущий экземпляр runner'а без создания нового"""
    return _strategy_runner_instance
