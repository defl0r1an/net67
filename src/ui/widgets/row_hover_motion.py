"""Живое наведение на строки списка: мягкая подсветка, блик и покачивание значка.

Помощник подключается к готовому списку (QListView/QListWidget), строки
которого рисует delegate. Когда мышь заходит на строку:
- полупрозрачная подсветка наведения плавно проявляется (а при уходе
  плавно гаснет) с мягким разгоном и торможением;
- значок строки мягко наклоняется и чуть увеличивается, затем возвращается
  на место с лёгкой пружинкой;
- если мышь задержалась на строке, по ней один раз проходит спокойный косой
  блик. При быстром проведении мышью по списку блик не вспыхивает, а на ту же
  строку сразу повторно не запускается.

Сам помощник ничего не рисует: delegate спрашивает у него уровень подсветки,
положение блика и движение значка (см. ``hover_level``, ``sheen_progress``,
``icon_angle``, ``icon_scale``, ``paint_icon_motion``). В покое таймер
остановлен и процессор не тратится.
При выключенных «Живых анимациях» ``hover_level`` возвращает None, и delegate
рисует обычное мгновенное наведение.

Движение живёт в ``HoverMotion`` и не знает, откуда берутся элементы. Раньше
оно было намертво привязано к QListView, и когда zapret 21.1.6.41 заменил
список DNS сеткой плиток, которую рисует один виджет, наведение там пропало
целиком: подключать было не к чему. Теперь строки списков отдаёт
``RowHoverMotion``, плитки — ``TileHoverMotion``, а время, пружинка и блик у
всех одни.
"""

from __future__ import annotations

import math
import time

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QRectF, QTimer
from PyQt6.QtGui import QCursor, QPainter

from ui.animation_policy import are_live_animations_enabled


FADE_IN_MS = 170
FADE_OUT_MS = 260
# Блик — только если мышь задержалась на строке, и не чаще раза в REPEAT.
SHEEN_DWELL_MS = 110
SHEEN_DURATION_MS = 760
SHEEN_REPEAT_MS = 1500
# Значок: один мягкий наклон и возврат с небольшой пружинкой.
TILT_DURATION_MS = 620
TILT_PEAK_DEG = 6.0
TILT_PEAK_SCALE = 0.06
_TILT_DAMPING = 4.6
_TILT_FREQUENCY = 1.05
_TICK_MS = 16
_MOTION_ATTR = "_zapret_row_hover_motion"


class HoverMotion(QObject):
    """Движение наведения для элементов, пронумерованных целыми числами.

    Владелец сообщает, какой элемент под мышью (``set_hover_item``), и
    перерисовывает те, что попросит ``_repaint_items``; всё остальное — здесь.
    """

    def __init__(self, owner) -> None:
        super().__init__(owner)
        self._owner = owner
        self._hover_item = -1
        self._levels: dict[int, float] = {}
        self._started_at: dict[int, float] = {}
        self._sheen_at: dict[int, float] = {}
        self._last_sheen_at: dict[int, float] = {}
        self._last_tick = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    def reset(self, *args) -> None:
        """Элементы перенумерованы: старые номера указывают уже на другие."""
        _ = args
        self._hover_item = -1
        self._levels.clear()
        self._started_at.clear()
        self._sheen_at.clear()
        self._last_sheen_at.clear()
        self._timer.stop()

    def set_hover_item(self, item: int) -> None:
        if item == self._hover_item:
            return
        previous = self._hover_item
        self._hover_item = item
        if not self._can_animate():
            self._levels.clear()
            self._started_at.clear()
            self._sheen_at.clear()
            return
        if previous >= 0:
            self._levels.setdefault(previous, 1.0)
            # Мышь ушла раньше, чем блик успел начаться, — блика не будет.
            planned = self._sheen_at.get(previous)
            if planned is not None and planned > time.monotonic():
                del self._sheen_at[previous]
        if item >= 0:
            now = time.monotonic()
            self._levels.setdefault(item, 0.0)
            self._started_at[item] = now
            last = self._last_sheen_at.get(item)
            if last is None or (now - last) * 1000.0 >= SHEEN_REPEAT_MS:
                self._sheen_at[item] = now + SHEEN_DWELL_MS / 1000.0
        self._start_timer()

    # ---- анимация ------------------------------------------------------

    def _can_animate(self) -> bool:
        try:
            window = self._owner.window()
            if window is not None and window.isMinimized():
                return False
        except RuntimeError:
            return False
        return are_live_animations_enabled()

    def _alive(self) -> bool:
        return not sip.isdeleted(self._owner)

    def _start_timer(self) -> None:
        if not self._timer.isActive():
            self._last_tick = time.monotonic()
            self._timer.start()

    def _tick(self) -> None:
        if not self._alive():
            self._timer.stop()
            return
        now = time.monotonic()
        dt_ms = max(0.0, (now - self._last_tick) * 1000.0)
        self._last_tick = now

        dirty: set[int] = set()
        for item in list(self._levels):
            target = 1.0 if item == self._hover_item else 0.0
            level = self._levels[item]
            if level < target:
                level = min(target, level + dt_ms / FADE_IN_MS)
            elif level > target:
                level = max(target, level - dt_ms / FADE_OUT_MS)
            if level <= 0.0 and target == 0.0:
                del self._levels[item]
            else:
                self._levels[item] = level
            dirty.add(item)

        for item, started in list(self._started_at.items()):
            dirty.add(item)
            if now - started > TILT_DURATION_MS / 1000.0:
                del self._started_at[item]
        for item, begins in list(self._sheen_at.items()):
            if now < begins:
                continue
            dirty.add(item)
            self._last_sheen_at[item] = begins
            if now - begins > SHEEN_DURATION_MS / 1000.0:
                del self._sheen_at[item]

        self._repaint_items(dirty)
        settled = not self._started_at and not self._sheen_at and all(
            level == (1.0 if item == self._hover_item else 0.0) for item, level in self._levels.items()
        )
        if settled:
            self._timer.stop()

    def _repaint_items(self, items: set[int]) -> None:
        raise NotImplementedError

    # ---- запросы того, кто рисует ---------------------------------------

    def level_of(self, item: int) -> float | None:
        """Насколько проявлена подсветка наведения (0..1); None — рисовать как обычно."""
        if not are_live_animations_enabled():
            return None
        level = self._levels.get(item, 1.0 if item == self._hover_item else 0.0)
        # Мягкий разгон и торможение вместо равномерного перехода.
        return level * level * (3.0 - 2.0 * level)

    def sheen_of(self, item: int) -> float | None:
        """Положение блика вдоль элемента (0..1) или None, если блика нет."""
        begins = self._sheen_at.get(item)
        if begins is None:
            return None
        t = (time.monotonic() - begins) * 1000.0 / SHEEN_DURATION_MS
        if not 0.0 <= t < 1.0:
            return None
        # Плавно разгоняется и плавно тормозит у правого края.
        return 4.0 * t ** 3 if t < 0.5 else 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0

    def _tilt_t(self, item: int) -> float | None:
        started = self._started_at.get(item)
        if started is None:
            return None
        t = (time.monotonic() - started) * 1000.0 / TILT_DURATION_MS
        return t if 0.0 < t < 1.0 else None

    def angle_of(self, item: int) -> float:
        """Наклон значка: быстрый мягкий наклон, возврат с маленькой пружинкой."""
        t = self._tilt_t(item)
        if t is None:
            return 0.0
        return TILT_PEAK_DEG * _tilt_wave(t) / _TILT_WAVE_PEAK * (1.0 - t)

    def scale_of(self, item: int) -> float:
        """Лёгкое увеличение значка вместе с наклоном (1.0 — обычный размер)."""
        t = self._tilt_t(item)
        if t is None:
            return 1.0
        return 1.0 + TILT_PEAK_SCALE * _scale_wave(t) / _SCALE_WAVE_PEAK

    def moving(self, item: int) -> bool:
        return self._tilt_t(item) is not None


class RowHoverMotion(HoverMotion):
    """Наведение на строки QListView/QListWidget; delegate спрашивает по QModelIndex."""

    def __init__(self, view, *, row_filter=None) -> None:
        super().__init__(view)
        self._view = view
        self._row_filter = row_filter
        self._model = None

        viewport = view.viewport()
        viewport.setMouseTracking(True)
        viewport.installEventFilter(self)
        self._bind_model()

    # ---- модель --------------------------------------------------------

    def _bind_model(self) -> None:
        model = self._view.model()
        if model is self._model:
            return
        self._model = model
        self.reset()
        if model is None:
            return
        for signal in (
            model.modelReset,
            model.layoutChanged,
            model.rowsInserted,
            model.rowsRemoved,
            model.rowsMoved,
        ):
            signal.connect(self.reset)

    # ---- наведение -----------------------------------------------------

    def _row_at(self, pos) -> int:
        index = self._view.indexAt(pos)
        if not index.isValid():
            return -1
        if self._row_filter is not None:
            try:
                if not self._row_filter(index):
                    return -1
            except Exception:
                return -1
        return index.row()

    def _recheck_under_cursor(self) -> None:
        if not self._alive():
            return
        viewport = self._view.viewport()
        pos = viewport.mapFromGlobal(QCursor.pos())
        if not viewport.rect().contains(pos):
            self.set_hover_item(-1)
            return
        self.set_hover_item(self._row_at(pos))

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        kind = event.type()
        if kind in (QEvent.Type.MouseMove, QEvent.Type.HoverMove, QEvent.Type.HoverEnter):
            self._bind_model()
            self.set_hover_item(self._row_at(event.position().toPoint()))
        elif kind in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            self.set_hover_item(-1)
        elif kind == QEvent.Type.Wheel:
            # Под неподвижным курсором строки уезжают при прокрутке.
            QTimer.singleShot(0, self._recheck_under_cursor)
        return False

    def _repaint_items(self, items: set[int]) -> None:
        model = self._view.model()
        if model is None:
            return
        viewport = self._view.viewport()
        for row in items:
            if 0 <= row < model.rowCount():
                viewport.update(self._view.visualRect(model.index(row, 0)))

    # ---- запросы delegate ----------------------------------------------

    def hover_level(self, index) -> float | None:
        return self.level_of(index.row())

    def sheen_progress(self, index) -> float | None:
        return self.sheen_of(index.row())

    def icon_angle(self, index) -> float:
        return self.angle_of(index.row())

    def icon_scale(self, index) -> float:
        return self.scale_of(index.row())

    def icon_moving(self, index) -> bool:
        return self.moving(index.row())


class TileHoverMotion(HoverMotion):
    """Наведение на плитки, которые рисует один виджет, — сетка DNS.

    Какая плитка под мышью, сетка знает сама и сообщает через
    ``set_hover_item``; перерисовать плитки по номерам — её ``repaint``.
    """

    def __init__(self, owner, *, repaint) -> None:
        super().__init__(owner)
        self._repaint = repaint

    def _repaint_items(self, items: set[int]) -> None:
        self._repaint(items)


def _tilt_wave(t: float) -> float:
    return math.exp(-_TILT_DAMPING * t) * math.sin(2.0 * math.pi * _TILT_FREQUENCY * t)


def _scale_wave(t: float) -> float:
    return math.sin(math.pi * t) ** 2 * (1.0 - t) ** 1.5


def _wave_peak(wave) -> float:
    return max(wave(step / 400.0) for step in range(1, 400)) or 1.0


# Нормировка: TILT_PEAK_DEG и TILT_PEAK_SCALE — настоящие максимумы движения.
_TILT_WAVE_PEAK = _wave_peak(_tilt_wave)
_SCALE_WAVE_PEAK = _wave_peak(_scale_wave)


def paint_rotated(painter: QPainter, rect, angle: float, draw, *, scale: float = 1.0) -> None:
    """Рисует draw() с поворотом и масштабом вокруг центра rect.

    Во время движения включено сглаживание: без него маленький значок при
    повороте рвётся «лесенкой» по краям.
    """
    if abs(angle) < 0.01 and abs(scale - 1.0) < 0.002:
        draw()
        return
    center = QRectF(rect).center()
    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(center)
        painter.rotate(angle)
        painter.scale(scale, scale)
        painter.translate(-center)
        draw()
    finally:
        painter.restore()


def paint_icon_motion(painter: QPainter, rect, motion, index, draw) -> None:
    """Рисует значок строки с наклоном и увеличением от наведения (если есть)."""
    if motion is None:
        draw()
        return
    paint_rotated(painter, rect, motion.icon_angle(index), draw, scale=motion.icon_scale(index))


def attach_row_hover_motion(view, *, row_filter=None) -> RowHoverMotion:
    """Подключает живое наведение к списку (один раз на список)."""
    motion = view.__dict__.get(_MOTION_ATTR)
    if motion is None:
        motion = RowHoverMotion(view, row_filter=row_filter)
        view.__dict__[_MOTION_ATTR] = motion
    return motion


def row_hover_motion(view) -> RowHoverMotion | None:
    try:
        return view.__dict__.get(_MOTION_ATTR)
    except Exception:
        return None


__all__ = [
    "HoverMotion",
    "RowHoverMotion",
    "TileHoverMotion",
    "attach_row_hover_motion",
    "paint_icon_motion",
    "paint_rotated",
    "row_hover_motion",
]
