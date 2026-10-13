"""Живой список серверов VPN: строки приходят и уходят, наведение плавное.

Список пересобирается целиком на каждое сворачивание группы и на каждую
смену вкладки: clear() и сборка заново. Серверы группы пропадали за кадр,
нижние строки прыгали вверх, при смене вкладки весь список подменялся
мгновенно. Подсветка под мышью включалась рывком, хотя в списках
профилей и пресетов она давно плавная.

Здесь две вещи.

``ServerListMotion`` — появление и уход строк. Строка появляется
вырастая из нулевой высоты и проявляясь, уходит — наоборот, волной снизу
вверх, как блоки в ui/reveal.py. Высота меняется через подсказку размера
строки: соседи подъезжают сами, без прыжка. Прерванное движение
продолжается с того значения, что на экране.

``ServerListDelegate`` — рисует строку с этим движением и плавной
подсветкой наведения (ui/widgets/row_hover_motion.py). Остальное — фон
выбранной строки, текст, флаг — рисует таблица стилей, как и раньше.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QObject, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ui.animation_policy import are_animations_enabled, are_live_animations_enabled

#: Сколько вырастает и проявляется одна строка.
#:
#: Короче появления блока страницы (REVEAL_MS): строк в группе бывает
#: тридцать, и волна должна закончиться раньше, чем человек начнёт читать.
ROW_APPEAR_MS = 220

#: Сколько гаснет и сжимается одна строка. Уход короче появления: на
#: уезжающее не смотрят.
ROW_LEAVE_MS = 170

#: Задержка между соседними строками и предел очереди.
#:
#: Тридцать строк по 28 мс — почти секунда до последней, поэтому после
#: десятой задержка не растёт: дальние строки трогаются вместе.
ROW_STAGGER_MS = 28
ROW_STAGGER_LIMIT = 10

#: На сколько точек строка поднимается, пока проявляется.
ROW_RISE_PX = 5

_TICK_MS = 16


def _out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def _in_cubic(t: float) -> float:
    return t**3


class _RowMove:
    __slots__ = ("start", "target", "began", "delay", "duration")

    def __init__(self, start: float, target: float, began: float, delay: float, duration: float) -> None:
        self.start = start
        self.target = target
        self.began = began
        self.delay = delay
        self.duration = duration

    def value(self, now: float) -> float:
        elapsed = now - self.began - self.delay
        if elapsed <= 0:
            return self.start
        t = min(1.0, elapsed / self.duration) if self.duration > 0 else 1.0
        ease = _out_cubic(t) if self.target > self.start else _in_cubic(t)
        return self.start + (self.target - self.start) * ease

    def done(self, now: float) -> bool:
        return now - self.began - self.delay >= self.duration


class ServerListMotion(QObject):
    """Появление и уход строк списка: прогресс 0..1 на строку."""

    def __init__(self, view) -> None:
        super().__init__(view)
        self._view = view
        self._moves: dict[int, _RowMove] = {}
        self._settled: dict[int, float] = {}
        self._finish = None
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ── что спрашивает delegate ───────────────────────────────────────

    def progress(self, row: int) -> float:
        move = self._moves.get(int(row))
        if move is not None:
            return max(0.0, min(1.0, move.value(time.monotonic())))
        return self._settled.get(int(row), 1.0)

    def busy(self) -> bool:
        return bool(self._moves)

    # ── что зовёт страница ────────────────────────────────────────────

    def reset(self) -> None:
        """Список пересобран: номера строк указывают уже на другие строки."""
        self._moves.clear()
        self._settled.clear()
        self._timer.stop()
        self._finish = None

    def appear(self, rows) -> bool:
        """Строки вырастают и проявляются волной сверху вниз. False — без движения."""
        rows = sorted({int(row) for row in rows if int(row) >= 0})
        if not rows or not are_animations_enabled():
            return False
        now = time.monotonic()
        for order, row in enumerate(rows):
            start = self.progress(row) if row in self._moves else 0.0
            delay = min(order, ROW_STAGGER_LIMIT) * ROW_STAGGER_MS / 1000.0
            self._moves[row] = _RowMove(start, 1.0, now, delay, ROW_APPEAR_MS * (1.0 - start) / 1000.0)
            self._settled.pop(row, None)
        self._start()
        return True

    def leave(self, rows, *, on_finished) -> bool:
        """Строки гаснут и сжимаются волной снизу вверх, потом on_finished.

        False — движения не будет (анимации выключены или строк нет):
        тогда убирать обязан вызывающий, и сразу.
        """
        rows = sorted({int(row) for row in rows if int(row) >= 0}, reverse=True)
        if not rows or not are_animations_enabled():
            return False
        now = time.monotonic()
        for order, row in enumerate(rows):
            start = self.progress(row)
            delay = min(order, ROW_STAGGER_LIMIT) * ROW_STAGGER_MS / 1000.0
            self._moves[row] = _RowMove(start, 0.0, now, delay, ROW_LEAVE_MS * start / 1000.0)
        self._finish = on_finished
        self._start()
        return True

    # ── ход ───────────────────────────────────────────────────────────

    def _start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self._tick()

    def _tick(self) -> None:
        now = time.monotonic()
        changed = list(self._moves)
        for row, move in list(self._moves.items()):
            if move.done(now):
                self._settled[row] = move.target
                del self._moves[row]
        self._relayout(changed)
        if self._moves:
            return
        self._timer.stop()
        finish, self._finish = self._finish, None
        if finish is not None:
            finish()

    def _relayout(self, rows) -> None:
        view = self._view
        try:
            delegate = view.itemDelegate()
            model = view.model()
            for row in rows:
                index = model.index(row, 0)
                if index.isValid():
                    delegate.sizeHintChanged.emit(index)
            view.viewport().update()
        except RuntimeError:
            # Список удалён вместе со страницей.
            self._timer.stop()
            self._moves.clear()


class ServerListDelegate(QStyledItemDelegate):
    """Строка с движением появления и плавной подсветкой наведения."""

    def __init__(self, view, motion: ServerListMotion, hover) -> None:
        super().__init__(view)
        self._motion = motion
        self._hover = hover

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 (Qt override)
        base = super().sizeHint(option, index)
        progress = self._motion.progress(index.row())
        if progress >= 1.0:
            return base
        return QSize(base.width(), max(0, int(round(base.height() * _out_cubic(progress)))))

    def paint(self, painter: QPainter, option, index) -> None:
        progress = self._motion.progress(index.row())
        if progress <= 0.0:
            return
        opt = QStyleOptionViewItem(option)
        hovered = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        # Подсветку наведения рисуем сами: у таблицы стилей она включается
        # рывком. Флаг снимаем, чтобы стиль не положил свою поверх нашей.
        opt.state &= ~QStyle.StateFlag.State_MouseOver

        painter.save()
        try:
            painter.setClipRect(option.rect)
            if progress < 1.0:
                # Пока строка мала по высоте, текст в ней давил бы сам себя:
                # проявляется она быстрее к концу пути, чем растёт.
                painter.setOpacity(painter.opacity() * progress * progress)
                painter.translate(0, (1.0 - progress) * ROW_RISE_PX)
            if not selected:
                self._paint_hover(painter, option.rect, index, hovered)
            super().paint(painter, opt, index)
        finally:
            painter.restore()

    def _paint_hover(self, painter: QPainter, rect: QRect, index, hovered: bool) -> None:
        live = self._hover is not None and are_live_animations_enabled()
        level = self._hover.hover_level(index) if live else None
        amount = level if level is not None else (1.0 if hovered else 0.0)
        if amount <= 0.0:
            return
        from shell.theme import ITEM_RADIUS, palette
        from ui.theme import get_theme_tokens

        tokens = get_theme_tokens()
        color = QColor(palette(not tokens.is_light).surface_hover)
        color.setAlphaF(max(0.0, min(1.0, amount)))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(rect.adjusted(0, 1, 0, -1).toRectF(), ITEM_RADIUS, ITEM_RADIUS)
        painter.fillPath(path, color)
        sheen = self._hover.sheen_progress(index) if live else None
        if sheen is not None:
            from ui.widgets.hover_row import paint_sheen

            paint_sheen(painter, rect, tokens, sheen, radius=float(ITEM_RADIUS))


def attach_server_list_motion(view) -> ServerListMotion:
    """Ставит на список движение строк, плавное наведение и delegate. Один раз."""
    motion = view.__dict__.get("_net67_server_list_motion")
    if motion is not None:
        return motion
    from ui.widgets.row_hover_motion import attach_row_hover_motion

    motion = ServerListMotion(view)
    hover = attach_row_hover_motion(view)
    view.setItemDelegate(ServerListDelegate(view, motion, hover))
    view.__dict__["_net67_server_list_motion"] = motion
    return motion


__all__ = [
    "ROW_APPEAR_MS",
    "ROW_LEAVE_MS",
    "ROW_STAGGER_MS",
    "ServerListDelegate",
    "ServerListMotion",
    "attach_server_list_motion",
]
