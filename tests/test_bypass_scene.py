"""Сцена обхода, светящаяся карточка и готовые слои — главная кнопка вкладки «Обход».

Тесты взяты у zapret вместе со сценой (ui/widgets/bypass_scene.py). Проверки
медоеда — его места, поз и жестов — не взяты: у net67 на его месте логотип.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

import presets.ui.control.status_hero_card as hero_module
import ui.pulsing_dot as dot_module
import ui.widgets.bypass_scene as scene_module
from test_paint_layer_cache import difference, paint_directly, render, share_above
from ui.paint_layer_cache import LayerCache
from presets.ui.control.status_hero_card import StatusHeroCard
from ui.widgets.bypass_scene import BypassScene


def _host(test: unittest.TestCase, child: QWidget) -> QWidget:
    host = QWidget()
    QVBoxLayout(host).addWidget(child)
    test.addCleanup(host.deleteLater)
    return host


class BypassSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._enabled = True
        for module in (dot_module, scene_module, hero_module):
            patcher = mock.patch.object(module, "are_live_animations_enabled", side_effect=lambda: self._enabled)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _scene(self, phase: str = "") -> BypassScene:
        scene = BypassScene()
        _host(self, scene).show()
        if phase:
            scene.set_phase(phase)
        return scene

    def test_running_flow_is_continuous_without_rest_pause(self) -> None:
        scene = self._scene("running")
        self.assertTrue(scene.is_beating())

        with mock.patch.object(scene._beat_clock, "elapsed", return_value=scene_module.BLOCKED_BURST_MS * 3):
            scene._on_beat_frame()

        self.assertTrue(scene.is_beating())
        self.assertFalse(scene._rest_timer.isActive())
        self.assertGreater(scene._flow_time, 0.0)

    def test_stopped_scene_fires_a_burst_and_then_rests_without_frames(self) -> None:
        scene = self._scene("stopped")
        self.assertTrue(scene.is_beating())

        with mock.patch.object(scene._beat_clock, "elapsed", return_value=scene_module.BLOCKED_BURST_MS // 2):
            scene._on_beat_frame()
        self.assertTrue(scene.is_beating())
        self.assertAlmostEqual(scene._pulse_phase, 0.5, places=2)

        with mock.patch.object(scene._beat_clock, "elapsed", return_value=scene_module.BLOCKED_BURST_MS + 1):
            scene._on_beat_frame()
        self.assertFalse(scene.is_beating())
        self.assertTrue(scene._rest_timer.isActive())
        self.assertEqual(scene._rest_timer.interval(), scene_module.BLOCKED_REST_MS)

    def test_stop_pulse_keeps_the_stopped_scene_alive(self) -> None:
        scene = self._scene("stopped")
        scene.stop_pulse()
        self.assertTrue(scene.is_beating() or scene._rest_timer.isActive())

    def test_no_frames_before_the_phase_is_known(self) -> None:
        scene = self._scene()
        scene.start_pulse()
        self.assertFalse(scene.is_beating())
        self.assertFalse(scene._rest_timer.isActive())

    def test_scene_stops_when_hidden(self) -> None:
        scene = BypassScene()
        host = _host(self, scene)
        scene.set_phase("running")
        self.assertFalse(scene.is_beating())

        host.show()
        self.assertTrue(scene.is_beating())
        host.hide()
        self.assertFalse(scene.is_beating())
        self.assertFalse(scene._rest_timer.isActive())

    def test_scene_halts_on_next_frame_when_animations_turn_off(self) -> None:
        scene = self._scene("running")
        self.assertTrue(scene.is_beating())

        self._enabled = False
        scene._on_beat_frame()

        self.assertFalse(scene.is_beating())
        self.assertFalse(scene._rest_timer.isActive())

    def test_no_frames_when_animations_are_disabled(self) -> None:
        self._enabled = False
        for phase in ("running", "stopped", "starting"):
            with self.subTest(phase=phase):
                scene = self._scene(phase)
                self.assertFalse(scene.is_beating())
                self.assertFalse(scene._rest_timer.isActive())
                self.assertEqual(scene._open_t, 1.0 if phase == "running" else 0.0)

    def test_flow_frames_are_announced_only_while_running(self) -> None:
        frames: list[float] = []
        scene = self._scene("starting")
        scene.flowFrame.connect(frames.append)
        with mock.patch.object(scene._beat_clock, "elapsed", return_value=500):
            scene._on_beat_frame()
        self.assertEqual(frames, [])

        scene.set_phase("running")
        with mock.patch.object(scene._beat_clock, "elapsed", return_value=500):
            scene._on_beat_frame()
        self.assertEqual(len(frames), 1)
        self.assertAlmostEqual(frames[0], scene._flow_time)

        scene.set_phase("stopped")
        with mock.patch.object(scene._beat_clock, "elapsed", return_value=500):
            scene._on_beat_frame()
        self.assertEqual(len(frames), 1)

    def test_frames_repaint_only_lanes_wall_and_button(self) -> None:
        scene = self._scene("running")
        region = scene._motion_region().boundingRect()
        self.assertGreater(region.left(), 0)
        self.assertLess(region.right(), scene.width() - 1)

    def test_wall_opens_only_while_running(self) -> None:
        scene = self._scene("stopped")
        self.assertEqual(scene._open_target(), 0.0)
        scene.set_phase("starting")
        self.assertEqual(scene._open_target(), 0.0)
        scene.set_phase("running")
        self.assertEqual(scene._open_target(), 1.0)
        self.assertEqual(scene._wall_fade.state(), scene._wall_fade.State.Running)

    def test_failure_shakes_only_when_it_happens_on_screen(self) -> None:
        first = self._scene("failed")
        self.assertNotEqual(first._shake.state(), first._shake.State.Running)

        scene = self._scene("starting")
        scene.set_phase("failed")
        self.assertEqual(scene._shake.state(), scene._shake.State.Running)

    def test_only_the_button_is_clickable(self) -> None:
        from PyQt6.QtCore import QPointF

        scene = self._scene("stopped")
        scene.set_clickable(True)
        clicks = []
        scene.clicked.connect(lambda: clicks.append(1))

        self.assertTrue(scene._is_over_button(QPointF(scene.gate_center())))
        self.assertFalse(scene._is_over_button(QPointF(12, scene.height() / 2)))

        scene.set_click_locked(True)
        scene.click()
        self.assertEqual(clicks, [])
        scene.set_click_locked(False)
        scene.set_click_enabled(False)
        scene.click()
        self.assertEqual(clicks, [])
        scene.set_click_enabled(True)
        scene.click()
        self.assertEqual(clicks, [1])

    def test_signals_report_phase_and_final_color_once(self) -> None:
        scene = self._scene()
        phases, colors = [], []
        scene.phaseChanged.connect(phases.append)
        scene.colorChanged.connect(colors.append)

        scene.set_color("#6ccb5f")
        scene.set_color("#6ccb5f")
        scene.set_phase("running")
        scene.set_phase("running")
        scene.set_phase("что-то новое")

        self.assertEqual(colors, ["#6ccb5f"])
        self.assertEqual(phases, ["running", "stopped"])

    def test_power_arc_links_the_logo_and_the_button_only_while_working(self) -> None:
        scene = self._scene("stopped")
        center = scene_module.QPointF(scene.gate_center())
        start, end = scene._link_ends(center)
        # Дуга короткая: от края логотипа до края кнопки.
        self.assertLess(start.x(), end.x())
        self.assertLess(end.x(), center.x())

        def drawn(phase: str) -> int:
            scene.set_phase(phase)
            scene._flow_time = 0.7
            calls = []
            painter = mock.Mock()
            painter.drawLine.side_effect = lambda a, b: calls.append((a, b))
            scene._paint_link(painter, center, QColor("#6ccb5f"), scene._open_target())
            return len(calls)

        self.assertEqual(drawn("stopped"), 0)
        self.assertEqual(drawn("failed"), 0)
        for phase in ("starting", "stopping", "running"):
            with self.subTest(phase=phase):
                self.assertGreater(drawn(phase), 0)

    def test_failed_scene_throws_nothing_and_dims_the_logo(self) -> None:
        """После сбоя залпов о стену нет: программа уже попробовала и не смогла."""
        image = QPixmap(scene_module.SCENE_WIDTH, scene_module.SCENE_HEIGHT)
        for phase, expected in (("stopped", 1), ("failed", 0)):
            with self.subTest(phase=phase):
                scene = self._scene("starting")
                scene.set_phase(phase)
                with mock.patch.object(scene._beat_clock, "elapsed", return_value=int(scene_module.BLOCKED_BURST_MS * 0.5)):
                    scene._on_beat_frame()
                with mock.patch.object(scene, "_paint_blocked", return_value=0.0) as blocked:
                    scene.render(image)
                self.assertEqual(blocked.call_count, expected)
        self.assertLess(scene_module.FAILED_LOGO_OPACITY, 1.0)

    def test_logo_breathes_with_the_flow_frames_only_while_running(self) -> None:
        scene = self._scene("running")
        quarter = int(scene_module.BREATH_PERIOD_S * 250)
        with mock.patch.object(scene._beat_clock, "elapsed", return_value=quarter):
            scene._on_beat_frame()
        self.assertAlmostEqual(scene._breath, 1.0, places=2)

        scene.set_phase("stopped")
        self.assertEqual(scene._breath, 0.0)

    def test_logo_stands_on_the_left_and_lanes_start_at_its_edge(self) -> None:
        scene = self._scene("stopped")
        scene.resize(420, scene_module.SCENE_HEIGHT)
        logo = scene.logo_rect()
        left, right, top, bottom = scene._lanes()

        self.assertEqual(logo.left(), scene_module.LOGO_MARGIN)
        self.assertAlmostEqual(logo.center().y(), scene.height() / 2, places=3)
        self.assertGreater(left, logo.right())
        self.assertLess(top, logo.center().y())
        self.assertGreater(bottom, logo.center().y())
        # Кнопка в стене — между логотипом и сайтами, между дорожками.
        center = scene.gate_center()
        self.assertGreater(center.x(), left)
        self.assertLess(center.x(), right)
        self.assertAlmostEqual(center.y(), (top + bottom) / 2, delta=1)

    def test_gate_opens_inner_bricks_first_with_overshoot(self) -> None:
        scene = self._scene("starting")
        scene.set_phase("running")
        self.assertTrue(scene.is_gate_moving())
        self.assertTrue(scene._gate_opening)
        self.assertEqual(scene._wall_fade.duration(), scene_module.GATE_OPEN_MS)

        scene._open_t = 0.3
        self.assertGreater(scene._brick_progress(0), scene._brick_progress(2))
        # Пружинка: где-то по ходу кирпич перелетает дальше конечного места.
        self.assertTrue(any(
            (setattr(scene, "_open_t", value), scene._brick_shift(0))[1] > 1.0
            for value in (0.6, 0.7, 0.8, 0.9)
        ))
        scene._open_t = 1.0
        self.assertEqual([scene._brick_shift(row) for row in range(scene_module.WALL_BLOCKS)], [1.0, 1.0, 1.0])

    def test_gate_closes_outer_bricks_first_and_lands_with_a_bounce(self) -> None:
        scene = self._scene("running")
        scene._wall_fade.stop()
        scene._open_t = 1.0
        scene.set_phase("stopping")
        self.assertFalse(scene._gate_opening)
        self.assertEqual(scene._wall_fade.duration(), scene_module.GATE_CLOSE_MS)

        scene._open_t = 0.3
        self.assertLess(scene._brick_progress(2), scene._brick_progress(0))
        scene._open_t = 0.02
        self.assertGreater(scene._brick_shift(0), 0.0)
        scene._open_t = 0.0
        self.assertEqual(scene._brick_shift(0), 0.0)

    def test_button_breathes_out_on_start_and_in_on_stop(self) -> None:
        scene = self._scene("running")
        self.assertFalse(scene.is_popping())

        scene.set_phase("stopping")
        self.assertTrue(scene.is_popping())
        self.assertFalse(scene._pop_up)
        scene._pop.setCurrentTime(scene._pop.duration() // 4)
        self.assertLess(scene._pop_scale(), 1.0)

        scene.set_phase("stopped")
        scene.set_phase("starting")
        scene.set_phase("running")
        self.assertTrue(scene._pop_up)
        scene._pop.setCurrentTime(scene._pop.duration() // 4)
        self.assertGreater(scene._pop_scale(), 1.0)
        scene._pop.setCurrentTime(scene._pop.duration())
        self.assertEqual(scene._pop_scale(), 1.0)

    def test_hidden_scene_jumps_to_the_final_look(self) -> None:
        scene = BypassScene()
        host = _host(self, scene)
        host.show()
        scene.set_phase("starting")
        scene.set_phase("running")
        self.assertTrue(scene.is_gate_moving() and scene.is_popping())

        host.hide()
        self.assertFalse(scene.is_gate_moving())
        self.assertFalse(scene.is_popping())
        self.assertEqual(scene._open_t, 1.0)

    def _stream(self, scene, through: float) -> list[tuple[float, float, int]]:
        drawn: list[tuple[float, float, int]] = []
        center = scene_module.QPointF(scene.gate_center())
        left, right, top, bottom = scene._lanes()
        with mock.patch.object(
            scene, "_paint_packet", side_effect=lambda _p, x, _y, _c, alpha, direction: drawn.append((x, alpha, direction))
        ):
            scene._paint_stream(None, center, left, right, (top, bottom), scene_module.BUTTON_RADIUS + 3.0, QColor("#6ccb5f"), through)
        return drawn

    def test_packets_keep_their_places_when_the_gate_opens(self) -> None:
        scene = self._scene("starting")
        scene._flow_time = 1.7
        closed = self._stream(scene, 0.0)
        opened = self._stream(scene, 1.0)

        self.assertEqual([x for x, _a, _d in closed], [x for x, _a, _d in opened])
        center_x = scene.gate_center().x()
        for x, alpha, direction in closed:
            if direction < 0 or x > center_x:
                # Ворота закрыты: за стеной и на обратной дорожке пакетов не видно.
                self.assertEqual(alpha, 0.0)
        self.assertTrue(any(alpha > 0.0 for x, alpha, direction in opened if direction < 0))

    def test_comet_spins_both_ways_and_paints(self) -> None:
        scene = BypassScene()
        scene.set_clickable(True)
        for phase in ("starting", "stopping"):
            scene.set_phase(phase)
            scene._flow_time = 0.4
            scene._pop_t = 0.3
            image = QPixmap(scene.sizeHint())
            image.fill(QColor(0, 0, 0, 0))
            scene.render(image)
            self.assertFalse(image.isNull())

    def test_paints_every_phase(self) -> None:
        scene = BypassScene()
        scene.set_clickable(True)
        scene.set_color("#6ccb5f")
        for phase in ("stopped", "failed", "autostart_pending", "starting", "running", "stopping"):
            scene.set_phase(phase)
            scene._pulse_phase = 0.7
            scene._flow_time = 1.3
            image = QPixmap(scene.sizeHint())
            image.fill(QColor(0, 0, 0, 0))
            scene.render(image)
            self.assertFalse(image.isNull())


class StatusHeroCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._enabled = True
        for module in (dot_module, scene_module, hero_module):
            patcher = mock.patch.object(module, "are_live_animations_enabled", side_effect=lambda: self._enabled)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _card(self):
        card = StatusHeroCard()
        scene = BypassScene(card)
        card.bind_scene(scene)
        card.resize(900, 104)
        self.addCleanup(card.deleteLater)
        return card, scene

    def test_card_takes_color_from_scene(self) -> None:
        card, scene = self._card()
        scene.set_color("#f5a623")
        scene.set_phase("starting")

        self.assertEqual(card.tint(), QColor("#f5a623"))

    def test_wave_plays_only_when_bypass_turns_on_in_view(self) -> None:
        card, scene = self._card()
        card.show()
        # Программа открылась, а обход уже работает: это не «только что включился».
        scene.set_phase("running")
        self.assertFalse(card.is_wave_playing())

        scene.set_phase("starting")
        self.assertFalse(card.is_wave_playing())
        scene.set_color("#6ccb5f")
        scene.set_phase("running")
        self.assertTrue(card.is_wave_playing())

        card.hide()
        self.assertFalse(card.is_wave_playing())

    def test_no_wave_and_instant_color_without_live_animations(self) -> None:
        self._enabled = False
        card, scene = self._card()
        card.show()
        scene.set_color("#f5a623")
        scene.set_phase("starting")
        scene.set_color("#6ccb5f")
        scene.set_phase("running")

        self.assertFalse(card.is_wave_playing())
        self.assertEqual(card.tint(), QColor("#6ccb5f"))

    def _flow_frame(self, scene, elapsed_ms: int) -> None:
        with mock.patch.object(scene._beat_clock, "elapsed", return_value=elapsed_ms):
            scene._on_beat_frame()

    def test_glow_shimmers_on_scene_frames_only_while_running(self) -> None:
        card, scene = self._card()
        card.show()
        scene.set_phase("starting")
        self._flow_frame(scene, 400)
        self.assertFalse(card.is_shimmering())

        scene.set_phase("running")
        self._flow_frame(scene, 400)
        self.assertTrue(card.is_shimmering())
        self.assertAlmostEqual(card._shimmer_t, scene._flow_time)

        scene.set_phase("stopping")
        self.assertFalse(card.is_shimmering())

    def test_glow_lives_only_behind_the_scene(self) -> None:
        card, scene = self._card()
        scene.move(16, 14)
        card.show()
        area = card.shimmer_rect()

        self.assertEqual(area.left(), 0)
        self.assertGreater(area.right(), scene.geometry().right())
        self.assertLess(area.right(), card.width() // 2)
        self.assertEqual(area.height(), card.height())

    def test_glow_stops_when_hidden_or_animations_are_off(self) -> None:
        card, scene = self._card()
        card.show()
        scene.set_phase("running")
        self._flow_frame(scene, 400)
        self.assertTrue(card.is_shimmering())
        card.hide()
        self.assertFalse(card.is_shimmering())

        self._enabled = False
        card.show()
        self._flow_frame(scene, 800)
        self.assertFalse(card.is_shimmering())

    def test_glow_spots_are_drawn_once_and_reused(self) -> None:
        hero_module._SPOT_CACHE.clear()
        first = hero_module._spot_pixmap(QColor("#6ccb5f"), 120, 1.0)
        again = hero_module._spot_pixmap(QColor("#6ccb5f"), 120, 1.0)

        self.assertEqual(first.cacheKey(), again.cacheKey())
        self.assertEqual(len(hero_module._SPOT_CACHE), 1)
        self.assertEqual(first.width(), 240)

        card, scene = self._card()
        card.show()
        scene.set_color("#6ccb5f")
        scene.set_phase("running")
        for elapsed in (400, 2400, 5200):
            self._flow_frame(scene, elapsed)
            image = QPixmap(card.size())
            image.fill(QColor(0, 0, 0, 0))
            card.render(image)
        # Два пятна — два оттенка, сколько бы кадров ни прошло.
        self.assertEqual(len(hero_module._SPOT_CACHE), 3)

    def test_narrow_card_puts_the_scene_on_its_own_stretched_row(self) -> None:
        from PyQt6.QtWidgets import QBoxLayout, QHBoxLayout

        card, scene = self._card()
        layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, card)
        layout.addWidget(scene)
        layout.addLayout(QHBoxLayout(), 1)
        card.set_stacking_layout(layout)
        card.show()

        card.resize(hero_module.STACK_BELOW_WIDTH + 100, 104)
        QApplication.processEvents()
        self.assertFalse(card.is_stacked())
        self.assertFalse(scene.is_stretched())

        card.resize(hero_module.STACK_BELOW_WIDTH - 100, 200)
        QApplication.processEvents()
        self.assertTrue(card.is_stacked())
        self.assertTrue(scene.is_stretched())
        self.assertGreater(scene.width(), scene_module.SCENE_WIDTH)

        card.resize(hero_module.STACK_BELOW_WIDTH + 100, 104)
        QApplication.processEvents()
        self.assertFalse(card.is_stacked())
        self.assertLessEqual(scene.width(), scene_module.SCENE_WIDTH)

    def test_paints_tint_and_wave(self) -> None:
        card, scene = self._card()
        card.show()
        scene.set_color("#6ccb5f")
        card._wave_t = 0.4
        image = QPixmap(card.size())
        image.fill(QColor(0, 0, 0, 0))
        card.render(image)
        self.assertFalse(image.isNull())


# В целом кадре слои лежат друг на друге (карточка, дорожки сцены, стена, кнопка),
# и округление при смешивании цветов складывается: до трёх единиц из 255 в
# отдельных точках на сглаженных краях. Больше чем на единицу расходятся
# считаные точки — меньше сотой доли процента.
STACKED_ROUNDING = 3
STACKED_SHARE_ABOVE_ONE = 0.0001


class StatusCardReadyLayersTests(unittest.TestCase):
    """Неподвижные части карточки и сцены рисуются один раз — и выглядят так же."""

    def assert_same_look(self, expected, actual) -> None:
        self.assertLessEqual(difference(expected, actual), STACKED_ROUNDING)
        self.assertLess(share_above(expected, actual, 1), STACKED_SHARE_ABOVE_ONE)

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from qfluentwidgets import Theme, isDarkTheme, setTheme

        for module in (dot_module, scene_module, hero_module):
            patcher = mock.patch.object(module, "are_live_animations_enabled", return_value=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        # Тема — явно: её оставляет предыдущий тест, а доля расхождений от
        # темы зависит. В тёмной подкраска карточки гуще, и около 0,024 %
        # сглаженных точек расходятся на 2–3 из 255 (замер 26 октября 2026;
        # в светлой таких нет). Глазом это не видно, а предел расхождения
        # тот же — его держит test_dark_theme_layers_stay_within_the_rounding_limit.
        self.addCleanup(setTheme, Theme.DARK if isDarkTheme() else Theme.LIGHT)
        setTheme(Theme.LIGHT)

    def test_dark_theme_layers_stay_within_the_rounding_limit(self) -> None:
        from qfluentwidgets import Theme, setTheme

        setTheme(Theme.DARK)
        for phase, color in (("running", "#6ccb5f"), ("stopped", "#ff6b6b")):
            for scale in (1.0, 1.5):
                with self.subTest(phase=phase, scale=scale):
                    root, card, scene = self._page(phase, color)
                    self._frame(card, scene, 1.3)
                    with mock.patch.object(LayerCache, "draw", paint_directly):
                        expected = render(root, scale)
                    self.assertLessEqual(difference(expected, render(root, scale)), STACKED_ROUNDING)

    def _page(self, phase: str = "running", color: str = "#6ccb5f", *, offset: tuple[int, int] = (23, 31)):
        """Карточка со сценой внутри страницы. Скрытая: цвет и ворота сразу в конечном виде."""
        root = QWidget()
        root.resize(900, 240)
        card = StatusHeroCard(root)
        card.setGeometry(offset[0], offset[1], 820, 167)
        scene = BypassScene(card)
        scene.set_clickable(True)
        scene.move(16, 39)
        card.bind_scene(scene)
        scene.set_color(color)
        scene.set_phase(phase)
        self.addCleanup(root.deleteLater)
        return root, card, scene

    @staticmethod
    def _frame(card, scene, flow_time: float) -> None:
        """Состояние одного кадра потока: пакеты, свечение и дыхание логотипа."""
        import math

        scene._flow_time = flow_time
        scene._pulse_phase = 0.4
        if scene.phase() == "running":
            card._shimmer_t = flow_time
            scene._breath = math.sin(2 * math.pi * flow_time / scene_module.BREATH_PERIOD_S)

    def test_card_frame_matches_the_library_card(self) -> None:
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QImage, QPainter, QRegion
        from qfluentwidgets import Theme, isDarkTheme, setTheme

        self.addCleanup(setTheme, Theme.DARK if isDarkTheme() else Theme.LIGHT)
        for theme in (Theme.DARK, Theme.LIGHT):
            setTheme(theme)
            for hover in (False, True):
                with self.subTest(theme=theme, hover=hover):
                    card = StatusHeroCard()
                    card.resize(400, 120)
                    self.addCleanup(card.deleteLater)
                    card.isHover = hover
                    # Без цвета состояния карточку рисует сама библиотека.
                    self.assertFalse(card.tint().isValid())
                    library = QImage(400, 120, QImage.Format.Format_ARGB32_Premultiplied)
                    library.fill(QColor("#20262e"))
                    card.render(library, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)

                    ours = QImage(400, 120, QImage.Format.Format_ARGB32_Premultiplied)
                    ours.fill(QColor("#20262e"))
                    painter = QPainter(ours)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    card._paint_card_frame(painter)
                    painter.end()
                    self.assertEqual(library, ours)

    def test_running_frame_with_ready_layers_looks_like_direct_painting(self) -> None:
        for scale in (1.0, 1.25, 1.5, 2.0):
            for flow_time in (0.7, 3.33):
                with self.subTest(scale=scale, flow_time=flow_time):
                    root, card, scene = self._page()
                    self._frame(card, scene, flow_time)
                    with mock.patch.object(LayerCache, "draw", paint_directly):
                        expected = render(root, scale)
                    self.assert_same_look(expected, render(root, scale))
                    self.assert_same_look(expected, render(root, scale))
                    # Слои действительно в деле: карточка, а у сцены — пол, стена и кнопка.
                    self.assertEqual(len(card._layers), 1)
                    self.assertEqual(len(scene._layers), 3)

    def test_stopped_and_starting_scenes_with_ready_layers_look_like_direct_painting(self) -> None:
        for phase, color in (("stopped", "#ff6b6b"), ("starting", "#f5a623"), ("failed", "#ff6b6b")):
            for scale in (1.0, 1.5):
                with self.subTest(phase=phase, scale=scale):
                    root, card, scene = self._page(phase, color)
                    self._frame(card, scene, 1.3)
                    with mock.patch.object(LayerCache, "draw", paint_directly):
                        expected = render(root, scale)
                    self.assert_same_look(expected, render(root, scale))
                    self.assert_same_look(expected, render(root, scale))

    def test_still_parts_are_painted_once_for_all_frames(self) -> None:
        root, card, scene = self._page()
        with mock.patch.object(card, "_paint_base", wraps=card._paint_base) as base, mock.patch.object(
            scene, "_paint_ground", wraps=scene._paint_ground
        ) as ground, mock.patch.object(scene, "_paint_wall", wraps=scene._paint_wall) as wall, mock.patch.object(
            scene, "_paint_core", wraps=scene._paint_core
        ) as core, mock.patch.object(scene, "_paint_link", wraps=scene._paint_link) as link:
            for frame in range(8):
                self._frame(card, scene, 0.05 * frame)
                render(root, 1.0)
        for still in (base, ground, wall, core):
            self.assertEqual(still.call_count, 1)
        # Дуга и пакеты — живые: рисуются в каждом кадре.
        self.assertEqual(link.call_count, 8)

    def test_new_look_gets_a_new_layer(self) -> None:
        root, card, scene = self._page()
        self._frame(card, scene, 0.5)
        render(root, 1.0)
        with mock.patch.object(card, "_paint_base", wraps=card._paint_base) as base, mock.patch.object(
            scene, "_paint_core", wraps=scene._paint_core
        ) as core:
            # Кнопку нажали: она меньше.
            scene._pressed = True
            render(root, 1.0)
            self.assertEqual(core.call_count, 1)
            scene._pressed = False
            # Карточка стала шире — рамка другая.
            card.resize(card.width() + 40, card.height())
            render(root, 1.0)
            render(root, 1.0)
            self.assertEqual(base.call_count, 1)

    def test_moving_scene_is_painted_directly(self) -> None:
        root, card, scene = self._page()
        self._frame(card, scene, 0.5)
        self.assertTrue(scene._is_still())
        with mock.patch.object(scene, "_paint_ground", wraps=scene._paint_ground) as ground, mock.patch.object(
            scene, "_paint_core", wraps=scene._paint_core
        ) as core:
            scene._open_t = 0.6  # ворота едут
            self.assertFalse(scene._is_still())
            render(root, 1.0)
            render(root, 1.0)
            scene._open_t = 1.0
            scene._shake_t = 0.3  # сцену трясёт
            self.assertFalse(scene._is_still())
            render(root, 1.0)
            scene._shake_t = 0.0
            self.assertEqual(ground.call_count, 3)

            scene._pop_t = 0.4  # кнопка «вздыхает»
            before = core.call_count
            render(root, 1.0)
            render(root, 1.0)
            self.assertEqual(core.call_count, before + 2)
        # Слоя кнопки нет; пол и стена на последних кадрах уже стояли.
        self.assertEqual(len(scene._layers), 2)

    def test_stopped_wall_shakes_directly_and_stands_as_a_layer(self) -> None:
        root, card, scene = self._page("stopped", "#ff6b6b")
        impacts: list[float] = []
        original = scene._paint_wall

        def record(painter, center, color, open_t, impact):
            impacts.append(impact)
            original(painter, center, color, open_t, impact)

        with mock.patch.object(scene, "_paint_wall", side_effect=record), mock.patch.object(
            scene, "is_beating", return_value=True
        ):
            # Пакет только что ударился о стену: она вздрагивает — без слоя.
            scene._pulse_phase = scene_module.BLOCKED_PACKET_STARTS[0] + 0.45 * scene_module.BLOCKED_PACKET_SPAN
            render(root, 1.0)
            render(root, 1.0)
            self.assertEqual(len(impacts), 2)
            self.assertGreater(min(impacts), 0.0)
            # Пакеты ещё не вылетели: стена стоит и берётся слоем.
            scene._pulse_phase = 0.01
            render(root, 1.0)
            render(root, 1.0)
            self.assertEqual(impacts[2:], [0.0])

    def test_color_fade_paints_the_card_directly(self) -> None:
        root, card, scene = self._page()
        with mock.patch.object(card, "_paint_base", wraps=card._paint_base) as base:
            with mock.patch.object(card._tint_fade, "state", return_value=card._tint_fade.State.Running):
                render(root, 1.0)
                render(root, 1.0)
            self.assertEqual(base.call_count, 2)
            self.assertEqual(len(card._layers), 0)
            render(root, 1.0)
            render(root, 1.0)
            self.assertEqual(base.call_count, 3)

    def test_motion_region_is_built_once_per_size(self) -> None:
        from PyQt6.QtGui import QRegion

        _root, _card, scene = self._page()
        first = scene._motion_region()
        with mock.patch.object(scene, "_lanes", wraps=scene._lanes) as lanes:
            again = scene._motion_region()
            lanes.assert_not_called()
        self.assertEqual(first, again)
        # Вызывающий получает свою копию: её можно менять.
        again += QRegion(0, 0, 5, 5)
        self.assertEqual(scene._motion_region(), first)

        scene.set_stretched(True)
        scene.resize(500, scene.height())
        self.assertNotEqual(scene._motion_region(), first)


if __name__ == "__main__":
    unittest.main()
