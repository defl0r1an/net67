"""Лента песчинок: волна внизу каждой страницы, полость под курсором.

Внизу течёт плотная волнистая лента из мелких точек. Курсор выбивает в
ней полость, а после ухода указателя лента смыкается. Песчинки одни и
те же на всех страницах: фигуры считывались как значки и тянули на себя
внимание, а фону положено оставаться фоном.

Числа в тестах не выдуманы: они получены замером и записаны в
particles.py рядом с коэффициентами. Тесты стерегут именно
их, потому что «выглядит красиво» проверить нечем, а «под курсором не
осталось ни одной частицы» — вполне.
"""

from __future__ import annotations

import inspect
import math
import os
import random
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

WIDTH, HEIGHT = 1180, 250
CURSOR = (560.0, 120.0)


def _settle(cursor, ticks: int, particles=None):
    """Прогоняет ленту заданное число тактов."""
    import shell.particles as particles_module

    if particles is None:
        particles = particles_module.make_particles(
            particles_module.GRAIN_COUNT, WIDTH, HEIGHT, random.Random(5)
        )
    phase = 0.0
    for _ in range(ticks):
        phase += particles_module.WAVE_SPEED * math.tau
        for particle in particles:
            particles_module.advance(
                particle, width=WIDTH, height=HEIGHT, phase=phase, cursor=cursor
            )
    return particles


def _near(particles, radius: float = 80.0) -> int:
    return sum(
        1
        for particle in particles
        if math.hypot(particle.x - CURSOR[0], particle.y - CURSOR[1]) < radius
    )


class QuietnessTests(unittest.TestCase):
    def test_grains_stay_in_the_background(self) -> None:
        """Ненавязчиво — значит по-настоящему тихо.

        Прежний верх 0.95 давал на тёмном фоне почти белую крошку,
        которая спорила с текстом.
        """
        from shell.particles import ALPHA_MAX, ALPHA_MIN

        self.assertLess(ALPHA_MAX, 0.5, "лента спорит с содержимым страницы")
        self.assertGreater(ALPHA_MIN, 0.0, "невидимые песчинки незачем считать")

    def test_no_shape_machinery_is_left_behind(self) -> None:
        """Ветка, до которой ничего не доходит, тихо гниёт."""
        import shell.particles as particles_module

        for gone in ("build_shape_path", "shape_for_page", "PAGE_SHAPES", "SHAPE_COUNT"):
            with self.subTest(name=gone):
                self.assertFalse(hasattr(particles_module, gone))


class RibbonTests(unittest.TestCase):
    def test_particles_gather_along_a_wave(self) -> None:
        """Лента, а не равномерная россыпь по всей полосе."""
        from shell.particles import GRAIN_COUNT, make_particles, wave_y

        particles = make_particles(GRAIN_COUNT, WIDTH, HEIGHT, random.Random(5))

        far = [
            particle
            for particle in particles
            if abs(particle.y - wave_y(particle.x, WIDTH, HEIGHT, 0.0)) > HEIGHT * 0.4
        ]

        self.assertEqual(far, [], "частицы разбрелись далеко от линии волны")

    def test_wave_actually_waves(self) -> None:
        from shell.particles import wave_y

        heights = [wave_y(x, WIDTH, HEIGHT, 0.0) for x in range(0, WIDTH, 40)]

        self.assertGreater(max(heights) - min(heights), HEIGHT * 0.2)

    def test_wave_travels_over_time(self) -> None:
        from shell.particles import wave_y

        before = wave_y(300.0, WIDTH, HEIGHT, 0.0)
        after = wave_y(300.0, WIDTH, HEIGHT, 1.0)

        self.assertNotAlmostEqual(before, after, places=3)


class CursorTests(unittest.TestCase):
    def test_cursor_dents_the_ribbon(self) -> None:
        """Вмятина под указателем, а не кратер.

        Сначала радиус был 135 при силе 9: полость выходила размером с
        ладонь, и песчинки улетали далеко за неё. Теперь чистый круг
        около сорока пикселей, а на восьмидесяти лента уже целая.
        """
        calm = _settle(None, 90)
        hot = _settle(CURSOR, 90)

        self.assertGreater(_near(calm, 40.0), 10, "лента должна быть плотной")
        self.assertEqual(_near(hot, 40.0), 0, "полость под курсором не продавилась")

    def test_ribbon_stays_whole_a_bit_further_out(self) -> None:
        """Иначе песчинки «слишком далеко разъезжаются от курсора»."""
        calm = _settle(None, 90)
        hot = _settle(CURSOR, 90)

        self.assertGreaterEqual(_near(hot, 120.0), _near(calm, 120.0) * 0.9)

    def test_ribbon_closes_after_the_cursor_leaves(self) -> None:
        """Иначе след от мыши висел бы на экране до перезапуска."""
        hot = _settle(CURSOR, 90)
        calm = _settle(None, 90)

        _settle(None, 40, hot)
        _settle(None, 40, calm)

        self.assertGreaterEqual(_near(hot), _near(calm) * 0.8)

    def test_push_is_stronger_up_close(self) -> None:
        from shell.particles import Particle, advance

        def probe(distance: float) -> float:
            particle = Particle(
                x=CURSOR[0] + distance,
                y=CURSOR[1],
                vx=0.0,
                vy=0.0,
                home_x=CURSOR[0] + distance,
                offset=0.0,
                size=1.5,
                alpha=0.5,
            )
            advance(particle, width=WIDTH, height=HEIGHT, cursor=CURSOR)
            return particle.vx

        self.assertGreater(probe(20.0), probe(100.0))

    def test_far_cursor_leaves_the_ribbon_alone(self) -> None:
        from shell.particles import Particle, advance

        particle = Particle(
            x=100.0, y=120.0, vx=0.0, vy=0.0, home_x=100.0,
            offset=0.0, size=1.5, alpha=0.5,
        )
        advance(particle, width=WIDTH, height=HEIGHT, cursor=(1100.0, 120.0))

        self.assertLess(abs(particle.vx), 0.01)

    def test_particles_are_pushed_away_not_pulled_in(self) -> None:
        """Притяжение сбивало бы их в комок ровно под указателем."""
        from shell.particles import Particle, advance

        particle = Particle(
            x=CURSOR[0] + 30.0, y=CURSOR[1], vx=0.0, vy=0.0,
            home_x=CURSOR[0] + 30.0, offset=0.0, size=1.5, alpha=0.5,
        )
        advance(particle, width=WIDTH, height=HEIGHT, cursor=CURSOR)

        self.assertGreater(particle.vx, 0.0)


class DampingTests(unittest.TestCase):
    def test_spring_is_underdamped_but_not_wobbly(self) -> None:
        """Коэффициент затухания: раскачка ниже 0.4, мёртвость выше 1.0.

        При прежних 0.055 и 0.86 он был 0.31, и лента качалась: плотность
        шла 26, потом 13, потом снова 37.
        """
        from shell.particles import DAMPING, SPRING

        ratio = (1.0 - DAMPING) / (2.0 * math.sqrt(SPRING))

        self.assertGreater(ratio, 0.4, "лента будет качаться")
        self.assertLess(ratio, 1.0, "лента примёрзнет и вернётся рывком")

    def test_recovery_takes_about_a_second(self) -> None:
        """Мгновенно — рывок, долго — след от мыши висит и мешает."""
        from shell.particles import TICK_MS

        hot = _settle(CURSOR, 90)
        calm = _settle(None, 90)
        ticks = int(1200 / TICK_MS)

        _settle(None, ticks, hot)
        _settle(None, ticks, calm)

        self.assertGreaterEqual(_near(hot), _near(calm) * 0.9)


class BudgetTests(unittest.TestCase):
    def test_sixty_frames_a_second(self) -> None:
        """Тридцать кадров человек описал как «пятнадцать»: мало.

        Замер: 1200 песчинок — 4.8 мс на кадр при рисовании пачками.
        В бюджет 16 мс укладывается с трёхкратным запасом.
        """
        from shell.particles import TICK_MS

        self.assertLessEqual(TICK_MS, 17)
        self.assertGreaterEqual(TICK_MS, 8)

    def test_density_stays_inside_the_measured_budget(self) -> None:
        """Замер после перехода на рисование пачками: 1200 песчинок —
        4.8 мс на кадр из 33 (1.7 физика + 3.1 рисование).

        Прежние 2600 давали 14 мс и, что важнее, лежали под содержимым:
        каждый кадр тянул за собой перерисовку всей страницы, и человек
        видел «пятнадцать кадров» на всём интерфейсе.
        """
        from shell.particles import GRAIN_COUNT

        # Порог поднят с 2000 до 2400: попросили «более плотный поток».
        # Замер на 2200 песчинках в ленте 1280x190 дал 10.4 мс на кадр
        # (2.8 физика + 7.5 рисование) при бюджете 16 мс на 60 кадрах.
        self.assertLessEqual(GRAIN_COUNT, 2400)
        self.assertGreaterEqual(GRAIN_COUNT, 800, "лента должна быть плотной")


class SafetyTests(unittest.TestCase):
    def test_layer_does_not_steal_mouse(self) -> None:
        """Иначе фон съедает клики по кнопкам под собой."""
        from shell.particles import ParticleLayer

        self.assertIn(
            "WA_TransparentForMouseEvents", inspect.getsource(ParticleLayer.__init__)
        )

    def test_cursor_is_polled_because_events_never_arrive(self) -> None:
        from shell.particles import ParticleLayer

        self.assertIn("QCursor.pos()", inspect.getsource(ParticleLayer._cursor_position))

    def test_animation_policy_is_respected(self) -> None:
        """Кто выключил анимации, не должен получить крутящийся таймер."""
        from shell.particles import ParticleLayer

        self.assertIn("_animations_enabled()", inspect.getsource(ParticleLayer.start))


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class LayerTests(unittest.TestCase):
    def _layer(self):
        from shell.particles import ParticleLayer

        layer = ParticleLayer()
        self.addCleanup(layer.deleteLater)
        layer.resize(WIDTH, HEIGHT)
        return layer

    def test_hidden_layer_is_not_left_empty(self) -> None:
        """Qt не шлёт resize скрытым виджетам — слой оставался пустым."""
        layer = self._layer()

        self.assertFalse(layer.particles, "resize скрытому виджету всё-таки дошёл")

        layer.ensure_seeded()

        self.assertTrue(layer.particles)

    def test_timer_stays_off_when_animations_are_disabled(self) -> None:
        layer = self._layer()
        layer._animations_enabled = lambda: False

        layer.start()

        self.assertFalse(layer._timer.isActive())
        self.assertTrue(layer.particles, "лента должна остаться на месте, а не исчезнуть")

    def test_timer_runs_when_animations_are_on(self) -> None:
        layer = self._layer()
        layer._animations_enabled = lambda: True

        layer.start()
        self.addCleanup(layer.stop)

        self.assertTrue(layer._timer.isActive())


if __name__ == "__main__":
    unittest.main()
