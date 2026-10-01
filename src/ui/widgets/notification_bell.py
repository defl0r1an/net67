"""Колокольчик в заголовке окна и панель с историей уведомлений.

Что сюда попадает и почему — в ui/notification_inbox.py. Здесь только вид.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.notification_inbox import InboxEntry, NotificationInbox

__all__ = [
    "NotificationBell",
    "NotificationPanel",
    "anchor_point",
    "badge_pop_scale",
    "bell_bump_scale",
    "ring_angle",
    "ring_flash",
]

#: Размер кнопки. Под высоту строки заголовка, как у кнопок окна.
BELL_SIZE = QSize(34, 28)

#: Ширина панели. Шире — строки ошибок растягиваются в одну длинную
#: ленту, которую глазу неудобно читать; уже — заголовки рвутся на два слова.
PANEL_WIDTH = 380

#: Качание колокольчика при новом уведомлении.
#:
#: Колокольчик качается от верхней точки, как настоящий: размах гаснет
#: по экспоненте. Перелёт здесь уместен — у колокольчика есть физика, и
#: именно качание читается как «звонок».
#:
#: Первая версия качалась на 16 и 7 градусов за три четверти секунды.
#: Значок — пятнадцать пикселей: 7 градусов сдвигали его низ на один
#: пиксель, 16 — на два с небольшим, и всё гасло раньше, чем глаз
#: успевал дойти до заголовка. Владелец: «двигается далеко не на все
#: уведомления и еле заметно». На «Готово» и «Сохранено» качание было
#: тем самым однопиксельным — его не видел никто.
#:
#: Теперь слабого качания нет: любое уведомление качает заметно, важное
#: — сильнее. Качаний три с половиной за полторы секунды, как у
#: настоящего колокольчика, и значок на первом взмахе подрастает.
RING_MS = 1500
RING_STRONG_DEG = 34.0
RING_SOFT_DEG = 26.0
_RING_DAMPING = 2.6
_RING_SWINGS = 3.5
#: Счётчик «выпрыгивает» в первые 45 % качания.
BADGE_POP_SCALE = 0.35
#: Насколько значок подрастает на первом взмахе и какую долю качания.
BELL_BUMP_SCALE = 0.22
_BELL_BUMP_SPAN = 0.3
#: Подсветка под колокольчиком в начале звонка (доля непрозрачности).
#: Она же — весь отклик, когда «лёгкие анимации» выключены: просьба
#: убрать движение — не просьба убрать сигнал.
RING_FLASH_ALPHA = 0.26
#: Колокольчик, скрытый вместе с окном, отзвонит при показе — с такой
#: задержкой, чтобы окно успело появиться.
PENDING_RING_DELAY_MS = 350


def ring_angle(t: float, amplitude: float) -> float:
    """Угол качания в момент t (0..1): затухающая синусоида."""
    t = max(0.0, min(1.0, float(t)))
    return amplitude * math.exp(-_RING_DAMPING * t) * math.sin(2.0 * math.pi * _RING_SWINGS * t) * (1.0 - t)


def bell_bump_scale(t: float) -> float:
    """Размер значка в момент t: подрастает на первом взмахе и возвращается."""
    t = max(0.0, min(1.0, float(t) / _BELL_BUMP_SPAN))
    return 1.0 + BELL_BUMP_SCALE * math.sin(math.pi * t)


def ring_flash(t: float) -> float:
    """Непрозрачность подсветки в момент t: вспыхивает сразу и гаснет."""
    t = max(0.0, min(1.0, float(t)))
    return RING_FLASH_ALPHA * (1.0 - t) ** 1.5


def badge_pop_scale(t: float) -> float:
    t = max(0.0, min(1.0, float(t) / 0.45))
    return 1.0 + BADGE_POP_SCALE * math.sin(math.pi * t) * (1.0 - t * 0.3)


_LEVEL_ICONS = {
    "error": "fa5s.exclamation-circle",
    "warning": "fa5s.exclamation-triangle",
    "success": "fa5s.check-circle",
    "info": "fa5s.info-circle",
}


def _shell_colors():
    from shell.theme import palette
    from ui.theme import get_theme_tokens

    try:
        dark = not get_theme_tokens().is_light
    except Exception:
        dark = True
    return palette(dark)


class NotificationBell(QPushButton):
    """Кнопка с колокольчиком и счётчиком непрочитанного."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("net67NotificationBell")
        self.setFixedSize(BELL_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._unread = 0
        self._level = ""
        self._hover = False
        self._ring_t = 1.0
        self._ring_amplitude = 0.0
        self._ring_pop = False
        # Есть новое, которого человек ещё не открывал, — см. ring().
        self._fresh = False
        # Звонок, пришедший, пока колокольчика не было на экране.
        self._pending_ring: bool | None = None
        # QVariantAnimation, а не QPropertyAnimation: общий выключатель
        # анимаций подменяет только второй.
        self._ring = QVariantAnimation(self)
        self._ring.setStartValue(0.0)
        self._ring.setEndValue(1.0)
        self._ring.setDuration(RING_MS)
        self._ring.valueChanged.connect(self._on_ring_value)
        self._ring.finished.connect(self._on_ring_finished)
        self._sync_text()

    def set_state(self, unread: int, level: str) -> None:
        self._unread = max(0, int(unread))
        self._level = str(level or "")
        self._sync_text()
        self.update()

    @property
    def unread(self) -> int:
        return self._unread

    def ring(self, *, strong: bool) -> None:
        """Качнуться: пришло новое уведомление.

        Раньше колокольчик молча менял цифру — новое замечали, только
        случайно взглянув на заголовок. Повторный звонок во время
        качания не начинает его заново с нуля: размах берётся больший из
        двух, а время — с начала, так что движение не дёргается.

        Три вещи, чтобы звонок не пропал:

        - на колокольчике остаётся точка, пока список не открыли.
          Счётчик зажигают только ошибки и предупреждения, а «Готово»
          лишь качало — моргнул, и следа нет;
        - звонок, пришедший при спрятанном окне (трей), не теряется:
          колокольчик отзвонит, когда окно покажут;
        - при выключенных «лёгких анимациях» качания нет, но подсветка
          остаётся.
        """
        from ui.animation_policy import are_animations_enabled, are_live_animations_enabled

        self._fresh = True
        if not self.isVisible():
            self._pending_ring = bool(strong or self._pending_ring)
            return
        swing = are_live_animations_enabled()
        if not swing and not are_animations_enabled():
            # Движение выключено в самой Windows: остаётся только точка.
            self.update()
            return
        amplitude = (RING_STRONG_DEG if strong else RING_SOFT_DEG) if swing else 0.0
        if self.is_ringing():
            amplitude = max(amplitude, self._ring_amplitude)
        self._ring_amplitude = amplitude
        self._ring_pop = bool(strong and self._unread) or not self._unread
        self._ring.stop()
        self._ring.start()

    def mark_seen(self) -> None:
        """Список открыли — точка «есть новое» гаснет."""
        if self._fresh:
            self._fresh = False
            self.update()

    def has_fresh(self) -> bool:
        return self._fresh

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        pending, self._pending_ring = self._pending_ring, None
        if pending is not None:
            QTimer.singleShot(PENDING_RING_DELAY_MS, lambda strong=pending: self._ring_if_shown(strong))

    def _ring_if_shown(self, strong: bool) -> None:
        if self.isVisible() and self._fresh:
            self.ring(strong=strong)

    def is_ringing(self) -> bool:
        return self._ring.state() == QVariantAnimation.State.Running

    def ring_angle(self) -> float:
        return ring_angle(self._ring_t, self._ring_amplitude) if self.is_ringing() else 0.0

    def ring_scale(self) -> float:
        if not self.is_ringing() or self._ring_amplitude <= 0.0:
            return 1.0
        return bell_bump_scale(self._ring_t)

    def _on_ring_value(self, value) -> None:
        self._ring_t = float(value)
        self.update()

    def _on_ring_finished(self) -> None:
        self._ring_t = 1.0
        self._ring_pop = False
        self.update()

    def _sync_text(self) -> None:
        from qfluentwidgets import ToolTipPosition

        from ui.accessibility import set_control_accessibility
        from ui.fluent_widgets import set_tooltip

        if self._unread:
            name = f"Уведомления: непрочитанных {self._unread}"
        else:
            name = "Уведомления"
        # Колокольчик в заголовке окна: подсказка сверху у развёрнутого окна
        # упёрлась бы в край экрана и легла бы на сам колокольчик.
        set_tooltip(self, name, position=ToolTipPosition.BOTTOM)
        set_control_accessibility(self, name=name, description="Показать историю уведомлений и ошибок")

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        from ui.theme import get_cached_qta_pixmap

        colors = _shell_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        if self._hover or self.isDown():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors.surface_hover))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        if self.is_ringing():
            # Вспышка под значком: её видно краем глаза, когда взгляд на
            # странице, а не на заголовке.
            flash = QColor(colors.text)
            flash.setAlphaF(ring_flash(self._ring_t))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(flash)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        if self.hasFocus():
            # Кнопка рисуется целиком здесь, стиль Qt её не касается — без
            # этой рамки человек с клавиатурой не видит, где фокус.
            painter.setPen(QColor(colors.text_muted))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), 8, 8)

        # Значок рисуется при каждой отрисовке по текущей палитре: смена
        # темы тогда не оставляет его чёрным на чёрном.
        icon_color = colors.text if (self._hover or self._unread or self._fresh) else colors.text_muted
        pixmap = get_cached_qta_pixmap("fa5s.bell", color=icon_color, size=15)
        if not pixmap.isNull():
            ratio = pixmap.devicePixelRatio() or 1.0
            width = pixmap.width() / ratio
            height = pixmap.height() / ratio
            left = int((rect.width() - width) / 2)
            top = int((rect.height() - height) / 2)
            angle = self.ring_angle()
            scale = self.ring_scale()
            if abs(angle) > 0.05 or scale > 1.001:
                # Качается от верхней точки — там, где колокольчик висит;
                # оттуда же и растёт, так что верх стоит на месте.
                pivot = QPointF(left + width / 2, top + 1.0)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.translate(pivot)
                painter.rotate(angle)
                painter.scale(scale, scale)
                painter.translate(-pivot)
                painter.drawPixmap(QPoint(left, top), pixmap)
                painter.restore()
            else:
                painter.drawPixmap(QPoint(left, top), pixmap)

        if self._fresh and not self._unread:
            # Новое без счётчика («Готово», «Сохранено»): точка без цифры.
            radius = 3.0
            if self._ring_pop and self.is_ringing():
                radius *= badge_pop_scale(self._ring_t)
            painter.setPen(QColor(colors.window))
            painter.setBrush(QColor(colors.text))
            painter.drawEllipse(QPointF(rect.width() - 9.0, 8.0), radius, radius)

        if self._unread:
            text = str(self._unread) if self._unread < 10 else "9+"
            font = QFont(self.font())
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)
            badge_width = max(14.0, painter.fontMetrics().horizontalAdvance(text) + 7.0)
            badge = QRectF(rect.width() - badge_width - 2, 2, badge_width, 14)
            if self._ring_pop and self.is_ringing():
                scale = badge_pop_scale(self._ring_t)
                center = badge.center()
                badge = QRectF(0, 0, badge.width() * scale, badge.height() * scale)
                badge.moveCenter(center)
            # Ошибка — заливка акцентом (самое контрастное в монохромной
            # теме), предупреждение — приглушённым: вес важности держит
            # светлота, а не цвет, как во всём интерфейсе.
            fill = colors.accent if self._level == "error" else colors.text_muted
            painter.setPen(QColor(colors.window))
            painter.setBrush(QColor(fill))
            painter.drawRoundedRect(badge, 7, 7)
            painter.setPen(QColor(colors.on_accent))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()


class _EntryCloser:
    """То, что действие уведомления закрывает после себя вместо плашки."""

    def __init__(self, on_close: Callable[[], None]) -> None:
        self._on_close = on_close

    def close(self) -> None:
        self._on_close()


#: Насколько можно сдвинуть мышь между нажатием и отпусканием, чтобы это
#: всё ещё был щелчок. Дальше — человек выделял текст, а не открывал.
CLICK_SLOP_PX = 4


class _EntryRow(QFrame):
    """Запись в панели — целиком кнопка: щелчок открывает её раздел.

    Раньше открыть что-то из списка можно было только кнопкой действия,
    а она есть у немногих записей. Остальные только читались:
    «Пресет сохранён» — а где он, куда смотреть — ищи сам.

    Текст записи по-прежнему выделяется мышью (скопировать ошибку):
    протяжка — выделение, щелчок на месте — переход.
    """

    def __init__(self, on_activate: Callable[[], None]) -> None:
        super().__init__()
        self._on_activate = on_activate
        self._pressed_at: QPoint | None = None
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Мышью открывается — значит, и с клавиатуры: Tab до записи,
        # Enter или пробел.
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            event.accept()
            self._on_activate()
            return
        super().keyPressEvent(event)

    def watch(self, label: QLabel) -> None:
        """Выделяемый текст сам забирает мышь — щелчок по нему ловим фильтром."""
        label.installEventFilter(self)
        label.setCursor(Qt.CursorShape.PointingHandCursor)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt override)
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._pressed_at = event.globalPosition().toPoint()
        elif kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            if isinstance(obj, QLabel) and obj.hasSelectedText():
                self._pressed_at = None
                return False
            self._release_at(event.globalPosition().toPoint())
        return False

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed_at = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self._release_at(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _release_at(self, point: QPoint) -> None:
        pressed, self._pressed_at = self._pressed_at, None
        if pressed is None or (point - pressed).manhattanLength() > CLICK_SLOP_PX:
            return
        if not self.rect().contains(self.mapFromGlobal(point)):
            return
        self._on_activate()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(event)
        if not (self._hovered or self.hasFocus()):
            return
        # Подсветка под курсором — единственное, что говорит «это
        # нажимается» до щелчка. Текст — дочерние виджеты, он поверх.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_shell_colors().surface_hover))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0, 3, 0, -3), 8, 8)
        painter.end()


class NotificationPanel(QFrame):
    """Всплывающий список под колокольчиком."""

    #: Панель закрывается. Флаг — закрыло ли её нажатие на колокольчик.
    #:
    #: Нажатие мимо всплывающего окна Qt сначала закрывает его, а потом
    #: отдаёт тому, что под курсором. Нажатие на колокольчик при открытой
    #: панели закрывало её и тут же открывало заново: переключатель не
    #: выключался. По флагу окно пропускает этот щелчок.
    closing = pyqtSignal(bool)

    def __init__(
        self,
        inbox: NotificationInbox,
        *,
        build_action: Callable[[dict, object], Callable[[], None] | None],
        on_changed: Callable[[], None],
        open_entry: Callable[[InboxEntry], None] | None = None,
        parent=None,
    ) -> None:
        # Системная тень Windows прямоугольная и под скруглённой панелью
        # торчала углами — рамка панели и так отделяет её от окна.
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setObjectName("net67NotificationPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        # Панель — отдельное всплывающее окно. Без прозрачного фона Windows
        # закрашивает его прямоугольником, и скругление видно не было:
        # углы выходили острыми. Фон и рамку рисует paintEvent.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._inbox = inbox
        self._anchor: QWidget | None = None
        self._build_action = build_action
        self._on_changed = on_changed
        self._open_entry = open_entry
        self.setFixedWidth(PANEL_WIDTH)

        colors = _shell_colors()
        self.setStyleSheet(
            f"""
            QLabel {{ color: {colors.text}; background: transparent; }}
            QLabel#net67InboxMuted {{ color: {colors.text_muted}; }}
            QLabel#net67InboxTitle {{ font-weight: 600; }}
            QFrame#net67InboxEntry {{ border-top: 1px solid {colors.border}; background: transparent; }}
            QPushButton#net67InboxButton {{
                background: transparent; border: 1px solid {colors.border_strong};
                border-radius: 10px; color: {colors.text}; padding: 3px 10px;
            }}
            QPushButton#net67InboxButton:hover {{ background: {colors.surface_hover}; }}
            QPushButton#net67InboxClear {{
                background: transparent; border: none; color: {colors.text_muted}; padding: 2px 6px;
            }}
            QPushButton#net67InboxClear:hover {{ color: {colors.text}; }}
            QScrollArea {{ background: transparent; border: none; }}
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Уведомления", self)
        title.setObjectName("net67InboxTitle")
        header.addWidget(title)
        header.addStretch(1)
        self._clear_button = QPushButton("Очистить", self)
        self._clear_button.setObjectName("net67InboxClear")
        self._clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_button.clicked.connect(self._clear)
        header.addWidget(self._clear_button)
        outer.addLayout(header)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Область прокрутки заливает себя цветом палитры: на панели это
        # был серый прямоугольник под записями, чужой её фону.
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.viewport().setStyleSheet("background: transparent;")
        self._list_host = QWidget()
        self._list_host.setAutoFillBackground(False)
        self._list_host.setStyleSheet("background: transparent;")
        self._list = QVBoxLayout(self._list_host)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(0)
        self._scroll.setWidget(self._list_host)
        outer.addWidget(self._scroll, 1)

        self._rebuild()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        """Фон и рамка панели — кистью, а не стилем.

        Стилем (``background`` у ``QFrame#net67NotificationPanel``) фон на
        настоящем всплывающем окне Windows не рисовался вовсе: замер поверх
        красного окна показал красный под заголовком и по краям, серым был
        закрашен только список. Снимок ``panel.grab()`` при этом выглядел
        правильно — он рисует виджет сам, мимо окна, — поэтому ошибка
        прошла проверку при разработке. Так же рисует себя колокольчик.
        """
        colors = _shell_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(colors.border_strong))
        painter.setBrush(QColor(colors.surface))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
        painter.end()

    # ── содержимое ────────────────────────────────────────────

    def _rebuild(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        entries = self._inbox.entries()
        self._clear_button.setVisible(bool(entries))
        if not entries:
            empty = QLabel("Пока тихо. Сюда попадут предупреждения и ошибки, которые программа заметит сама.")
            empty.setObjectName("net67InboxMuted")
            empty.setWordWrap(True)
            empty.setContentsMargins(0, 8, 0, 8)
            self._list.addWidget(empty)
        for entry in entries:
            self._list.addWidget(self._entry_widget(entry))
        self._list.addStretch(1)
        self._fit_height(len(entries))

    def _fit_height(self, count: int) -> None:
        # Панель растёт с числом записей, но не выше полэкрана окна.
        wanted = 70 + max(1, count) * 86
        self.setFixedHeight(max(120, min(460, wanted)))

    def _entry_widget(self, entry: InboxEntry) -> QWidget:
        from ui.theme import get_cached_qta_pixmap

        colors = _shell_colors()
        box = _EntryRow(lambda e=entry: self._activate(e))
        box.setObjectName("net67InboxEntry")
        layout = QHBoxLayout(box)
        # Поля по бокам — под подсветку наведения: без них текст
        # упирался бы в её край.
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(3)
        top = QHBoxLayout()
        title = QLabel(entry.title, box)
        title.setObjectName("net67InboxTitle")
        title.setWordWrap(True)
        top.addWidget(title, 1)

        # Значок — в ячейке высотой ровно в строку заголовка, по центру.
        # Выровненные по верху, круг и треугольник разной высоты стояли
        # вразнобой и выше текста.
        icon = QLabel(box)
        color = colors.text if entry.level == "error" else colors.text_muted
        icon.setPixmap(get_cached_qta_pixmap(_LEVEL_ICONS.get(entry.level, "fa5s.info-circle"), color=color, size=15))
        title.ensurePolished()
        line_height = title.fontMetrics().height()
        icon.setFixedSize(18, max(18, line_height))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        stamp = time.strftime("%H:%M", time.localtime(entry.last_seen))
        meta = f"×{entry.count}  {stamp}" if entry.count > 1 else stamp
        meta_label = QLabel(meta, box)
        meta_label.setObjectName("net67InboxMuted")
        top.addWidget(meta_label, 0, Qt.AlignmentFlag.AlignTop)
        text.addLayout(top)

        if entry.content:
            body = QLabel(entry.content, box)
            body.setObjectName("net67InboxMuted")
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.watch(body)
            text.addWidget(body)
        if entry.source == "global_logger":
            hint = QLabel("Подробности — в журнале: Диагностика → Логи", box)
            hint.setObjectName("net67InboxMuted")
            text.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        closer = _EntryCloser(lambda e=entry: self._dismiss(e))
        for action in entry.buttons:
            label = str(action.get("text") or "").strip()
            callback = self._build_action(action, closer) if label else None
            if callback is None:
                continue
            button = QPushButton(label, box)
            button.setObjectName("net67InboxButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, cb=callback: cb())
            buttons.addWidget(button)
        if buttons.count():
            buttons.addStretch(1)
            text.addLayout(buttons)

        layout.addLayout(text, 1)
        return box

    # ── действия ─────────────────────────────────────────────

    def _activate(self, entry: InboxEntry) -> None:
        """Щелчок по записи: панель уходит, окно открывает раздел записи."""
        open_entry = self._open_entry
        self.close()
        if open_entry is not None:
            open_entry(entry)

    def _dismiss(self, entry: InboxEntry) -> None:
        self._inbox.remove(entry)
        self._on_changed()
        self._rebuild()

    def _clear(self) -> None:
        self._inbox.clear()
        self._on_changed()
        self._rebuild()

    def show_under(self, anchor: QWidget, motion=None) -> None:
        self._anchor = anchor
        point = anchor.mapToGlobal(QPoint(anchor.width() - self.width(), anchor.height() + 6))
        screen = anchor.screen()
        if screen is not None:
            area = screen.availableGeometry()
            point.setX(max(area.left() + 8, min(point.x(), area.right() - self.width() - 8)))
        self.move(point)
        if motion is None:
            self.show()
            return
        motion.open(self, anchor_point(anchor))

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        anchor = self._anchor
        by_anchor = False
        try:
            if anchor is not None:
                by_anchor = anchor.rect().contains(anchor.mapFromGlobal(QCursor.pos()))
        except RuntimeError:
            # Окно закрывается целиком, колокольчик уже удалён.
            by_anchor = False
        self.closing.emit(by_anchor)
        super().closeEvent(event)


def anchor_point(anchor: QWidget) -> QPoint:
    """Точка на экране, из которой панель растёт и куда уходит: низ колокольчика."""
    return anchor.mapToGlobal(QPoint(anchor.width() // 2, anchor.height()))
