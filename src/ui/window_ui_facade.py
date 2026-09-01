# ui/window_ui_facade.py
"""
Главное окно приложения — навигация через qfluentwidgets FluentWindow.

Все страницы добавляются через addSubInterface() вместо ручного SideNavBar + QStackedWidget.
Бизнес-логика (сигналы, обработчики) сохранена без изменений.
"""


def _get_nav_icons():
    from ui.navigation.icons import build_nav_icons

    return build_nav_icons()


def _get_nav_labels():
    from app.page_names import PageName

    return {
        PageName.NETWORK: "Настройка DNS",
        PageName.HOSTS: "Редактор hosts",
        PageName.BLOCKCHECK: "BlockCheck",
        PageName.LOGS: "Логи",
        PageName.ABOUT: "О программе",
        PageName.SERVERS: "Обновления",
        PageName.SUPPORT: "Поддержка",
        PageName.ZAPRET2_MODE_CONTROL: "Управление net67 v2",
        PageName.ZAPRET2_PRESET_SETUP: "Настройка preset-а",
        PageName.ZAPRET2_USER_PRESETS: "Мои пресеты",
        PageName.TELEGRAM_PROXY: "Telegram Proxy",
    }


def _default_nav_icon():
    from ui.navigation.icons import default_nav_icon

    return default_nav_icon()


def _nav_scroll_position():
    from qfluentwidgets import NavigationItemPosition

    return NavigationItemPosition.SCROLL


class MainWindowUI:
    """
    Mixin: creates pages and registers them with FluentWindow navigation.
    """

    def _get_ui_root(self):
        ui_root = getattr(self, "_ui_root", None)
        if ui_root is None:
            raise RuntimeError("WindowUiRoot не подключён. Сначала выполните attach_app_runtime_to_window().")
        return ui_root

    def build_ui(self, width: int, height: int):
        """Build UI: create pages and populate FluentWindow navigation sidebar.

        Note: window geometry (size/position) is restored in __init__ via the
        dedicated window geometry runtime before this is called - do NOT
        resize here, that would overwrite the saved geometry.
        """
        self._get_ui_root().build(
            width=width,
            height=height,
            nav_icons=_get_nav_icons(),
            nav_labels=_get_nav_labels(),
            default_nav_icon=_default_nav_icon(),
            nav_scroll_position=_nav_scroll_position(),
        )

    def finish_ui_bootstrap(self) -> None:
        """Дозавершает тяжёлые связи главного окна после первого показа UI.

        На старте нам важно как можно быстрее показать рабочее окно и первую
        страницу. Общие подписки окна на preset-store и watcher активного
        preset-а подключаются во второй фазе старта, не блокируя первый
        визуальный отклик.
        """
        self._get_ui_root().finish_bootstrap()

    def get_launch_method(self) -> str:
        from settings.mode import DEFAULT_LAUNCH_METHOD
        from ui.workflows.common import get_current_launch_method

        method = get_current_launch_method(default="")
        return method or DEFAULT_LAUNCH_METHOD

    # Window-facing API intentionally kept minimal. Page opening and routing go
    # through window_adapter/page_host/workflow layers, not through this mixin.
