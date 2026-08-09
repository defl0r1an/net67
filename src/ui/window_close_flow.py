from __future__ import annotations

from log.log import log
from settings.schema import (
    TRAY_CLOSE_MODE_MINIMIZE_AND_CLOSE,
    TRAY_CLOSE_MODE_MINIMIZE_ONLY,
    TRAY_CLOSE_MODE_NORMAL,
)



class WindowCloseFlow:
    """Единый сценарий поведения при закрытии главного окна.

    Здесь решается только пользовательский сценарий закрытия:
    показать диалог, свернуть в трей или выбрать полный выход.
    Само финальное освобождение ресурсов остаётся в main.closeEvent.
    """

    def __init__(
        self,
        *,
        parent,
        close_state,
        get_launch_state_snapshot,
        close_to_tray,
        exit_stop_dpi,
        exit_keep_dpi,
        tray_close_mode=None,
    ) -> None:
        self._parent = parent
        self._close_state = close_state
        self._get_launch_state_snapshot = get_launch_state_snapshot
        self._close_to_tray = close_to_tray
        self._exit_stop_dpi = exit_stop_dpi
        self._exit_keep_dpi = exit_keep_dpi
        self._tray_close_mode = tray_close_mode

    def tray_close_mode(self) -> str:
        provider = self._tray_close_mode
        if not callable(provider):
            return TRAY_CLOSE_MODE_NORMAL
        try:
            mode = str(provider() or TRAY_CLOSE_MODE_NORMAL)
        except Exception as exc:
            log(f"Не удалось прочитать режим поведения окна и трея из памяти: {exc}", "DEBUG")
            return TRAY_CLOSE_MODE_NORMAL
        if mode in {
            TRAY_CLOSE_MODE_MINIMIZE_AND_CLOSE,
            TRAY_CLOSE_MODE_MINIMIZE_ONLY,
            TRAY_CLOSE_MODE_NORMAL,
        }:
            return mode
        return TRAY_CLOSE_MODE_NORMAL

    def minimize_to_tray_enabled(self) -> bool:
        return self.tray_close_mode() in {
            TRAY_CLOSE_MODE_MINIMIZE_AND_CLOSE,
            TRAY_CLOSE_MODE_MINIMIZE_ONLY,
        }

    def close_to_tray_enabled(self) -> bool:
        return self.tray_close_mode() == TRAY_CLOSE_MODE_MINIMIZE_AND_CLOSE

    def should_continue_final_close(self, event) -> bool:
        """Возвращает True только для окончательного закрытия приложения."""
        if bool(getattr(self._close_state, "windows_session_ending", False)):
            return True

        if self._close_state.closing_completely:
            return True

        try:
            event.ignore()
        except Exception:
            pass

        try:
            if self.close_to_tray_enabled():
                minimized = bool(self._close_to_tray())
                if not minimized:
                    log("Сценарий 'закрыть в трей' не выполнен: tray manager не готов", "WARNING")
                return False

            from ui.close_dialog import ask_close_action

            launch_running = False
            try:
                snapshot = self._get_launch_state_snapshot()
                launch_running = bool(
                    getattr(snapshot, "running", getattr(snapshot, "launch_running", False))
                )
            except Exception as snapshot_error:
                log(f"Не удалось прочитать состояние запуска перед диалогом закрытия: {snapshot_error}", "DEBUG")

            result = ask_close_action(
                parent=self._parent,
                launch_running=launch_running,
            )
            if result is None:
                return False

            if result == "tray":
                minimized = bool(self._close_to_tray())
                if not minimized:
                    log("Сценарий 'свернуть в трей' не выполнен: tray manager не готов", "WARNING")
                return False

            if bool(result):
                self._exit_stop_dpi()
            else:
                self._exit_keep_dpi()
            return False
        except Exception as e:
            log(f"Ошибка пользовательского сценария закрытия окна: {e}", "DEBUG")
            return False
