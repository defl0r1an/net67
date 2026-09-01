"""Круглая кнопка подключения VPN.

Тот же приём, что у главной кнопки обхода (`oneclick/ui/button.py`), и
намеренно: две кнопки, которые делают одно и то же — включают и
выключают, — должны и вести себя одинаково. Разный отклик на нажатие в
одном приложении читается как небрежность.

## Что здесь происходит

Круг рисует себя сам: заливка, кольцо по краю, значок в центре. Под
нажатием круг проседает, при подключении по кольцу идёт пульсация,
после подключения она останавливается.

## Почему размер, а не геометрия

Кнопка живёт в раскладке, и правка геометрии ничего не даст: раскладка
вернёт прежние координаты на следующем же пересчёте. Меняется
фиксированный размер, а выравнивание по центру превращает это в
симметричное проседание.

## Почему анимации идут через animation_policy

Кто выключил анимации в системе, не должен их видеть. Там же лежит
разбор случая «анимации выключены»: длительность обнуляется, кадров нет
вовсе, и конечное значение надо ставить руками — иначе кнопка застынет
в промежуточном виде.
"""

from __future__ import annotations

from enum import Enum

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ui.accessibility import enable_keyboard_click, set_control_accessibility, set_state_text


class VpnButtonState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"


#: Диаметр круга и насколько он проседает под нажатием.
BUTTON_SIZE = 96
PRESS_DELTA = 6

#: Толщина кольца и запас под пульсацию.
RING_WIDTH = 3
PULSE_EXTRA = 6

#: Ореол вокруг круга — то, чего кнопке не хватало больше всего.
#:
#: Плоский круг на плоском фоне читается как картинка, а не как то, на
#: что нажимают. Мягкое свечение отделяет кнопку от фона и делает её
#: главным предметом страницы, каковым она и является.
HALO_EXTRA = 18
HALO_STEPS = 7

_TITLES = {
    VpnButtonState.DISCONNECTED: "Подключить",
    VpnButtonState.CONNECTING: "Подключаем...",
    VpnButtonState.CONNECTED: "Отключить",
    VpnButtonState.DISCONNECTING: "Отключаем...",
}

_STATE_TEXTS = {
    VpnButtonState.DISCONNECTED: "VPN отключён",
    VpnButtonState.CONNECTING: "VPN подключается",
    VpnButtonState.CONNECTED: "VPN подключён",
    VpnButtonState.DISCONNECTING: "VPN отключается",
}


class VpnConnectButton(QWidget):
    """Круглая кнопка «Подключить / Отключить»."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._state = VpnButtonState.DISCONNECTED
        self._size = BUTTON_SIZE
        self._pulse_phase = 0.0
        self._press_animation = None
        self._pulse_animation = None

        self._hover = False

        margin = max(PULSE_EXTRA, HALO_EXTRA)
        self.setFixedSize(QSize(BUTTON_SIZE + margin * 2, BUTTON_SIZE + margin * 2))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        enable_keyboard_click(self)
        self._sync_accessibility()

    # ── состояние ─────────────────────────────────────────────────────

    def state(self) -> VpnButtonState:
        return self._state

    def set_state(self, state: VpnButtonState) -> None:
        if state == self._state:
            return
        self._state = state
        self._sync_accessibility()

        if state in (VpnButtonState.CONNECTING, VpnButtonState.DISCONNECTING):
            self._start_pulse()
        else:
            self._stop_pulse()

        self.update()

    def title(self) -> str:
        return _TITLES.get(self._state, "")

    def _sync_accessibility(self) -> None:
        title = self.title()
        state_text = _STATE_TEXTS.get(self._state, "")
        set_control_accessibility(self, name=title, description=state_text)
        set_state_text(self, f"{title}, {state_text}")

    # ── анимации ──────────────────────────────────────────────────────

    def _animate_size(self, target: int) -> None:
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation

        from ui.animation_policy import start_managed_animation

        target = int(target)
        if target == self._size:
            return

        if self._press_animation is not None:
            self._press_animation.stop()

        animation = QVariantAnimation(self)
        animation.setStartValue(int(self._size))
        animation.setEndValue(target)
        animation.setDuration(110)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(self._set_size)
        self._press_animation = animation
        start_managed_animation(animation)

        # Анимации выключены в системе — кадров не будет, ставим сами.
        if animation.duration() <= 0:
            self._set_size(target)

    def _set_size(self, value) -> None:
        self._size = int(value)
        self.update()

    def _start_pulse(self) -> None:
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation

        from ui.animation_policy import start_managed_animation

        self._stop_pulse()

        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(1100)
        animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        animation.setLoopCount(-1)
        animation.valueChanged.connect(self._set_pulse_phase)
        self._pulse_animation = animation
        start_managed_animation(animation)

    def _stop_pulse(self) -> None:
        if self._pulse_animation is not None:
            self._pulse_animation.stop()
            self._pulse_animation = None
        self._pulse_phase = 0.0
        self.update()

    def _set_pulse_phase(self, value) -> None:
        try:
            self._pulse_phase = float(value)
        except (TypeError, ValueError):
            self._pulse_phase = 0.0
        self.update()

    # ── ввод ──────────────────────────────────────────────────────────

    def enterEvent(self, event):  # noqa: N802 (Qt override)
        # Отклик на наведение — это то, чем кнопка отличается от
        # картинки. Без него непонятно, живая она или нарисована.
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 (Qt override)
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self._animate_size(BUTTON_SIZE - PRESS_DELTA)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 (Qt override)
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return

        self._animate_size(BUTTON_SIZE)
        # Нажатие засчитываем, только если отпустили внутри круга: увёл
        # палец в сторону — значит передумал.
        if self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        event.accept()

    # ── рисование ─────────────────────────────────────────────────────

    def _colours(self):
        """Заливка и цвет значка для текущего состояния.

        Чёрно-белая гамма: состояние различается не цветом, а
        светлотой. Подключено — светлый круг с тёмным значком,
        отключено — ровно наоборот. Разница видна издалека и не требует
        различать оттенки.

        Оранжевый круг, стоявший здесь раньше, выжигал глаз на тёмном
        фоне и выглядел как предупреждение об ошибке, хотя означал
        всего лишь «сейчас выключено».
        """
        if self._state == VpnButtonState.CONNECTED:
            fill, glyph = QColor("#f2f2f2"), QColor("#161616")
        elif self._state in (VpnButtonState.CONNECTING, VpnButtonState.DISCONNECTING):
            # Переходное состояние — середина шкалы, между двумя концами.
            fill, glyph = QColor("#8a8a8a"), QColor("#f2f2f2")
        else:
            fill, glyph = QColor("#2a2a2a"), QColor("#e6e6e6")

        if self._hover:
            # Светлеет и светлый круг, и тёмный: иначе тёмный под
            # курсором на тёмном фоне вовсе не отзывался бы.
            fill = fill.lighter(118)

        if not self.isEnabled():
            fill = QColor(fill.red(), fill.green(), fill.blue(), 90)
            glyph = QColor(glyph.red(), glyph.green(), glyph.blue(), 120)

        return fill, glyph

    def _draw_halo(self, painter, centre, radius) -> None:
        """Мягкое свечение вокруг круга.

        Рисуется несколькими кольцами с убывающей прозрачностью: это
        дешевле размытия и не тянет за собой графические эффекты Qt,
        которые на слабых машинах заметно просаживают отрисовку.
        """
        extra = HALO_EXTRA if self._hover else HALO_EXTRA // 2
        if extra <= 0:
            return

        for step in range(HALO_STEPS, 0, -1):
            share = step / HALO_STEPS
            # Свечение белое независимо от заливки: «в цвет» у тёмного
            # круга оно было бы чёрным на чёрном, то есть никаким.
            ring = QColor("#ffffff")
            ring.setAlphaF(0.10 * (1.0 - share) + 0.015)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ring)
            grown = radius + int(extra * share)
            painter.drawEllipse(centre, grown, grown)

    def paintEvent(self, event):  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        fill, glyph = self._colours()
        centre = self.rect().center()
        radius = self._size // 2

        self._draw_halo(painter, centre, radius)

        # Пульсирующее кольцо снаружи — только пока идёт переключение.
        if self._pulse_animation is not None:
            phase = self._pulse_phase
            ring_radius = radius + int(PULSE_EXTRA * phase)
            ring = QColor("#ffffff")
            ring.setAlphaF(max(0.0, 0.40 * (1.0 - phase)))
            painter.setPen(QPen(ring, RING_WIDTH))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centre, ring_radius, ring_radius)

        painter.setBrush(fill)
        # Тонкая обводка по всей окружности. В чёрно-белой гамме круг
        # «выключено» почти совпадает с фоном страницы, и без неё виден
        # только значок, висящий в пустоте.
        edge = QColor("#ffffff")
        edge.setAlphaF(0.28 if self._hover else 0.18)
        painter.setPen(QPen(edge, 1))
        painter.drawEllipse(centre, radius, radius)

        # Светлый ободок по верхнему краю — та самая мелочь, из-за
        # которой круг перестаёт выглядеть наклейкой: он даёт кнопке
        # объём, как будто свет падает сверху.
        highlight = QColor("#ffffff")
        highlight.setAlphaF(0.22 if self._hover else 0.14)
        pen = QPen(highlight, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        arc = self.rect().adjusted(
            centre.x() - radius + 1 - self.rect().left(),
            centre.y() - radius + 1 - self.rect().top(),
            -(self.rect().right() - centre.x() - radius + 1),
            -(self.rect().bottom() - centre.y() - radius + 1),
        )
        painter.drawArc(arc, 30 * 16, 120 * 16)

        # Значок питания: дуга с разрывом сверху и черта из центра.
        pen = QPen(glyph, max(3, radius // 12))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        glyph_radius = int(radius * 0.42)
        rect = self.rect().adjusted(
            centre.x() - glyph_radius - self.rect().left(),
            centre.y() - glyph_radius - self.rect().top(),
            -(self.rect().right() - centre.x() - glyph_radius),
            -(self.rect().bottom() - centre.y() - glyph_radius),
        )
        # Дуга от 60° до 480° — разрыв сверху, как на кнопке питания.
        painter.drawArc(rect, 60 * 16, 420 * 16)
        painter.drawLine(centre.x(), centre.y() - glyph_radius - 4, centre.x(), centre.y() - 2)

        painter.end()


__all__ = [
    "BUTTON_SIZE",
    "HALO_EXTRA",
    "PRESS_DELTA",
    "VpnButtonState",
    "VpnConnectButton",
]
