"""Фоновое свечение за содержимым.

Два больших размытых пятна, медленно дрейфующих в разные стороны. Приём
чужой — так сделан фон в нескольких оформлениях, которые человеку
понравились, — но здесь он написан заново и на своих числах: чужой код
в Qt всё равно не вставляется, там CSS для Electron.

Смысл приёма в том, что ровная заливка на большой площади выглядит
мёртвой, а еле заметная неоднородность даёт глубину, которую глаз
замечает, не осознавая. Поэтому прозрачность здесь мизерная: пятно,
которое видно как пятно, — это уже брак.

## Почему без настоящего размытия

`QGraphicsBlurEffect` с радиусом в сотню пикселей на площади в полтора
мегапикселя стоит десятки миллисекунд на кадр. Радиальный градиент даёт
ту же мягкую границу бесплатно: он и есть размытая окружность, только
посчитанная сразу, а не через свёртку.

## Почему четыре кадра в секунду

Пятна проходят полный путь за полминуты. При таком темпе смещение между
соседними кадрами при 60 кадрах в секунду — доли пикселя, то есть работа
вхолостую. Четыре кадра дают то же движение и в пятнадцать раз дешевле,
а это важно: слой лежит под содержимым, и каждая его перерисовка тянет
за собой перерисовку всего, что сверху. Ровно на этом обжигались
песчинки, из-за них весь интерфейс шёл «пятнадцатью кадрами».
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QTimer, Qt
from PyQt6.QtGui import QColor, QPainter, QRadialGradient
from PyQt6.QtWidgets import QWidget


#: Такт перерисовки. Четыре кадра в секунду, см. описание модуля.
TICK_MS = 250

#: Диаметр пятна в долях от меньшей стороны окна.
#:
#: Больше единицы намеренно: пятно должно выходить за края, иначе видно
#: его границу и вся затея превращается в «круг на фоне».
BLOB_SCALE = 1.35

#: Наибольшая прозрачность в центре пятна.
#:
#: Ноль целых пять сотых — это на грани различимости, и так и задумано.
#: При 0.12 пятна уже читаются как пятна.
BLOB_ALPHA = 0.055

#: За сколько секунд пятно проходит свой путь туда и обратно.
#: Разные периоды у двух пятен намеренно: с одинаковыми они двигались бы
#: синхронно, и это читалось бы как дыхание, а не как дрейф.
PERIOD_A = 26.0
PERIOD_B = 32.0

#: Насколько пятно отходит от своего угла, в долях размера окна.
DRIFT = 0.12


def blob_center(
    phase: float,
    *,
    width: int,
    height: int,
    second: bool = False,
) -> tuple[float, float]:
    """Центр пятна в текущий момент.

    Первое живёт у правого верхнего угла, второе у левого нижнего — по
    диагонали, чтобы неоднородность прошла через всё окно. Оба смещаются
    по синусу, но по разным осям, поэтому их пути не повторяют друг
    друга.
    """
    width = max(1, int(width))
    height = max(1, int(height))
    drift_x = width * DRIFT
    drift_y = height * DRIFT

    if second:
        angle = phase * math.tau / PERIOD_B
        return (
            width * 0.08 + math.sin(angle) * drift_x,
            height * 1.02 - math.cos(angle) * drift_y,
        )

    angle = phase * math.tau / PERIOD_A
    return (
        width * 0.92 - math.cos(angle) * drift_x,
        height * -0.02 + math.sin(angle) * drift_y,
    )


class AmbientLayer(QWidget):
    """Слой свечения. Кладётся под содержимое и не ловит мышь."""

    def __init__(self, parent=None, *, dark: bool = True):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._dark = bool(dark)
        self._phase = 0.0
        #: Готовый кадр пятен и приметы, при которых он ещё годится.
        self._cache = None
        self._cache_key = None
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ── состояние ─────────────────────────────────────────────────────

    def set_dark(self, dark: bool) -> None:
        self._dark = bool(dark)
        self.update()

    @property
    def phase(self) -> float:
        return self._phase

    def start(self) -> None:
        if not self._timer.isActive() and self._animations_enabled():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    @staticmethod
    def _animations_enabled() -> bool:
        try:
            from ui.animation_policy import are_animations_enabled

            return bool(are_animations_enabled())
        except Exception:
            return True

    def _tick(self) -> None:
        self._phase += TICK_MS / 1000.0
        self.update()

    # ── отрисовка ─────────────────────────────────────────────────────

    def showEvent(self, event):  # noqa: N802 (Qt override)
        super().showEvent(event)
        self.start()

    def hideEvent(self, event):  # noqa: N802 (Qt override)
        # Невидимый слой не должен будить окно четыре раза в секунду.
        self.stop()
        super().hideEvent(event)

    def _render_blobs(self, painter, width: int, height: int) -> None:
        """Рисует два пятна в переданный painter."""
        radius = min(width, height) * BLOB_SCALE
        # Свечение белое в тёмной теме и чёрное в светлой: свой цвет у
        # пятна означал бы цветной подтон, а палитра строго нейтральная.
        tint = QColor(255, 255, 255) if self._dark else QColor(0, 0, 0)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        for second in (False, True):
            x, y = blob_center(self._phase, width=width, height=height, second=second)
            gradient = QRadialGradient(QPointF(x, y), radius)
            centre = QColor(tint)
            centre.setAlphaF(BLOB_ALPHA if not second else BLOB_ALPHA * 0.8)
            edge = QColor(tint)
            edge.setAlphaF(0.0)
            gradient.setColorAt(0.0, centre)
            gradient.setColorAt(1.0, edge)
            painter.setBrush(gradient)
            painter.drawEllipse(QPointF(x, y), radius, radius)

    def _ensure_cache(self, width: int, height: int):
        """Готовый кадр пятен. Пересобирается только когда он устарел.

        Слой лежит под прозрачным содержимым, поэтому его перерисовывают
        не четыре раза в секунду, а на каждый кадр любой анимации: Qt
        обязан восстановить фон под тем, что движется. Два больших
        радиальных градиента при этом растеризуются заново.

        Замер на окне 1440×1000: 4.1 мс на кадр. При бюджете 16.7 мс это
        четверть кадра, отданная фону, который меняется за секунду на
        доли пикселя.

        Готовая картинка снимает почти всё: вместо растеризации —
        копирование. Пересобираем её при смене размера, темы и раз в
        такт таймера; между тактами кадр один и тот же, и глаз этого не
        видит — пятна ползут с периодом в полминуты.
        """
        from PyQt6.QtGui import QPixmap

        ratio = float(self.devicePixelRatioF())
        key = (width, height, self._dark, round(self._phase, 3), round(ratio, 2))
        if self._cache is not None and self._cache_key == key:
            return self._cache

        pixmap = QPixmap(int(width * ratio), int(height * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        self._render_blobs(painter, width, height)
        painter.end()

        self._cache = pixmap
        self._cache_key = key
        return pixmap

    def paintEvent(self, event):  # noqa: N802 (Qt override)
        width, height = self.width(), self.height()
        if width <= 0 or height <= 0:
            return

        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._ensure_cache(width, height))
        painter.end()


__all__ = [
    "BLOB_ALPHA",
    "BLOB_SCALE",
    "DRIFT",
    "PERIOD_A",
    "PERIOD_B",
    "TICK_MS",
    "AmbientLayer",
    "blob_center",
]
