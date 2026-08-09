# winws_runtime/runners/runner_factory.py
"""
Factory module for strategy runners.
Выбирает между Winws1StrategyRunner и Winws2StrategyRunner по выбранному exe-файлу.
"""

import os
from typing import Optional
from log.log import log

from settings.mode import EXE_NAME_WINWS2

# Import both runner classes
from .zapret1_runner import Winws1StrategyRunner
from .zapret2_runner import Winws2StrategyRunner
from .runner_base import StrategyRunnerBase

_strategy_runner_instance: Optional[StrategyRunnerBase] = None


def get_strategy_runner(winws_exe_path: str) -> StrategyRunnerBase:
    """
    Получает или создает экземпляр runner'а.
    Автоматически выбирает winws1 или winws2 на основе выбранного exe-файла.
    """
    global _strategy_runner_instance

    exe_name = os.path.basename(str(winws_exe_path or "")).lower()
    if exe_name == EXE_NAME_WINWS2:
        runner_class = Winws2StrategyRunner
    else:
        runner_class = Winws1StrategyRunner

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
