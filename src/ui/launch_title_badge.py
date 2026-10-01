"""Метка состояния обхода в верхней панели окна.

Метка сама является выключателем: клик запускает или останавливает net67
через единый пульт ui.launch_control.LaunchControl. Состояние она не
вычисляет — фаза приходит из общего UI-store.

Пока обход работает, метка — маленькая копия главного круга: кружок
«включено» и время работы, как на самом круге. Слово «Работает» рядом с
ним ничего не добавляло, а время было видно только на главной странице.
Остановленный обход метка называет словом — «Остановлен».
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy
from qfluentwidgets import TransparentPushButton, setCustomStyleSheet

from app.ui_texts import tr as tr_catalog
from ui.accessibility import set_control_accessibility
from ui.animation_policy import are_live_animations_enabled
from ui.fluent_widgets import set_tooltip
from ui.launch_control import BUSY_LAUNCH_PHASES, mode_label_for_launch_method, normalize_launch_phase, phase_color
from ui.theme_semantic import get_semantic_palette
from ui.title_badge_paint import badge_qss, badge_shape, current_theme_name, paint_badge_body


LAUNCH_TITLE_BADGE_OBJECT_NAME = "launchTitleBadge"
BADGE_DOT_RADIUS = 3.5
BADGE_DOT_LEFT = 12
BADGE_TEXT_LEFT = 23
# Пока идёт запуск или остановка, точка мягко «дышит».
BUSY_BREATH_MS = 1200
# «Работает»: от точки расходится кольцо, подложка в такт светлеет.
RUNNING_PULSE_MS = 1800
# Кольцо дорастает до 10 px: целиком помещается в значок высотой 22 px.
RUNNING_RING_GROWTH = 5.5
STOPPED_DOT_COLOR = "#9aa0a6"

#: Размеры метки в заголовке net67: по высоте кнопок заголовка (колокольчик
#: 28 px), текст после точки с воздухом.
NET67_BADGE_HEIGHT = 26
NET67_DOT_LEFT = 13
NET67_TEXT_LEFT = 25
NET67_TEXT_RIGHT = 12
#: Кружок «включено» — главный круг в миниатюре: заливка акцентом и знак
#: питания. 16 px в метке высотой 26: по пять пикселей воздуха сверху и снизу.
NET67_ON_RADIUS = 8.0
NET67_ON_TEXT_LEFT = 28
#: От кружка расходится кольцо; дальше трёх пикселей оно вылезло бы из метки.
NET67_ON_RING_GROWTH = 3.0
UPTIME_TICK_MS = 1000


@dataclass(frozen=True, slots=True)
class LaunchBadgeView:
    phase: str
    text: str
    tooltip: str


def build_launch_badge_view(*, phase: str, launch_method: str, language: str | None) -> LaunchBadgeView:
    normalized = normalize_launch_phase(phase)
    if normalized == "autostart_pending":
        key = "starting"
    else:
        key = normalized
    defaults = {
        "running": ("Работает", "{mode} работает · нажмите, чтобы остановить"),
        "starting": ("Запуск…", "{mode} запускается · нажмите, чтобы остановить"),
        "stopping": ("Остановка…", "{mode} останавливается…"),
        "stopped": ("Остановлен", "{mode} остановлен · нажмите, чтобы запустить"),
        "failed": ("Ошибка", "Ошибка запуска {mode} · нажмите, чтобы попробовать снова"),
    }
    text_default, tooltip_default = defaults[key]
    mode = mode_label_for_launch_method(launch_method)
    text = tr_catalog(f"launch.badge.{key}", language=language, default=text_default)
    tooltip = tr_catalog(f"launch.badge.tooltip.{key}", language=language, default=tooltip_default)
    return LaunchBadgeView(phase=normalized, text=text, tooltip=tooltip.format(mode=mode))


def _badge_colors(*, phase: str, theme_name: str) -> tuple[str, str, str]:
    """Цвета значка: текст, фон, фон при наведении."""
    palette = get_semantic_palette(theme_name)
    if phase == "running":
        return palette.success_text, "rgba(108, 203, 95, 0.16)", "rgba(108, 203, 95, 0.28)"
    if phase in BUSY_LAUNCH_PHASES:
        return palette.warning_text, "rgba(245, 166, 35, 0.16)", "rgba(245, 166, 35, 0.28)"
    if phase == "failed":
        return palette.error_text, palette.error_soft_bg, "rgba(255, 82, 82, 0.26)"
    return palette.neutral_badge_fg, palette.neutral_badge_bg, palette.neutral_badge_bg_hover


def _badge_qss(*, phase: str, theme_name: str) -> str:
    fg, _bg, _hover = _badge_colors(phase=phase, theme_name=theme_name)
    return badge_qss(f"#{LAUNCH_TITLE_BADGE_OBJECT_NAME}", fg=fg, left_padding=BADGE_TEXT_LEFT, disabled=True)


class LaunchTitleBadge(TransparentPushButton):
    """Кнопка-метка состояния net67 в titleBar.

    Это кнопка, а не QLabel: кнопка сама забирает нажатие мыши, поэтому клик
    по метке не начинает перетаскивание окна.
    """

    def __init__(self, parent=None, *, language_provider: Callable[[], str | None]):
        super().__init__(parent)
        self._language_provider = language_provider
        self._phase = ""
        self._launch_method = ""
        self._override_text = ""
        self._styled_phase: str | None = None
        # Насколько метка на экране: 0 — её место занимает главный круг
        # страницы (shell/launch_badge_handoff.py), 1 — стоит как есть.
        self._presence = 1.0
        # Какую долю своей ширины метка занимает в заголовке, см. set_handoff.
        self._slot = 1.0
        self._state_text = ""
        self._tooltip_text = ""

        self.setObjectName(LAUNCH_TITLE_BADGE_OBJECT_NAME)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedHeight(NET67_BADGE_HEIGHT)
        # Спрятанная метка места не держит. Сначала держала — чтобы вкладки
        # рядом не прыгали, — и на главной странице в заголовке зияла
        # дыра шириной в метку: владелец спросил, чего там не хватает.
        # Теперь вкладки не прыгают по другой причине: место раздвигается
        # и сходится плавно, вместе с полётом круга (set_handoff).
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(UPTIME_TICK_MS)
        self._uptime_timer.timeout.connect(self._refresh_uptime)

        self._breath_t = 0.0
        # QVariantAnimation, а не QPropertyAnimation: при выключенных
        # анимациях общий fallback подменяет QPropertyAnimation.start.
        self._breath = QVariantAnimation(self)
        self._breath.setStartValue(0.0)
        self._breath.setEndValue(1.0)
        self._breath.setDuration(BUSY_BREATH_MS)
        self._breath.setLoopCount(-1)
        self._breath.valueChanged.connect(self._on_breath_value)
        self._pulse_t = 0.0
        self._pulse = QVariantAnimation(self)
        self._pulse.setStartValue(0.0)
        self._pulse.setEndValue(1.0)
        self._pulse.setDuration(RUNNING_PULSE_MS)
        self._pulse.setLoopCount(-1)
        self._pulse.valueChanged.connect(self._on_pulse_value)
        self.hide()

    def phase(self) -> str:
        return self._phase

    def set_state(self, *, phase: str, launch_method: str) -> bool:
        """Показывает новую фазу. True — изменились текст или видимость (ширина в titleBar)."""
        phase = normalize_launch_phase(phase)
        launch_method = str(launch_method or "")
        if phase == self._phase and launch_method == self._launch_method and not self.isHidden():
            return False
        self._phase = phase
        self._launch_method = launch_method
        return self._render()

    def set_override(self, text: str | None) -> bool:
        """Временная надпись поверх фазы — пока «одна кнопка» ещё работает.

        Обход уже поднят, и фаза — «running», но кнопка простого вида
        ещё пишет «Запускаем…» и «Проверка»: метка в заголовке писала
        «Работает», и два места на экране говорили разное.
        """
        text = str(text or "")
        if text == self._override_text:
            return False
        self._override_text = text
        return self._render() if self._phase else False

    def set_handoff(self, *, slot: float, presence: float) -> None:
        """Место метки в заголовке и её видимость — порознь.

        ``slot`` — доля ширины, которую метка занимает в раскладке
        заголовка: 0 — её нет вовсе, и вкладки стоят вплотную к
        колокольчику, 1 — занимает своё место целиком. ``presence`` —
        насколько она нарисована.

        Порознь они ради полёта: пока снимок круга летит в заголовок,
        место под метку уже раздвигается (вкладки едут плавно, а не
        прыгают в конце), но самой метки ещё нет — иначе на экране их
        было бы две.
        """
        self._slot = max(0.0, min(1.0, float(slot)))
        self._presence = max(0.0, min(1.0, float(presence)))
        # Полупрозрачную метку не нажать: щелчок по тени выключателя
        # выключил бы обход, которого человек не видел.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, self._presence < 0.999)
        self._apply_width()
        if self._slot <= 0.001:
            if not self.isHidden():
                self.hide()
            return
        if self.isHidden() and self._phase:
            self.show()
        self.update()

    def set_presence(self, value: float) -> None:
        """0 — метки нет (её место у главного круга), 1 — видна целиком.

        Промежуточное — только проявление без движения, когда «лёгкие
        анимации» выключены: полёт снимка тогда не показывают.
        """
        value = max(0.0, min(1.0, float(value)))
        self.set_handoff(slot=0.0 if value <= 0.001 else 1.0, presence=value)

    def presence(self) -> float:
        return self._presence

    def slot(self) -> float:
        return self._slot

    def grab_full(self) -> QPixmap:
        """Снимок метки целиком, как она встанет, — для полёта из круга.

        Рисуется отдельно, а не снимается с виджета: пока метка в пути,
        виджет стоит прозрачным и шириной в долю своего места.
        """
        self._refresh_uptime()
        ratio = max(1.0, float(self.devicePixelRatioF()))
        width, height = self.full_width(), self.height()
        pixmap = QPixmap(max(1, round(width * ratio)), max(1, round(height * ratio)))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        self._paint_net67(painter, width=width, presence=1.0, live=False)
        painter.end()
        return pixmap

    def retranslate(self) -> bool:
        if not self._phase:
            return False
        return self._render()

    def _render(self) -> bool:
        view = build_launch_badge_view(
            phase=self._phase,
            launch_method=self._launch_method,
            language=self._language_provider(),
        )
        if self._override_text:
            view = LaunchBadgeView(
                phase="starting",
                text=self._override_text,
                tooltip="Кнопка обхода ещё выполняет свои шаги",
            )
        was_hidden = self.isHidden()
        old_text = self.text()

        self._apply_style(view.phase)
        # Во время остановки нажимать нечего — ждём, пока процесс завершится.
        # И пока «одна кнопка» выполняет шаги: выключить обход посреди них
        # значит оставить её цепочку на полпути.
        self.setEnabled(view.phase != "stopping" and not self._override_text)
        state_changed = self._state_text != view.text
        self._state_text = view.text
        self._tooltip_text = view.tooltip
        shown = self._uptime_text() if self._shows_uptime() else view.text
        if old_text != shown:
            self.setText(shown)
        self._apply_width()
        set_tooltip(self, view.tooltip)
        # Время работы в имя не идёт: оно менялось бы каждую секунду, и
        # программа экранного доступа читала бы метку без остановки.
        set_control_accessibility(self, name=f"Состояние net67: {view.text}", description=view.tooltip)
        self._sync_breath()
        if was_hidden and self._slot > 0.001:
            self.show()
        self.update()
        return was_hidden or state_changed

    # ---- время работы -----------------------------------------------------

    def state_text(self) -> str:
        """Состояние словом («Работает», «Остановлен») — и когда на метке время."""
        return self._state_text

    def _shows_uptime(self) -> bool:
        return self._phase == "running" and not self._override_text

    def _uptime_text(self) -> str:
        from ui.launch_uptime import ensure, format_uptime

        return format_uptime(time.monotonic() - ensure())

    def _refresh_uptime(self) -> None:
        if not self._shows_uptime():
            return
        text = self._uptime_text()
        if text == self.text():
            return
        grew = len(text) != len(self.text())
        self.setText(text)
        if grew:
            # «9:59» → «10:00»: метка шире на цифру.
            self._apply_width()
        self.update()

    # ---- «дыхание» точки во время запуска/остановки --------------------

    def _can_animate(self) -> bool:
        if not self.isVisible():
            return False
        window = self.window()
        if window is not None and window.isMinimized():
            return False
        return are_live_animations_enabled()

    def _can_breathe(self) -> bool:
        busy = self._phase in BUSY_LAUNCH_PHASES or bool(self._override_text)
        return busy and self._can_animate()

    def _can_pulse(self) -> bool:
        return self._phase == "running" and not self._override_text and self._can_animate()

    def _sync_breath(self) -> None:
        if self._can_breathe():
            if self._breath.state() != QVariantAnimation.State.Running:
                self._breath.start()
        else:
            self._breath.stop()
            self._breath_t = 0.0
        if self._can_pulse():
            if self._pulse.state() != QVariantAnimation.State.Running:
                self._pulse.start()
        else:
            self._pulse.stop()
            self._pulse_t = 0.0
        if self._shows_uptime() and self.isVisible():
            self._refresh_uptime()
            if not self._uptime_timer.isActive():
                self._uptime_timer.start()
        else:
            self._uptime_timer.stop()

    def is_pulsing(self) -> bool:
        return self._pulse.state() == QVariantAnimation.State.Running

    def _on_pulse_value(self, value) -> None:
        try:
            self._pulse_t = float(value)
        except (TypeError, ValueError):
            return
        self.update()

    def is_breathing(self) -> bool:
        return self._breath.state() == QVariantAnimation.State.Running

    def _on_breath_value(self, value) -> None:
        try:
            self._breath_t = float(value)
        except (TypeError, ValueError):
            return
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_breath()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._breath.stop()
        self._pulse.stop()
        self._uptime_timer.stop()
        super().hideEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_breath()

    def _text_left(self) -> int:
        return NET67_ON_TEXT_LEFT if self._shows_uptime() else NET67_TEXT_LEFT

    def full_width(self) -> int:
        """Ширина метки, когда она стоит целиком.

        Цифры меряются как нули: у пропорционального шрифта «1» уже «0»,
        и метка со временем работы дрожала бы на пиксель каждую секунду —
        а с ней и вкладки заголовка.
        """
        text = re.sub(r"[0-9]", "0", self.text() or "")
        return self._text_left() + self._text_metrics().horizontalAdvance(text) + NET67_TEXT_RIGHT

    def _apply_width(self) -> None:
        self.setFixedWidth(max(0, round(self.full_width() * self._slot)))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.full_width(), NET67_BADGE_HEIGHT)

    def _text_font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        return font

    def _text_metrics(self):
        from PyQt6.QtGui import QFontMetrics

        return QFontMetrics(self._text_font())

    def paintEvent(self, event) -> None:  # noqa: N802
        """Метка net67 рисует себя целиком — фон, точку и текст.

        У zapret текст рисует стиль Qt с отступом под точку из QSS. В net67
        общие стили кнопок этот отступ перебивали, текст вставал по
        центру и наезжал на точку. И цвета: зелёная и жёлтая подложки
        выбивались из монохромного заголовка — вес держит светлота, а не
        цвет, как во всём интерфейсе net67 (так же рисует себя колокольчик).
        """
        if self._presence <= 0.001:
            # Место занято, а метки ещё нет: её снимок в пути из круга.
            return
        painter = QPainter(self)
        # В пути место уже метки: рисуем её целиком от правого края, и
        # левый край обрезается — метка «выезжает» из-под вкладок.
        full = self.full_width()
        if self.width() < full:
            painter.translate(self.width() - full, 0)
        self._paint_net67(painter, width=full, presence=self._presence, live=True)
        painter.end()

    def _paint_net67(self, painter: QPainter, *, width: int, presence: float, live: bool) -> None:
        """Рисует метку шириной ``width``. ``live`` — с наведением и пульсом."""
        from shell.theme import palette
        from ui.theme import get_theme_tokens

        # Тема — из тех же токенов, что у колокольчика рядом.
        try:
            dark = not get_theme_tokens().is_light
        except Exception:
            dark = True
        colors = palette(dark)
        phase = "starting" if self._override_text else self._phase
        running = phase == "running"
        hovered = live and (bool(getattr(self, "isHover", False)) or self.underMouse())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(presence)
        body = QRectF(0, 0, width, self.height()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = body.height() / 2

        # Работает — светлая подложка; остальное — рамка, как у соседних
        # кнопок заголовка.
        if running:
            fill = QColor(colors.text)
            fill.setAlphaF(0.16 if hovered else 0.11)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
        else:
            painter.setPen(QPen(QColor(colors.border_strong), 1.0))
            painter.setBrush(QColor(colors.surface_hover) if hovered else Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body, radius, radius)

        center = QPointF(NET67_DOT_LEFT, self.height() / 2)
        if running:
            self._paint_on_mark(painter, center, colors, body, radius, live=live)
        elif phase:
            dot = QColor(colors.text_muted)
            painter.setPen(Qt.PenStyle.NoPen)
            if live and self.is_pulsing():
                p = self._pulse_t
                ring = QColor(dot)
                ring.setAlphaF(0.8 * (1.0 - p) ** 1.3)
                painter.save()
                painter.setPen(QPen(ring, 1.6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                r = BADGE_DOT_RADIUS + 1.0 + RUNNING_RING_GROWTH * (1.0 - (1.0 - p) ** 2)
                painter.drawEllipse(center, r, r)
                painter.restore()
            if live and self.is_breathing():
                strength = 0.35 + 0.65 * (0.5 - 0.5 * math.cos(2.0 * math.pi * self._breath_t))
                dot.setAlphaF(0.35 + 0.65 * strength)
            painter.setBrush(dot)
            painter.drawEllipse(center, BADGE_DOT_RADIUS, BADGE_DOT_RADIUS)

        text_left = self._text_left()
        painter.setFont(self._text_font())
        painter.setPen(QColor(colors.text if (running or hovered) else colors.text_muted))
        text_rect = QRectF(text_left, 0, width - text_left - NET67_TEXT_RIGHT + 4, self.height())
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self.text())
        if live and self.hasFocus():
            painter.setPen(QPen(QColor(colors.text_muted), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(body.adjusted(1, 1, -1, -1), radius - 1, radius - 1)

    def _paint_on_mark(self, painter: QPainter, center: QPointF, colors, body: QRectF, radius: float, *, live: bool) -> None:
        """Кружок «включено»: главный круг страницы в миниатюре.

        Те же цвета, что у круга в работающем состоянии (заливка акцентом,
        знак цветом «на акценте»), — метка читается как он же, только
        маленький. Знак питания рисуется линиями: значок из шрифта в
        шестнадцати пикселях расплывался.
        """
        fill = QColor(colors.accent)
        ink = QColor(colors.on_accent)
        if live and self.is_pulsing():
            p = self._pulse_t
            ring = QColor(fill)
            ring.setAlphaF(0.7 * (1.0 - p) ** 1.3)
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(body, radius, radius)
            painter.setClipPath(clip)
            painter.setPen(QPen(ring, 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = NET67_ON_RADIUS + 0.5 + NET67_ON_RING_GROWTH * (1.0 - (1.0 - p) ** 2)
            painter.drawEllipse(center, r, r)
            painter.restore()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(center, NET67_ON_RADIUS, NET67_ON_RADIUS)

        pen = QPen(ink, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        arc = 3.6
        # Дуга с разрывом сверху и чёрточка в разрыве.
        painter.drawArc(QRectF(center.x() - arc, center.y() - arc + 0.4, arc * 2, arc * 2), (90 + 38) * 16, 284 * 16)
        painter.drawLine(QPointF(center.x(), center.y() - arc - 0.6), QPointF(center.x(), center.y() - 0.4))

    def _paint_zapret(self, event) -> None:
        _fg, background, hover = _badge_colors(phase=self._phase, theme_name=current_theme_name())
        # Фон со сглаженными углами — до текста кнопки.
        paint_badge_body(self, background=background, hover_background=hover)
        super().paintEvent(event)
        if not self._phase:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        color = QColor(phase_color(self._phase) or STOPPED_DOT_COLOR)
        center = QPointF(BADGE_DOT_LEFT, self.height() / 2)

        if self.is_pulsing():
            p = self._pulse_t
            # Подложка в такт мягко светлеет и гаснет.
            glow = QColor(color)
            glow.setAlphaF(0.2 * math.sin(math.pi * p))
            shape = badge_shape(self)
            painter.fillPath(shape, glow)
            painter.save()
            painter.setClipPath(shape)
            # Кольцо расходится от точки и тает.
            ring = QColor(color)
            ring.setAlphaF(0.95 * (1.0 - p) ** 1.3)
            painter.setPen(QPen(ring, 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            radius = BADGE_DOT_RADIUS + 1.0 + RUNNING_RING_GROWTH * (1.0 - (1.0 - p) ** 2)
            painter.drawEllipse(center, radius, radius)
            painter.restore()
            painter.setPen(Qt.PenStyle.NoPen)

        if self._phase == "running" or self.is_breathing():
            # Мягкий ореол: у «работает» постоянный, у запуска/остановки дышит.
            strength = 1.0
            if self.is_breathing():
                strength = 0.35 + 0.65 * (0.5 - 0.5 * math.cos(2.0 * math.pi * self._breath_t))
            halo = QColor(color)
            halo.setAlphaF(0.35 * strength)
            painter.setBrush(halo)
            radius = BADGE_DOT_RADIUS + 2.5 * strength
            painter.drawEllipse(center, radius, radius)

        painter.setBrush(color)
        painter.drawEllipse(center, BADGE_DOT_RADIUS, BADGE_DOT_RADIUS)
        painter.end()

    def _apply_style(self, phase: str) -> None:
        style_key = "busy" if phase in BUSY_LAUNCH_PHASES else phase
        if self._styled_phase == style_key:
            return
        self._styled_phase = style_key
        setCustomStyleSheet(
            self,
            _badge_qss(phase=phase, theme_name="light"),
            _badge_qss(phase=phase, theme_name="dark"),
        )


__all__ = [
    "LAUNCH_TITLE_BADGE_OBJECT_NAME",
    "LaunchBadgeView",
    "LaunchTitleBadge",
    "build_launch_badge_view",
]
