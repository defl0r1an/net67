"""Метка «● Работает / ● Остановлен» в верхней панели окна.

Метка видна в любом разделе и сама является выключателем: клик запускает
или останавливает net67 через единый пульт ui.launch_control.LaunchControl.
Состояние она не вычисляет — фаза приходит из общего UI-store через
ui/window_state_binder.py.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
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

        self.setObjectName(LAUNCH_TITLE_BADGE_OBJECT_NAME)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedHeight(NET67_BADGE_HEIGHT)
        policy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Спрятанная метка держит место: иначе вкладки заголовка рядом
        # прыгали бы на каждом переходе круга в метку и обратно.
        policy.setRetainSizeWhenHidden(True)
        self.setSizePolicy(policy)

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

    def set_presence(self, value: float) -> None:
        """0 — метки нет (её место у главного круга), 1 — видна целиком.

        Промежуточное — только проявление без движения, когда «лёгкие
        анимации» выключены: полёт снимка тогда не показывают.
        """
        value = max(0.0, min(1.0, float(value)))
        self._presence = value
        # Полупрозрачную метку не нажать: щелчок по тени выключателя
        # выключил бы обход, которого человек не видел.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, value < 0.999)
        if value <= 0.001:
            if not self.isHidden():
                self.hide()
            return
        if self.isHidden() and self._phase:
            self.show()
        self.update()

    def presence(self) -> float:
        return self._presence

    def grab_full(self) -> QPixmap:
        """Снимок метки целиком, как она встанет, — для полёта из круга."""
        saved = self._presence
        self._presence = 1.0
        try:
            return self.grab()
        finally:
            self._presence = saved

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
        if old_text != view.text:
            self.setText(view.text)
            self.setFixedWidth(self.sizeHint().width())
        set_tooltip(self, view.tooltip)
        set_control_accessibility(self, name=f"Состояние net67: {view.text}", description=view.tooltip)
        self._sync_breath()
        if was_hidden and self._presence > 0.001:
            self.show()
        self.update()
        return was_hidden or old_text != view.text

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
        super().hideEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_breath()

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = self._text_metrics()
        width = NET67_TEXT_LEFT + metrics.horizontalAdvance(self.text() or "") + NET67_TEXT_RIGHT
        return QSize(width, NET67_BADGE_HEIGHT)

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
        self._paint_net67()

    def _paint_net67(self) -> None:
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
        hovered = bool(getattr(self, "isHover", False)) or self.underMouse()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._presence)
        body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
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

        if phase:
            dot = QColor(colors.text if running else colors.text_muted)
            center = QPointF(NET67_DOT_LEFT, self.height() / 2)
            painter.setPen(Qt.PenStyle.NoPen)
            if self.is_pulsing():
                p = self._pulse_t
                ring = QColor(dot)
                ring.setAlphaF(0.8 * (1.0 - p) ** 1.3)
                painter.save()
                painter.setPen(QPen(ring, 1.6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                r = BADGE_DOT_RADIUS + 1.0 + RUNNING_RING_GROWTH * (1.0 - (1.0 - p) ** 2)
                painter.drawEllipse(center, r, r)
                painter.restore()
            if self.is_breathing():
                strength = 0.35 + 0.65 * (0.5 - 0.5 * math.cos(2.0 * math.pi * self._breath_t))
                dot.setAlphaF(0.35 + 0.65 * strength)
            painter.setBrush(dot)
            painter.drawEllipse(center, BADGE_DOT_RADIUS, BADGE_DOT_RADIUS)

        painter.setFont(self._text_font())
        painter.setPen(QColor(colors.text if (running or hovered) else colors.text_muted))
        text_rect = QRectF(NET67_TEXT_LEFT, 0, self.width() - NET67_TEXT_LEFT - NET67_TEXT_RIGHT + 4, self.height())
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self.text())
        if self.hasFocus():
            painter.setPen(QPen(QColor(colors.text_muted), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(body.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
        painter.end()

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
