"""Поток «одной кнопки»: включение и выключение вне потока окна.

Отдельный модуль, а не класс в ui/button.py: модуль с наследником QThread
проверка архитектуры считает фоновым и запрещает ему элементы окна
(app/architecture_checks.py, check_background_code_does_not_create_widgets),
а кнопка — это элемент окна.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from log.log import log
from oneclick.state import OneClickState


class _OneClickWorker(QThread):
    """Выполняет включение или выключение вне UI-потока."""

    progress = pyqtSignal(object, str)
    finished_with = pyqtSignal(object, str)

    def __init__(self, *, enable: bool, runtime_feature, parent=None):
        super().__init__(parent)
        self._enable = bool(enable)
        self._runtime_feature = runtime_feature

    def run(self) -> None:
        try:
            from oneclick.deps import build_oneclick_deps
            from oneclick.runner import OneClickRunner
            from wizard.apply import build_request_from_settings

            deps = build_oneclick_deps(
                runtime_feature=self._runtime_feature,
                report=lambda state, message: self.progress.emit(state, message),
            )
            runner = OneClickRunner(deps)

            # Запрос читается и на выключение — ради одного поля.
            #
            # «Одна кнопка» снимает прокси Telegram только тогда, когда
            # сама же его и поднимает. Иначе выключение обхода убивало
            # прокси, включённый человеком на его собственной странице,
            # и вернуть его было нечем.
            request = build_request_from_settings()

            if self._enable:
                outcome = runner.enable(request)
            else:
                outcome = runner.disable(
                    owns_telegram_proxy=request.needs_telegram_proxy
                )

            self.finished_with.emit(outcome.state, outcome.message)
        except Exception as exc:
            log(f"Оркестратор «одной кнопки»: {exc}", "❌ ERROR")
            self.finished_with.emit(OneClickState.ERROR, f"{type(exc).__name__}: {exc}")
