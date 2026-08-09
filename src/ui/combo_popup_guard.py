from __future__ import annotations

from PyQt6.QtCore import QObject, QEvent
from PyQt6.QtWidgets import QApplication, QComboBox


class GlobalComboPopupCloser(QObject):
    """Closes open ComboBox popups when app loses focus."""

    def __init__(self, app: QApplication):
        super().__init__(app)
        self._app = app
        self._cleanup_in_progress = False
        app.installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        if self._cleanup_in_progress:
            return False
        try:
            if event is not None and event.type() == QEvent.Type.ApplicationDeactivate:
                self.close_all_popups()
        except Exception:
            pass
        return False

    def close_all_popups(self) -> None:
        try:
            widgets = list(self._app.allWidgets())
        except Exception:
            widgets = []

        for widget in widgets:
            if widget is None:
                continue
            try:
                if hasattr(widget, "_closeComboMenu"):
                    widget._closeComboMenu()
                    continue
            except Exception:
                pass

            try:
                if isinstance(widget, QComboBox):
                    widget.hidePopup()
            except Exception:
                pass

    def cleanup(self) -> None:
        if self._cleanup_in_progress:
            return
        self._cleanup_in_progress = True
        app = self._app
        self._app = None
        if app is None:
            return
        try:
            app.removeEventFilter(self)
        except Exception:
            pass
        try:
            if getattr(app, "_zapret_global_combo_popup_closer", None) is self:
                setattr(app, "_zapret_global_combo_popup_closer", None)
        except Exception:
            pass


def install_global_combo_popup_closer(app: QApplication | None = None) -> GlobalComboPopupCloser | None:
    try:
        qapp = app or QApplication.instance()
    except Exception:
        qapp = None
    if qapp is None:
        return None

    existing = getattr(qapp, "_zapret_global_combo_popup_closer", None)
    if isinstance(existing, GlobalComboPopupCloser):
        return existing

    closer = GlobalComboPopupCloser(qapp)
    setattr(qapp, "_zapret_global_combo_popup_closer", closer)
    return closer
