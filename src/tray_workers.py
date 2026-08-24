from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from log.log import log


class TrayGithubApiRemovalToggleWorker(QThread):
    completed = pyqtSignal(bool, str)
    failed = pyqtSignal(str)

    def __init__(self, *, toggle_github_api_removal, parent=None):
        super().__init__(parent)
        self._toggle_github_api_removal = toggle_github_api_removal

    def run(self) -> None:
        messages: list[str] = []
        try:
            ok = bool(
                self._toggle_github_api_removal(
                    status_callback=lambda message: messages.append(str(message or "")),
                )
            )
        except Exception as exc:
            message = f"Ошибка при переключении удаления GitHub API: {exc}"
            log(message, "WARNING")
            self.failed.emit(message)
            return

        message = next((item for item in reversed(messages) if item), "")
        if not message:
            message = (
                "Удаление api.github.com из hosts переключено"
                if ok
                else "Ошибка при сохранении настройки удаления GitHub API"
            )
        self.completed.emit(ok, message)


class TrayDiscordRestartToggleWorker(QThread):
    completed = pyqtSignal(bool, str)
    failed = pyqtSignal(str)

    def __init__(self, *, set_discord_restart_enabled, enabled: bool, parent=None):
        super().__init__(parent)
        self._set_discord_restart_enabled = set_discord_restart_enabled
        self._enabled = bool(enabled)

    def run(self) -> None:
        try:
            ok = bool(self._set_discord_restart_enabled(self._enabled))
        except Exception as exc:
            message = f"Ошибка при переключении автоперезапуска Discord: {exc}"
            log(message, "WARNING")
            self.failed.emit(message)
            return

        if ok:
            state_text = "включён" if self._enabled else "отключён"
            message = f"Автоматический перезапуск Discord {state_text}"
        else:
            message = "Ошибка при сохранении настройки автоперезапуска Discord"
        self.completed.emit(ok, message)


__all__ = ["TrayGithubApiRemovalToggleWorker", "TrayDiscordRestartToggleWorker"]
