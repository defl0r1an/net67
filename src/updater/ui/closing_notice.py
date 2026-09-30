"""Надпись «net67 закроется для обновления и откроется сам».

При обновлении программа молча закрывалась: окно пропадало, и человек,
решив, что она упала, открывал её снова. А установщик в это время
убивает net67.exe и заменяет файлы — открытая посреди установки
программа держит свой exe, установка с /SUPPRESSMSGBOXES срывается
молча, и остаётся полуобновлённая папка. После тихого обновления net67
к тому же сам не открывался (в net67.iss запуск стоял с skipifsilent).

Надпись появляется до запуска установщика, а не после: после него
Restart Manager установщика закрывает net67 сам и на показ может не
остаться времени. Окно отдельное, поверх остальных — главное окно в
этот момент может быть свёрнуто или спрятано в трей.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

__all__ = ["UPDATE_CLOSING_NOTICE_LEAD_MS", "UpdateClosingNotice", "closing_notice_text", "show_update_closing_notice"]

#: Сколько надпись висит до запуска установщика, мс.
#:
#: Две с половиной секунды — прочитать две строки. Дольше — человек
#: ждёт обновления, которое уже скачано.
UPDATE_CLOSING_NOTICE_LEAD_MS = 2500

_WIDTH = 440


def closing_notice_text(version: str) -> tuple[str, str]:
    version = str(version or "").strip()
    title = f"Устанавливаю обновление {version}".rstrip()
    body = (
        "net67 сейчас закроется и откроется сам, когда установка закончится, "
        "обычно секунд через 20.\n\n"
        "Пока не открылся — не запускайте его: установщик в это время "
        "заменяет файлы программы."
    )
    return title, body


def _shell_colors():
    from shell.theme import palette
    from ui.theme import get_theme_tokens

    try:
        dark = not get_theme_tokens().is_light
    except Exception:
        dark = True
    return palette(dark)


class UpdateClosingNotice(QWidget):
    """Карточка по центру экрана; мышь сквозь неё не проходит, фокус не забирает."""

    def __init__(self, version: str, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setObjectName("net67UpdateClosingNotice")
        # Фон рисует paintEvent: стиль на всплывающем окне Windows фон не
        # рисовал (см. NotificationPanel в ui/widgets/notification_bell.py).
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(_WIDTH)
        colors = _shell_colors()
        title_text, body_text = closing_notice_text(version)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 20)
        layout.setSpacing(10)
        self.title = QLabel(title_text, self)
        self.title.setStyleSheet(f"color: {colors.text}; font-size: 15px; font-weight: 600; background: transparent;")
        self.body = QLabel(body_text, self)
        self.body.setWordWrap(True)
        self.body.setStyleSheet(f"color: {colors.text_muted}; font-size: 13px; background: transparent;")
        layout.addWidget(self.title)
        layout.addWidget(self.body)

        from ui.accessibility import set_control_accessibility

        set_control_accessibility(self, name=title_text, description=body_text)
        self.adjustSize()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        colors = _shell_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(colors.border_strong))
        painter.setBrush(QColor(colors.surface))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
        painter.end()

    def show_centered(self, anchor: QWidget | None) -> None:
        screen = anchor.screen() if anchor is not None else None
        if screen is None:
            from PyQt6.QtGui import QGuiApplication

            screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else None
        if area is not None:
            self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.show()
        self.raise_()


def show_update_closing_notice(anchor: QWidget | None, version: str) -> UpdateClosingNotice:
    notice = UpdateClosingNotice(version, anchor.window() if anchor is not None else None)
    notice.show_centered(anchor)
    return notice
