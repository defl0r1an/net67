from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from main.runtime_state import log_startup_metric as emit_startup_metric
from main.window_actions import WindowActionsMixin
from main.window_lifecycle import WindowLifecycleMixin
from main.window_startup import WindowStartupMixin
from main.window_state_sync import WindowStateSyncMixin
from shell.app_window import AppShellWindow
from ui.window_ui_facade import MainWindowUI

class LupiDPIApp(
    WindowStartupMixin,
    WindowLifecycleMixin,
    WindowActionsMixin,
    WindowStateSyncMixin,
    AppShellWindow,
    MainWindowUI,
):
    """Главное окно приложения — своя оболочка и навигация.

    Из списка предков убран ThemeSubscriptionManager. Он держал метку
    [PREMIUM] у названия окна, и после отказа от подписки метка только
    и делала, что пряталась при каждом обновлении состояния.

    Прежде здесь стояло окно qfluentwidgets. Оно заменено на своё:
    AppShellWindow отвечает теми же navigationInterface, stackedWidget,
    addSubInterface и switchTo, поэтому сборщик навигации, сорок
    страниц, поиск и трей продолжают работать без правок.
    """

    deferred_init_requested = pyqtSignal()
    continue_startup_requested = pyqtSignal()
    finalize_ui_bootstrap_requested = pyqtSignal()
    startup_interactive_ready = pyqtSignal(str)
    startup_post_init_ready = pyqtSignal(str)

    def log_startup_metric(self, marker: str, details: str = "") -> None:
        emit_startup_metric(marker, details)

__all__ = ["LupiDPIApp"]
