# ui/fluent_app_window.py
"""
Main app window using qfluentwidgets FluentWindow (WinUI 3 style).
Replaces the old QWidget + FramelessWindowMixin + CustomTitleBar stack.
"""
import time as _time

from branding import APP_NAME
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon,
    setTheme, Theme, setThemeColor, NavigationAvatarWidget,
)
from qfluentwidgets import NavigationWidget
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtCore import QEvent, Qt, QTimer

from config.build_info import APP_VERSION

from log.log import log
from main.runtime_state import log_startup_metric as emit_startup_metric



class AppFluentWindow(FluentWindow):
    """Main app window using qfluentwidgets FluentWindow (WinUI 3 style)."""

    def __init__(self, parent=None):
        # Tint color painted as window background (below all content, above Mica).
        # QColor(0,0,0,0) = pure Mica (no tint), alpha 1-200 = visible tint.
        self._mica_tint_color = QColor(0, 0, 0, 0)

        t_super = _time.perf_counter()
        super().__init__(parent)
        emit_startup_metric(
            "StartupFluentWindowSuper",
            f"{(_time.perf_counter() - t_super) * 1000:.0f}ms",
        )
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self._sync_titlebar_icon_from_application()

        # Theme mode (DARK/LIGHT) is set in main.py via _sync_theme_mode_to_qfluent()
        # before the window is created, so no hardcoded setTheme(DARK) here.

    def setTitleBar(self, title_bar) -> None:  # noqa: N802 (qfluentwidgets API)
        """Безопасно заменяет верхнюю панель окна.

        qframelesswindow регистрирует каждую TitleBar как фильтр событий окна,
        но при замене только откладывает её удаление. На Python 3.14 / PyQt6
        6.11 старая панель иногда успевает получить WindowStateChange уже во
        время очистки Python-объекта, когда maxBtn в нём больше нет.
        """
        previous_title_bar = getattr(self, "titleBar", None)
        if previous_title_bar is not None and previous_title_bar is not title_bar:
            self.removeEventFilter(previous_title_bar)

        super().setTitleBar(title_bar)

    def _sync_titlebar_icon_from_application(self) -> None:
        """Показывает уже готовый общий значок в окончательной верхней панели."""
        app = QApplication.instance()
        title_bar = getattr(self, "titleBar", None)
        set_icon = getattr(title_bar, "setIcon", None)
        if app is None or not callable(set_icon):
            return

        icon = app.windowIcon()
        if not icon.isNull():
            set_icon(icon)

    # ------------------------------------------------------------------
    # Background tint (Mica + semi-transparent Qt background layer)
    # ------------------------------------------------------------------

    def _normalBackgroundColor(self) -> QColor:  # noqa: N802
        """Override: inject semi-transparent tint when Mica is active.

        FluentWidget._normalBackgroundColor() returns QColor(0,0,0,0) when
        Mica is enabled, making the Qt surface fully transparent. By returning
        our _mica_tint_color instead, the background is painted as a
        semi-transparent fill BELOW all content widgets, so the tint blends
        with the DWM Mica backdrop without covering text or controls.
        """
        try:
            if self.isMicaEffectEnabled():
                return self._mica_tint_color
        except Exception:
            pass
        return super()._normalBackgroundColor()

    def set_tint_overlay(self, r: int, g: int, b: int, alpha: int) -> None:
        """Update the Mica tint color (painted below content, above Mica backdrop).

        alpha=0  → pure Mica (no tint)
        alpha=200 → strong tint but content still readable (drawn on top)
        """
        self._mica_tint_color = QColor(r, g, b, max(0, min(255, alpha)))
        try:
            self._updateBackgroundColor()
        except Exception:
            pass

    def clear_tint_overlay(self) -> None:
        """Reset tint to fully transparent (pure Mica or default background)."""
        self._mica_tint_color = QColor(0, 0, 0, 0)
        try:
            self._updateBackgroundColor()
        except Exception:
            pass

    def prepare_transparent_mica_background(self) -> None:
        """Готовит прозрачный фон перед отключением Mica на Windows 11."""
        self._darkBackgroundColor = QColor(0, 0, 0, 0)
        self._lightBackgroundColor = QColor(0, 0, 0, 0)

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    def addSeparatorToNav(self):
        """Add a separator line in the navigation."""
        self.navigationInterface.addSeparator()

    # ------------------------------------------------------------------
    # Background image support (for РКН Тян preset)
    # ------------------------------------------------------------------

    def set_background_image(self, path: str | None) -> None:
        """Set a full-window background image (dimmed). Pass None to hide."""
        if not hasattr(self, '_bg_label'):
            self._bg_label = QLabel(self)
            self._bg_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._bg_rawpath = None
        if path is None:
            self._bg_label.hide()
            self._bg_rawpath = None
            return
        self._bg_rawpath = path
        self._rescale_bg()
        self._bg_label.lower()
        self._bg_label.show()

    def _rescale_bg(self) -> None:
        """Rescale and dim the background image to current window size."""
        if not (hasattr(self, '_bg_label') and getattr(self, '_bg_rawpath', None)):
            return
        pm = QPixmap(self._bg_rawpath)
        if pm.isNull():
            return
        pm = pm.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        dimmed = QPixmap(pm.size())
        dimmed.fill(QColor(0, 0, 0, 0))
        p = QPainter(dimmed)
        p.drawPixmap(0, 0, pm)
        p.fillRect(dimmed.rect(), QColor(0, 0, 0, 155))
        p.end()
        self._bg_label.setPixmap(dimmed)
        self._bg_label.setGeometry(self.rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale_bg()

    # ------------------------------------------------------------------
    # Возврат из развёрнутого окна
    # ------------------------------------------------------------------

    def changeEvent(self, event):  # noqa: N802 (сигнатура Qt)
        """Ловит выход из развёрнутого состояния.

        Окно после нажатия на «свернуть в окно» оказывалось сдвинутым
        влево и обведённым белой каймой — до первого перетаскивания мышью. Рамы у
        окна своей нет, её рисует qframelesswindow, и размеры полей она
        считает по-разному для развёрнутого окна и обычного. Пересчёт
        запускает WM_NCCALCSIZE, а Windows шлёт его не всегда: при
        обычном ShowWindow(SW_RESTORE) рама остаётся посчитанной по
        прежнему состоянию. Перетаскивание сообщение вызывает — отсюда и
        «чинится, когда потащишь».
        """
        super().changeEvent(event)

        try:
            if event.type() != QEvent.Type.WindowStateChange:
                return
            was_zoomed = bool(event.oldState() & Qt.WindowState.WindowMaximized)
            now_zoomed = bool(self.isMaximized() or self.isFullScreen())
        except Exception:
            return

        if not was_zoomed or now_zoomed:
            return

        # Следующим тактом: Qt в этот момент ещё внутри обработки смены
        # состояния, и просить у него окно пересчитать раму рано.
        QTimer.singleShot(0, self._recalculate_native_frame)

    def _recalculate_native_frame(self) -> None:
        """Просит Windows пересчитать поля окна, ничего не двигая.

        SetWindowPos с SWP_FRAMECHANGED и без перемещения, размера и
        смены порядка окон — единственный смысл вызова в том, чтобы
        Windows прислала WM_NCCALCSIZE. Обработчик рамы получает
        сообщение уже с правильным состоянием окна и считает поля
        заново.

        argtypes задаём явно: без них ctypes режет HWND до 32 бит, и на
        64-разрядной Windows вызов уходит в никуда, молча возвращая
        ложь.
        """
        import sys

        if sys.platform != "win32":
            return

        try:
            import ctypes

            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020

            user32 = ctypes.windll.user32
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SetWindowPos.restype = ctypes.c_bool
            user32.SetWindowPos(
                int(self.winId()),
                None,
                0,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
        except Exception as exc:
            log(f"[WINDOW] рама не пересчитана: {exc}", "DEBUG")
            return

        try:
            self.update()
        except Exception:
            pass
