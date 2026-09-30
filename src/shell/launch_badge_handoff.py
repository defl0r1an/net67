"""Метка в заголовке — продолжение главной кнопки, а не её копия.

На главной странице метка «● Работает» стояла над большим кругом и
говорила то же, что он, — два выключателя одного и того же на одном
экране. Владелец попросил: пока круг виден, метки нет; ушёл круг из
вида — прокруткой или переходом в другой раздел, — и он сам уходит
наверх, в метку. Вернулся — метка уходит обратно в круг тем же путём.

Движение — снимок, который летит от круга к метке и по дороге
перетекает из круга в пилюлю. Пружина с критическим затуханием (без
перелёта: у прокрутки нет броска, который его оправдал бы) и можно
развернуть на полпути — со скоростью, что на экране. Концы пути читаются
на каждом кадре: круг, уезжающий вместе с прокруткой, призрак догоняет,
а не прилетает туда, где круг был в начале.

Пока снимок в пути, настоящей метки нет: две метки на экране — та же
двойственность, от которой уходили. Место в заголовке за ней держится
(retainSizeWhenHidden), иначе вкладки рядом прыгали бы на каждом
переходе.
"""

from __future__ import annotations

import time

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QPoint, QRectF, QTimer, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QWidget

from ui.popup_motion import DAMPING, FRAME_MS, MAX_FRAME_DT_S, Spring, popup_motion_mode

__all__ = [
    "HANDOFF_RESPONSE_S",
    "LaunchBadgeHandoff",
    "badge_wanted",
    "clip_top",
    "crossfade",
    "lerp_rect",
    "visible_fraction",
]

#: Отклик пружины, с. Перенос предмета с места на место — 0,4 у Apple;
#: чуть быстрее, потому что путь короткий, а метка — мелочь.
HANDOFF_RESPONSE_S = 0.36

#: Сколько круга должно показаться, чтобы метка ушла в него.
#:
#: Метка появляется, только когда круг ушёл целиком, а уходит — когда
#: круг показался хотя бы на эту долю. Без зазора прокрутка, замершая на
#: краю, гоняла бы снимок туда-обратно на каждом пикселе.
SHOW_AT_FRACTION = 0.0
HIDE_AT_FRACTION = 0.05


def visible_fraction(circle: QRectF, viewport: QRectF) -> float:
    """Какая доля круга видна в области прокрутки страницы."""
    area = circle.width() * circle.height()
    if area <= 0:
        return 0.0
    part = circle.intersected(viewport)
    if part.isEmpty():
        return 0.0
    return max(0.0, min(1.0, part.width() * part.height() / area))


def badge_wanted(fraction: float, *, page_current: bool, shown_now: bool) -> bool:
    """Нужна ли метка. ``shown_now`` — зазор, см. SHOW_AT_FRACTION."""
    if not page_current:
        return True
    if shown_now:
        return fraction < HIDE_AT_FRACTION
    return fraction <= SHOW_AT_FRACTION


def lerp_rect(a: QRectF, b: QRectF, t: float) -> QRectF:
    return QRectF(
        a.x() + (b.x() - a.x()) * t,
        a.y() + (b.y() - a.y()) * t,
        a.width() + (b.width() - a.width()) * t,
        a.height() + (b.height() - a.height()) * t,
    )


def clip_top(viewport_top: float, progress: float) -> float:
    """Верх видимой области для снимка.

    В начале пути снимок обрезан страницей, как настоящий круг: круг,
    уехавший за край прокрутки, не должен вдруг проступить поверх
    заголовка. К концу обрезка поднимается до верха окна — снимок
    выходит из-под края туда, куда круг и уехал.
    """
    return viewport_top * (1.0 - max(0.0, min(1.0, progress)))


def crossfade(progress: float) -> float:
    """Доля метки в снимке: круг перетекает в пилюлю в середине пути."""
    t = max(0.0, min(1.0, (progress - 0.2) / 0.6))
    return t * t * (3.0 - 2.0 * t)


class _Ghost(QWidget):
    """Снимок в пути. Дочерний слой окна, мышь проходит насквозь."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.circle = QPixmap()
        self.badge = QPixmap()
        self.rect_now = QRectF()
        self.clip_top = 0.0
        self.mix = 0.0
        self.hide()

    def set_frame(self, rect: QRectF, top: float, mix: float) -> None:
        old = self.rect_now.toAlignedRect().adjusted(-2, -2, 2, 2)
        self.rect_now, self.clip_top, self.mix = rect, top, mix
        # Перерисовываем только след снимка: слой во всё окно, и полная
        # перерисовка тянула бы за собой страницу под ним на каждом кадре.
        self.update(old.united(rect.toAlignedRect().adjusted(-2, -2, 2, 2)))

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        rect = self.rect_now
        if rect.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setClipRect(QRectF(0, self.clip_top, self.width(), self.height() - self.clip_top))
        shape = QPainterPath()
        radius = min(rect.width(), rect.height()) / 2.0
        shape.addRoundedRect(rect, radius, radius)
        painter.setClipPath(shape, Qt.ClipOperation.IntersectClip)
        if self.mix < 1.0 and not self.circle.isNull():
            # Круг вписан по высоте и стоит у левого края пилюли — там,
            # где у метки точка: к концу пути он становится ею.
            side = rect.height()
            painter.setOpacity(1.0 - self.mix)
            painter.drawPixmap(QRectF(rect.x() + (rect.width() - side) * (1.0 - self.mix) / 2.0, rect.y(), side, side), self.circle, QRectF(self.circle.rect()))
        if self.mix > 0.0 and not self.badge.isNull():
            painter.setOpacity(self.mix)
            painter.drawPixmap(rect, self.badge, QRectF(self.badge.rect()))
        painter.end()


class LaunchBadgeHandoff(QObject):
    """Следит, виден ли главный круг, и переводит его в метку и обратно."""

    def __init__(self, window: QWidget, badge, *, locate_circle=None) -> None:
        super().__init__(window)
        self._window = window
        self._badge = badge
        self._locate_circle = locate_circle or self._default_locate
        self._watched: set[int] = set()
        self._shown = True
        self._spring = Spring(1.0, response=HANDOFF_RESPONSE_S, damping=DAMPING)
        self._mode = "none"
        self._ghost = _Ghost(window)
        self._last_tick = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._pending = False
        # Первое решение принимается без движения. Главная страница
        # строится уже после метки, и без этого флага запуск программы
        # начинался с полёта метки в круг — движения, которого никто не
        # вызывал.
        self._primed = False

        stack = getattr(window, "stackedWidget", None)
        signal = getattr(stack, "currentChanged", None)
        if signal is not None:
            signal.connect(lambda *_a: self.schedule())
        window.installEventFilter(self)
        self._evaluate(animate=False)

    # ── где круг ─────────────────────────────────────────────

    @staticmethod
    def _default_locate(window):
        from app.page_names import PageName
        from ui.window_adapter import get_loaded_page

        try:
            page = get_loaded_page(window, PageName.ZAPRET2_MODE_CONTROL)
        except Exception:
            return None, None
        hero = getattr(page, "oneclick_button", None) if page is not None else None
        return page, getattr(hero, "button", None)

    def _watch(self, obj) -> None:
        if obj is None or id(obj) in self._watched:
            return
        self._watched.add(id(obj))
        obj.installEventFilter(self)

    def _geometry(self):
        """(страница видна, доля круга, круг, область прокрутки) в координатах окна."""
        page, circle = self._locate_circle(self._window)
        if page is None or circle is None or sip.isdeleted(page) or sip.isdeleted(circle):
            return False, 0.0, None, None
        viewport = page.viewport() if hasattr(page, "viewport") else page
        self._watch(page)
        self._watch(viewport)
        self._watch(circle)
        self._watch(circle.parentWidget())
        bar = page.verticalScrollBar() if hasattr(page, "verticalScrollBar") else None
        if bar is not None and id(bar) not in self._watched:
            self._watched.add(id(bar))
            bar.valueChanged.connect(lambda *_a: self.schedule())
        origin = viewport.mapTo(self._window, QPoint(0, 0))
        view_rect = QRectF(origin.x(), origin.y(), viewport.width(), viewport.height())
        spot = circle.mapTo(self._window, QPoint(0, 0))
        circle_rect = QRectF(spot.x(), spot.y(), circle.width(), circle.height())
        stack = getattr(self._window, "stackedWidget", None)
        current = stack.currentWidget() if stack is not None else page
        page_current = current is page and page.isVisible() and circle.isVisibleTo(page)
        fraction = visible_fraction(circle_rect, view_rect) if page_current else 0.0
        return page_current, fraction, circle_rect, view_rect

    def _badge_rect(self) -> QRectF:
        spot = self._badge.mapTo(self._window, QPoint(0, 0))
        return QRectF(spot.x(), spot.y(), self._badge.width(), self._badge.height())

    # ── решение ──────────────────────────────────────────────

    def schedule(self) -> None:
        """Сгустить пачку событий (прокрутка, раскладка) в одну проверку."""
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(0, self._run_scheduled)

    def _run_scheduled(self) -> None:
        self._pending = False
        if not sip.isdeleted(self._badge):
            self._evaluate(animate=True)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt override)
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show, QEvent.Type.Hide):
            self.schedule()
        return False

    def is_badge_wanted(self) -> bool:
        return self._shown

    def _evaluate(self, *, animate: bool) -> None:
        page_current, fraction, circle, _view = self._geometry()
        if not self._primed:
            animate = False
            if circle is not None and self._window.isVisible():
                self._primed = True
        wanted = badge_wanted(fraction, page_current=page_current, shown_now=self._shown)
        if wanted == self._shown and (animate or self._spring.settled()):
            return
        self._shown = wanted
        target = 1.0 if wanted else 0.0
        window = self._window
        mode = popup_motion_mode() if animate else "none"
        if not window.isVisible() or window.isMinimized():
            mode = "none"
        if mode == "none":
            self._finish(target)
            return
        self._mode = mode
        if mode == "spring" and not self._timer.isActive():
            self._take_snapshots()
        self._badge.set_presence(0.0 if mode == "spring" else self._spring.value)
        self._spring.retarget(target)
        if not self._timer.isActive():
            self._last_tick = time.monotonic()
            self._timer.start()
        self._tick(advance=False)

    def _take_snapshots(self) -> None:
        _page, circle = self._locate_circle(self._window)
        self._ghost.circle = circle.grab() if circle is not None and not sip.isdeleted(circle) else QPixmap()
        self._ghost.badge = self._badge.grab_full()

    # ── движение ─────────────────────────────────────────────

    def _tick(self, advance: bool = True) -> None:
        if sip.isdeleted(self._badge):
            self._timer.stop()
            return
        now = time.monotonic()
        if advance:
            self._spring.step(min(MAX_FRAME_DT_S, now - self._last_tick))
        self._last_tick = now
        progress = max(0.0, min(1.0, self._spring.value))
        if self._spring.settled():
            self._finish(self._spring.target)
            return
        if self._mode == "fade":
            self._badge.set_presence(progress)
            return
        _current, _fraction, circle_rect, view_rect = self._geometry()
        end = self._badge_rect()
        start = circle_rect if circle_rect is not None else end
        top = view_rect.top() if view_rect is not None else 0.0
        ghost = self._ghost
        if ghost.geometry() != self._window.rect():
            ghost.setGeometry(self._window.rect())
        if ghost.isHidden():
            ghost.show()
        ghost.raise_()
        ghost.set_frame(lerp_rect(start, end, progress), clip_top(top, progress), crossfade(progress))

    def _finish(self, target: float) -> None:
        self._timer.stop()
        self._spring.jump(target)
        self._ghost.hide()
        self._ghost.circle = QPixmap()
        self._ghost.badge = QPixmap()
        self._badge.set_presence(target)
