"""Появление и уход всплывающей панели — из кнопки, которая её открыла.

Панель колокольчика появлялась рывком и так же рывком пропадала: её
просто показывали и прятали. Глаз не видел, откуда она взялась, и
панель читалась как чужое окно поверх программы, а не как продолжение
кнопки.

Теперь панель вырастает из колокольчика и уходит обратно в него тем же
путём. Движение — пружина с критическим затуханием: без перелёта,
потому что у щелчка нет импульса, который бы его оправдал. Пружина
держит скорость, поэтому движение можно перехватить на полпути:
щелчок мимо во время появления разворачивает панель обратно с той
точки и той скоростью, что на экране, без скачка.

Движется не сама панель, а её снимок в отдельном окне-призраке.
Причин две:
- панель — Popup: пока она на экране, она забирает мышь. Анимированный
  уход держал бы её там ещё треть секунды, и щелчок по окну в это время
  съедался бы. Поэтому панель прячется сразу, а уходит призрак, прозрачный
  для мыши;
- масштабировать живые виджеты Qt не умеет, снимок — умеет.

При появлении настоящая панель показывается сразу, но невидимой: она уже
ловит щелчки, пока призрак вырастает, и ничего не приходится ждать.
Когда призрак встал на место, панель становится видимой, призрак
исчезает — снимок совпадает с панелью, подмены не видно.
"""

from __future__ import annotations

import math
import time

from PyQt6 import sip
from PyQt6.QtCore import QObject, QPoint, QPointF, QRect, QTimer, Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from ui.animation_policy import are_animations_enabled, are_live_animations_enabled

__all__ = ["PopupMotion", "Spring", "popup_motion_mode"]

#: Отклик пружины, с: за сколько значение в основном доходит до цели.
#: Это не длительность — у пружины её нет, время успокоения выходит из
#: отклика и затухания.
RESPONSE_S = 0.3

#: Затухание 1.0 — критическое, без перелёта. Отскок уместен, когда
#: движению предшествовал бросок; панель открывают щелчком.
DAMPING = 1.0

#: Масштаб в начале пути. Не из точки: на первых кадрах текст в
#: крошечной панели сливается в кашу, и появление выглядит как вспышка.
START_SCALE = 0.9

#: Шаг кадров, мс.
FRAME_MS = 16

#: Самый большой шаг времени за кадр, с.
#:
#: Первое появление создаёт два окна, и первый кадр приходил через
#: 100–150 мс: пружина за один шаг проходила 70 % пути, и панель не
#: вырастала, а выскакивала. Опоздавший кадр теперь только замедляет
#: движение — оно начинается с начала, а не с середины.
MAX_FRAME_DT_S = 1.0 / 30.0

#: Шаг интегрирования, с. Кадр может прийти и через 50 мс, если окно
#: занято; большой шаг раскачал бы жёсткую пружину.
_SUBSTEP_S = 1.0 / 240.0


class Spring:
    """Одномерная пружина, которую можно перенацелить на ходу.

    Новая цель не сбрасывает скорость: движение, развёрнутое на полпути,
    плавно тормозит и идёт обратно, а не упирается в стену.
    """

    def __init__(self, value: float = 0.0, *, response: float = RESPONSE_S, damping: float = DAMPING) -> None:
        omega = 2.0 * math.pi / max(0.01, float(response))
        self._stiffness = omega * omega
        self._friction = 2.0 * float(damping) * omega
        self.value = float(value)
        self.velocity = 0.0
        self.target = float(value)

    def retarget(self, target: float) -> None:
        self.target = float(target)

    def jump(self, value: float) -> None:
        """Сразу в точку — когда движения нет вовсе (анимации выключены)."""
        self.value = self.target = float(value)
        self.velocity = 0.0

    def step(self, dt: float) -> None:
        remaining = max(0.0, float(dt))
        while remaining > 1e-9:
            h = min(_SUBSTEP_S, remaining)
            acceleration = -self._stiffness * (self.value - self.target) - self._friction * self.velocity
            self.velocity += acceleration * h
            self.value += self.velocity * h
            remaining -= h

    def settled(self) -> bool:
        return abs(self.value - self.target) < 1e-3 and abs(self.velocity) < 1e-2


def popup_motion_mode() -> str:
    """Каким будет движение: «spring», «fade» или «none».

    Выключенные «лёгкие анимации» — просьба убрать движение, а не
    отклик: остаётся спокойное проявление без масштаба и сдвига. Если
    выключены и анимации Windows, панель просто появляется.
    """
    if are_live_animations_enabled():
        return "spring"
    if are_animations_enabled():
        return "fade"
    return "none"


class _Ghost(QWidget):
    """Окно со снимком панели. Мышь проходит сквозь него."""

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.snapshot = QPixmap()
        self.origin = QPointF()
        self.progress = 0.0
        self.scale_motion = True

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        if self.snapshot.isNull():
            return
        p = max(0.0, min(1.0, self.progress))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setOpacity(p)
        if self.scale_motion and p < 1.0:
            scale = START_SCALE + (1.0 - START_SCALE) * p
            painter.translate(self.origin)
            painter.scale(scale, scale)
            painter.translate(-self.origin)
        painter.drawPixmap(0, 0, self.snapshot)
        painter.end()


class PopupMotion(QObject):
    """Ведёт появление и уход одной всплывающей панели за раз.

    Живёт дольше панели (панель удаляется при закрытии), поэтому
    принадлежит окну, а не ей.
    """

    def __init__(self, owner: QWidget) -> None:
        super().__init__(owner)
        self._owner = owner
        self._ghost: _Ghost | None = None
        self._panel: QWidget | None = None
        self._spring = Spring(0.0)
        self._mode = "spring"
        self._last_tick = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # ── снаружи ──────────────────────────────────────────────

    @property
    def progress(self) -> float:
        return self._spring.value

    def is_moving(self) -> bool:
        return self._timer.isActive()

    def ghost(self) -> _Ghost | None:
        return self._ghost

    def open(self, panel: QWidget, anchor_global: QPoint) -> None:
        """Показывает панель, выращивая её из точки anchor_global (экран)."""
        self._mode = popup_motion_mode()
        self._panel = panel
        if self._mode == "none":
            self._spring.jump(1.0)
            self._hide_ghost()
            self._timer.stop()
            panel.setWindowOpacity(1.0)
            panel.show()
            return
        layout = panel.layout()
        if layout is not None:
            layout.activate()
        snapshot = panel.grab()
        panel.setWindowOpacity(0.0)
        panel.show()
        self._show_ghost(panel.geometry(), snapshot, anchor_global)
        self._spring.retarget(1.0)
        self._start()

    def close(self, panel: QWidget, anchor_global: QPoint) -> None:
        """Панель уже закрывается — уводит её снимок обратно к anchor_global."""
        if panel is not self._panel:
            return
        self._panel = None
        if self._mode == "none" or sip.isdeleted(panel):
            self._spring.jump(0.0)
            self._hide_ghost()
            self._timer.stop()
            return
        # Снимок — таким, какой панель сейчас: записи могли смениться, пока
        # она была открыта.
        self._show_ghost(panel.geometry(), panel.grab(), anchor_global)
        self._spring.retarget(0.0)
        self._start()

    # ── кадры ────────────────────────────────────────────────

    def _start(self) -> None:
        if not self._timer.isActive():
            self._last_tick = time.monotonic()
            self._timer.start()
        self._paint()

    def _tick(self) -> None:
        now = time.monotonic()
        self._spring.step(min(MAX_FRAME_DT_S, now - self._last_tick))
        self._last_tick = now
        if self._spring.settled():
            self._spring.jump(self._spring.target)
            self._timer.stop()
            self._finish()
            return
        self._paint()

    def _paint(self) -> None:
        ghost = self._ghost
        if ghost is not None and not sip.isdeleted(ghost):
            ghost.progress = self._spring.value
            ghost.update()

    def _finish(self) -> None:
        panel = self._panel
        if self._spring.target >= 1.0 and panel is not None and not sip.isdeleted(panel):
            panel.setWindowOpacity(1.0)
        self._hide_ghost()

    # ── призрак ──────────────────────────────────────────────

    def _show_ghost(self, geometry: QRect, snapshot: QPixmap, anchor_global: QPoint) -> None:
        ghost = self._ghost
        if ghost is None or sip.isdeleted(ghost):
            ghost = _Ghost(self._owner if not sip.isdeleted(self._owner) else None)
            self._ghost = ghost
        ghost.setGeometry(geometry)
        ghost.snapshot = snapshot
        ghost.origin = QPointF(anchor_global - geometry.topLeft())
        ghost.scale_motion = self._mode == "spring"
        ghost.progress = self._spring.value
        if not ghost.isVisible():
            ghost.show()
        ghost.raise_()
        ghost.update()

    def _hide_ghost(self) -> None:
        ghost = self._ghost
        if ghost is not None and not sip.isdeleted(ghost):
            ghost.hide()
            ghost.snapshot = QPixmap()
