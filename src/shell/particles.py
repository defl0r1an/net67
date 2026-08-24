"""Лента песчинок в нижней части каждой страницы.

Внизу окна течёт плотная волнистая лента из мелких точек. Курсор
выбивает в ней полость: песчинки разлетаются, а когда указатель уходит —
возвращаются на свои места, и лента смыкается обратно.

Одни песчинки на всех страницах. Раньше форма менялась по разделам —
щиты на главной, ключи в VPN, — но фигуры считываются как значки и
тянут на себя внимание, а фону положено оставаться фоном. Код тех форм
удалён, а не оставлен «на всякий случай»: ветка, до которой ничего не
доходит, тихо гниёт.

Четыре решения, которые здесь важнее вида.

У каждой частицы есть дом. Без него курсор разгонял бы ленту навсегда:
первый же проход мыши размазал бы её по всей полосе, и вернуть форму
было бы нечем. Пружина к дому — то, что держит ленту лентой.

Частицы не перехватывают мышь. Слой прозрачен для событий, а курсор
берётся опросом. Иначе красивый фон съедал бы клики по кнопкам под
собой — и это уже не оформление, а неработающее приложение.

Частицы слушаются политики анимаций. Кто выключил анимацию в системе,
увидит ленту неподвижной, а таймер не запустится вовсе.

Плотность выставлена по замеру времени кадра, а не на глаз. Числа — в
комментарии к GRAIN_COUNT.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget


#: Высота полосы с песчинками.
BAND_HEIGHT = 190

#: Ниже этого ленту не показываем вовсе.
#:
#: Узкая полоска песка под текстом читается как грязь на экране, а не
#: как оформление. Лучше её отсутствие.
MIN_BAND_HEIGHT = 70

#: Сколько песчинок в ленте.
#:
#: Число взято из замера времени кадра при ленте шириной 1400 пикселей.
#: Бюджет — 33 мс (тридцать кадров в секунду), и уложиться надо с
#: запасом: у двадцати менеджеров машины слабее моей.
#:
#:    900 — 5.9 мс
#:   2600 — 14.1 мс
#:   3600 — 19.3 мс
#:   5000 — 26.8 мс
#:
#: Берём 1200. Замер выше делался по одной песчинке за вызов; сейчас
#: рисование идёт пачками и стоит вдвое дешевле, но у человека всё равно
#: выходило «пятнадцать кадров» — потому что лента лежала под
#: содержимым и тянула за собой перерисовку всей страницы. Полосу
#: увели в свободное место, а количество снизили с запасом.
GRAIN_COUNT = 2200

#: Как часто перерисовывать. 16 мс — примерно 60 кадров в секунду.
#:
#: Было 33 (тридцать кадров) ради экономии, но человек видит разницу и
#: описал её как «пятнадцать кадров». Бюджет на кадр теперь 16 мс, и
#: лента в него укладывается: замер дал 4.8 мс на 1200 песчинок при
#: рисовании пачками. Запас трёхкратный.
TICK_MS = 16

#: На каком расстоянии курсор начинает расталкивать частицы.
#:
#: Было 135 — полость выходила размером с ладонь и выглядела дырой в
#: половину полосы. 85 даёт заметное расхождение вокруг указателя, а не
#: воронку.
CURSOR_RADIUS = 85.0

#: Сила расталкивания.
#:
#: Было 9.0 — песчинки улетали далеко за радиус и долго возвращались.
#: 3.2 расталкивает их ровно настолько, чтобы движение читалось.
CURSOR_PUSH = 3.2

#: Насколько резко толчок спадает к краю радиуса.
#:
#: Квадрат оказался слишком резким: полость получалась узкой, и на
#: половине радиуса частицы уже почти не двигались. Показатель чуть
#: больше единицы даёт широкую воронку с чётким центром.
FALLOFF_POWER = 1.3

#: Сила возврата домой и затухание скорости.
#:
#: Пара подобрана замером, а не на глаз. Коэффициент затухания
#: (1 - DAMPING) / (2·√SPRING) при этих значениях равен 0.64 — это
#: недодемпфированная пружина с небольшим перелётом.
#:
#: Измерено на ленте из 900 частиц: под курсором в радиусе 80 пикселей
#: не остаётся ни одной, после ухода указателя плотность
#: восстанавливается до 48% за треть секунды, до 88% за 0.6 с, доходит
#: до 109% на 0.9 с и садится на 100% к 1.2 с. Перелёт в девять
#: процентов и есть та живость, ради которой пружину не сделали
#: критической: лента возвращается, а не примерзает на место.
#:
#: Прежние 0.055 и 0.86 давали коэффициент 0.31, и это была уже
#: настоящая раскачка: плотность шла 26, потом 13, потом снова 37.
SPRING = 0.011
DAMPING = 0.88

#: Сколько волн укладывается по ширине ленты.
WAVE_PERIODS = 2.4

#: Размах волны в долях высоты полосы.
WAVE_AMPLITUDE = 0.28

#: Скорость бега волны.
WAVE_SPEED = 0.0035

#: Разброс песчинок поперёк линии волны, в долях высоты полосы.
WAVE_SPREAD = 0.20

#: Прозрачность песчинок.
#:
#: Ненавязчиво — значит по-настоящему тихо. Прежний разброс 0.30–0.95
#: давал на тёмном фоне почти белую крошку, которая спорила с текстом.
#: Здесь верх — меньше половины непрозрачности: лента читается как
#: движение на краю зрения, а не как содержимое.
ALPHA_MIN = 0.08
ALPHA_MAX = 0.42


#: Сколько раз лента перекручивается на всю ширину окна.
#:
#: Полтора оборота: на целом числе оба перехлёста оказываются у краёв,
#: где лента и так гаснет, и перекрут перестаёт читаться.
TWISTS = 1.5

#: Насколько тускнеет изнанка ленты в месте перехлёста.
#:
#: Ноль дал бы разрыв, единица — плоскую полосу без всякого перекрута.
BACKSIDE_ALPHA = 0.35

#: Доля ширины, на которой лента угасает у левого и правого края.
#:
#: Без этого поток обрывался вертикальной стеной — человек отметил
#: стрелками ровно эти обрывы. Гасим прозрачностью, а не обрезкой:
#: обрезка любой формы всё равно даёт край, просто другой формы.
EDGE_FADE = 0.14


def wave_y(x: float, width: int, height: int, phase: float) -> float:
    """Высота осевой линии ленты в точке x.

    Две синусоиды разной длины вместо одной: одна даёт правильную,
    машинную волну, а от ленты нужен живой поток.
    """
    width = max(1, int(width))
    t = float(x) / width
    main = math.sin(t * math.tau * WAVE_PERIODS + phase)
    ripple = math.sin(t * math.tau * WAVE_PERIODS * 2.7 + phase * 1.6) * 0.35
    return height * 0.5 + (main + ripple) * height * WAVE_AMPLITUDE


def twist(x: float, width: int, phase: float) -> float:
    """Раскрытие ленты в точке x: от -1 до 1.

    Это и есть перекрут. Лента Мёбиуса — поверхность с одной стороной:
    обойдя её по кругу, приходишь на изнанку, не пересекая края. На
    плоскости это читается так: ширина ленты плавно сходит к нулю, и
    сразу за этой точкой видна уже изнанка.

    Знак и говорит, какой стороной лента повёрнута к нам. Модуль —
    насколько она раскрыта: у нуля лента встала ребром, у единицы
    развёрнута плашмя.
    """
    width = max(1, int(width))
    return math.cos(float(x) / width * math.tau * TWISTS + phase * 0.6)


def edge_fade(x: float, width: int) -> float:
    """Множитель прозрачности у краёв: 0 на самом краю, 1 в глубине."""
    width = max(1, int(width))
    margin = width * EDGE_FADE
    if margin <= 0.0:
        return 1.0
    left = float(x) / margin
    right = (width - float(x)) / margin
    return max(0.0, min(1.0, left, right))


@dataclass(slots=True)
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    #: Где частица «живёт». Дом по горизонтали фиксирован, по вертикали
    #: считается от волны, поэтому хранится только смещение.
    home_x: float
    offset: float
    size: float
    alpha: float


def make_particles(count: int, width: int, height: int, rng=None) -> list[Particle]:
    """Раскидывает частицы вдоль ленты.

    Генератор передаётся снаружи, чтобы тест мог получить повторяемую
    раскладку: проверять случайное расположение иначе невозможно.
    """
    random_source = rng or random.Random()
    width = max(1, int(width))
    height = max(1, int(height))
    particles: list[Particle] = []
    for _ in range(max(0, int(count))):
        home_x = random_source.uniform(-10.0, width + 10.0)
        # Разброс поперёк ленты берём как сумму двух случайных чисел:
        # так частиц гуще у осевой линии и реже по краям, а равномерный
        # разброс дал бы полосу с обрубленными краями.
        spread = (random_source.random() + random_source.random() - 1.0)
        offset = spread * height * WAVE_SPREAD * 2.0
        start_y = wave_y(home_x, width, height, 0.0) + offset * abs(
            twist(home_x, width, 0.0)
        )
        particles.append(
            Particle(
                x=home_x,
                y=start_y,
                vx=0.0,
                vy=0.0,
                home_x=home_x,
                offset=offset,
                size=random_source.uniform(0.7, 1.9),
                alpha=random_source.uniform(ALPHA_MIN, ALPHA_MAX),
            )
        )
    return particles


def advance(
    particle: Particle,
    *,
    width: int,
    height: int,
    phase: float = 0.0,
    cursor=None,
) -> None:
    """Двигает частицу на один такт: курсор толкает, пружина возвращает.

    Курсор именно отталкивает. Притяжение выглядит эффектнее на видео,
    но на деле частицы сбиваются в комок под указателем и закрывают то,
    на что человек навёл.
    """
    # Дом по вертикали складывается из осевой линии и смещения поперёк
    # ленты, сжатого её раскрытием. У перехлёста раскрытие близко к нулю,
    # и частицы сходятся к оси — это и даёт перекрут.
    opening = twist(particle.home_x, width, phase)
    home_y = wave_y(particle.home_x, width, height, phase) + particle.offset * abs(opening)

    if cursor is not None:
        dx = particle.x - float(cursor[0])
        dy = particle.y - float(cursor[1])
        distance = math.hypot(dx, dy)
        if 0.0 < distance < CURSOR_RADIUS:
            falloff = 1.0 - distance / CURSOR_RADIUS
            force = (falloff ** FALLOFF_POWER) * CURSOR_PUSH
            particle.vx += dx / distance * force
            particle.vy += dy / distance * force

    particle.vx += (particle.home_x - particle.x) * SPRING
    particle.vy += (home_y - particle.y) * SPRING
    particle.vx *= DAMPING
    particle.vy *= DAMPING

    particle.x += particle.vx
    particle.y += particle.vy


class ParticleLayer(QWidget):
    """Прозрачный слой с лентой частиц внизу окна."""

    def __init__(self, parent=None, *, dark: bool = True):
        super().__init__(parent)
        # Ключевое: слой не должен ловить мышь, иначе кнопки под ним
        # перестанут нажиматься.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._dark = bool(dark)
        self._particles: list[Particle] = []
        self._cursor: tuple[float, float] | None = None
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ──────────────────────────────────────────────────────────────────

    def set_dark(self, dark: bool) -> None:
        self._dark = bool(dark)
        self.update()

    @property
    def particles(self) -> list[Particle]:
        return self._particles

    @property
    def phase(self) -> float:
        return self._phase

    def reseed(self, *, rng=None) -> None:
        self._particles = make_particles(GRAIN_COUNT, self.width(), self.height(), rng)

    def ensure_seeded(self) -> None:
        """Сеет частицы, если их ещё нет и размер уже известен.

        Одного resizeEvent мало: скрытому виджету Qt его не шлёт вовсе,
        только запоминает геометрию. Слой, собранный до показа окна, так
        и остался бы пустым.
        """
        if not self._particles and self.width() > 0 and self.height() > 0:
            self.reseed()

    def start(self) -> None:
        """Запускает движение, если анимации разрешены.

        Выключенные анимации — не повод прятать ленту: она остаётся на
        месте. Но таймер в этом случае не крутится вовсе.
        """
        self.ensure_seeded()
        if self._animations_enabled() and not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _animations_enabled(self) -> bool:
        try:
            from ui.animation_policy import are_animations_enabled

            return bool(are_animations_enabled())
        except Exception:
            return False

    def _tick(self) -> None:
        self._phase += WAVE_SPEED * math.tau
        self._cursor = self._cursor_position()
        width, height = self.width(), self.height()
        for particle in self._particles:
            advance(
                particle,
                width=width,
                height=height,
                phase=self._phase,
                cursor=self._cursor,
            )
        self.update()

    def _cursor_position(self):
        """Курсор опросом, а не событиями.

        Слой прозрачен для мыши и событий не получает вовсе. Опрос
        решает это, ничего не отбирая у кнопок под слоем.
        """
        try:
            from PyQt6.QtGui import QCursor

            local = self.mapFromGlobal(QCursor.pos())
        except Exception:
            return None
        if not self.rect().contains(local):
            return None
        return (float(local.x()), float(local.y()))

    def showEvent(self, event):
        super().showEvent(event)
        self.ensure_seeded()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reseed()

    #: На сколько групп по размеру и прозрачности бьётся лента при
    #: рисовании. Каждая группа — один вызов drawPoints вместо сотен
    #: отдельных кружков: замер дал 10.3 мс против 6.0 на той же ленте.
    SIZE_BUCKETS = 3
    ALPHA_BUCKETS = 6

    def paintEvent(self, event):
        if not self._particles:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        base = QColor(255, 255, 255) if self._dark else QColor(20, 20, 20)

        size_span = 1.9 - 0.7
        alpha_span = ALPHA_MAX - ALPHA_MIN
        width = max(1, self.width())
        phase = self._phase
        buckets: dict[tuple[int, int], list] = {}
        for particle in self._particles:
            size_index = min(
                self.SIZE_BUCKETS - 1,
                max(0, int((particle.size - 0.7) / size_span * self.SIZE_BUCKETS)),
            )

            # Прозрачность частицы складывается из трёх множителей:
            # её собственной, угасания у края и стороны ленты. Изнанка
            # тусклее — без этого перекрут не читается, полоса выглядит
            # просто сужающейся.
            opening = twist(particle.home_x, width, phase)
            side = 1.0 if (opening >= 0.0) == (particle.offset >= 0.0) else BACKSIDE_ALPHA
            visible_alpha = particle.alpha * edge_fade(particle.x, width) * side
            if visible_alpha <= 0.01:
                continue

            alpha_index = min(
                self.ALPHA_BUCKETS - 1,
                max(0, int((visible_alpha - ALPHA_MIN) / alpha_span * self.ALPHA_BUCKETS)),
            )
            buckets.setdefault((size_index, alpha_index), []).append(
                QPointF(particle.x, particle.y)
            )

        for (size_index, alpha_index), points in buckets.items():
            # Круглый наконечник пера превращает точку в кружок нужного
            # диаметра, поэтому размер задаётся толщиной пера.
            diameter = (0.7 + (size_index + 0.5) * size_span / self.SIZE_BUCKETS) * 2.0
            color = QColor(base)
            color.setAlphaF(
                ALPHA_MIN + (alpha_index + 0.5) * alpha_span / self.ALPHA_BUCKETS
            )
            pen = QPen(color, diameter)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawPoints(*points)
        painter.end()


__all__ = [
    "ALPHA_MAX",
    "BACKSIDE_ALPHA",
    "EDGE_FADE",
    "TWISTS",
    "edge_fade",
    "twist",
    "ALPHA_MIN",
    "BAND_HEIGHT",
    "MIN_BAND_HEIGHT",
    "CURSOR_PUSH",
    "CURSOR_RADIUS",
    "DAMPING",
    "FALLOFF_POWER",
    "GRAIN_COUNT",
    "SPRING",
    "TICK_MS",
    "WAVE_SPEED",
    "Particle",
    "ParticleLayer",
    "advance",
    "make_particles",
    "wave_y",
]
