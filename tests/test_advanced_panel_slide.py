"""Панель расширенного режима выезжает плавно и с выбранной стороны.

Простой вид показывает одну главную страницу, всё остальное открывает
кнопка «Расширенные настройки». Панель с разделами перекрывает часть
содержимого, пока едет, поэтому сторону выбирает человек: на широком
мониторе удобнее слева, на вертикальном — сверху, а с окном у правого
края экрана — справа.

Правило движения проверяется без окна намеренно. «Слева панель приезжает
справа налево» — это арифметика, и она не должна зависеть от того,
удалось ли поднять Qt.
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class SideTests(unittest.TestCase):
    def test_every_side_hides_outside_the_window(self) -> None:
        """Спрятанная панель обязана уйти за край целиком."""
        from ui.navigation.panel_side import SIDES, hidden_offset

        for side in SIDES:
            with self.subTest(side=side.key):
                dx, dy = hidden_offset(side.key, width=260, height=180)
                moved = abs(dx) if side.axis == "x" else abs(dy)
                self.assertEqual(moved, 260 if side.axis == "x" else 180)

    def test_left_and_right_move_opposite_ways(self) -> None:
        from ui.navigation.panel_side import hidden_offset

        left = hidden_offset("left", width=260, height=180)[0]
        right = hidden_offset("right", width=260, height=180)[0]

        self.assertLess(left, 0)
        self.assertGreater(right, 0)

    def test_top_moves_along_the_other_axis(self) -> None:
        from ui.navigation.panel_side import hidden_offset

        dx, dy = hidden_offset("top", width=260, height=180)

        self.assertEqual(dx, 0)
        self.assertLess(dy, 0)

    def test_unknown_side_falls_back_instead_of_failing(self) -> None:
        """Испорченная настройка не должна ломать переключение режима."""
        from ui.navigation.panel_side import DEFAULT_SIDE, normalize_side

        for junk in ("сбоку", "", None, 17):
            with self.subTest(value=junk):
                self.assertEqual(normalize_side(junk), DEFAULT_SIDE)

    def test_default_keeps_the_habit(self) -> None:
        """Панель всегда была слева — смена умолчания переучивала бы всех."""
        from ui.navigation.panel_side import DEFAULT_SIDE

        self.assertEqual(DEFAULT_SIDE, "left")

    def test_titles_are_offered_for_every_side(self) -> None:
        from ui.navigation.panel_side import SIDES, side_titles

        titles = side_titles()

        self.assertEqual(len(titles), len(SIDES))
        self.assertEqual({key for key, _ in titles}, {side.key for side in SIDES})


class SlideTests(unittest.TestCase):
    """Панель раскрывается по размеру, а не сдвигается по месту.

    Раньше здесь проверялось движение позиции: панель уезжала за левый
    край на свою ширину. Это и оказалось той поломкой, о которой человек
    говорил «нажать расширенный, потом простой — и всё ломается».

    Раскладка расставляет виджеты сама, но пропускает спрятанные, а
    панель прячут сразу после сворачивания. Позиция -288 оставалась на
    ней и становилась новой точкой отсчёта: следующее раскрытие честно
    ехало «на 288 вправо от -288» и возвращалось в -288. Слева получалась
    пустая полоса без единого пункта. Замерено:

        старт             панель x = 0
        уходим в простой  панель x = -288
        возвращаемся      панель x = -288   ожидалось 0

    Ширину раскладка уважает, накопить в ней нечего. Проверка не
    ослаблена, а переписана под другую механику.
    """

    def test_expanding_grows_from_nothing_to_full_size(self) -> None:
        from ui.navigation.panel_slide import compute_slide

        start, end = compute_slide("left", width=260, height=180, expanding=True)

        self.assertEqual(start, 0)
        self.assertEqual(end, 260)

    def test_collapsing_is_the_reverse(self) -> None:
        from ui.navigation.panel_slide import compute_slide

        expand = compute_slide("right", width=260, height=180, expanding=True)
        collapse = compute_slide("right", width=260, height=180, expanding=False)

        self.assertEqual(collapse, (expand[1], expand[0]))

    def test_horizontal_sides_animate_width(self) -> None:
        from ui.navigation.panel_slide import slide_property

        for side in ("left", "right"):
            with self.subTest(side=side):
                self.assertEqual(slide_property(side), b"maximumWidth")

    def test_top_side_animates_height(self) -> None:
        from ui.navigation.panel_slide import slide_property

        self.assertEqual(slide_property("top"), b"maximumHeight")

    def test_top_side_measures_along_its_own_axis(self) -> None:
        """Панель сверху раскрывается на свою высоту, а не ширину."""
        from ui.navigation.panel_slide import compute_slide

        _start, end = compute_slide("top", width=260, height=180, expanding=True)

        self.assertEqual(end, 180)

    def test_duration_reads_as_smooth_not_as_a_wait(self) -> None:
        from ui.navigation.panel_slide import SLIDE_DURATION_MS

        self.assertGreaterEqual(SLIDE_DURATION_MS, 120)
        self.assertLessEqual(SLIDE_DURATION_MS, 320)

    def test_missing_panel_is_not_an_error(self) -> None:
        from ui.navigation.panel_slide import animate_panel

        self.assertIsNone(animate_panel(None, "left", expanding=True))


class PolicyTests(unittest.TestCase):
    def test_animation_obeys_the_application_policy(self) -> None:
        """Кто выключил анимации в системе, не должен их видеть."""
        from ui.navigation import panel_slide

        source = inspect.getsource(panel_slide.animate_panel)

        self.assertIn("start_managed_animation", source)
        self.assertNotIn("animation.start()", source)

    def test_animation_is_kept_alive(self) -> None:
        """Локальная ссылка соберётся раньше, чем анимация доиграет."""
        from ui.navigation import panel_slide

        source = inspect.getsource(panel_slide.animate_panel)

        self.assertIn("_net67_slide_animation", source)

    def test_panel_settles_even_if_interrupted(self) -> None:
        """Застрявшая на середине панель закроет содержимое навсегда."""
        from ui.navigation import panel_slide

        source = inspect.getsource(panel_slide.animate_panel)

        self.assertIn("_settle", source)
        self.assertIn("animation.finished.connect(_settle)", source)

    def test_position_is_never_touched(self) -> None:
        """Ровно та ошибка, из-за которой панель пропадала совсем."""
        from ui.navigation import panel_slide

        source = inspect.getsource(panel_slide)

        self.assertNotIn("panel.move(", source)

    def test_items_appear_one_after_another(self) -> None:
        """Просили «красивые, а не просто выезд» — меню собирается на глазах."""
        from ui.navigation.panel_slide import STAGGER_LIMIT, STAGGER_MS

        self.assertGreater(STAGGER_MS, 0)
        # Хвост появления не должен тянуться дольше самого раскрытия:
        # иначе последний пункт проявляется, когда панель уже стоит.
        from ui.navigation.panel_slide import ITEM_FADE_MS, SLIDE_DURATION_MS

        tail = STAGGER_LIMIT * STAGGER_MS + ITEM_FADE_MS
        self.assertLessEqual(tail, SLIDE_DURATION_MS * 2)


class WiringTests(unittest.TestCase):
    def test_toggle_slides_the_panel(self) -> None:
        from ui.navigation import advanced_toggle

        source = inspect.getsource(advanced_toggle.toggle_advanced_mode)

        self.assertIn("_slide_navigation_panel", source)

    def test_slide_runs_after_visibility_is_applied(self) -> None:
        """Иначе человек увидит панель, в которой ещё не те разделы."""
        from ui.navigation import advanced_toggle

        source = inspect.getsource(advanced_toggle.toggle_advanced_mode)
        filter_at = source.index("apply_nav_visibility_filter(window")
        slide_at = source.index("_slide_navigation_panel")

        self.assertLess(filter_at, slide_at)

    def test_broken_animation_does_not_block_the_switch(self) -> None:
        """Оформление не вправе мешать переключению режима."""
        from ui.navigation import advanced_toggle

        source = inspect.getsource(advanced_toggle._slide_navigation_panel)

        self.assertIn("except Exception", source)

    def test_the_appearance_page_is_gone(self) -> None:
        """Здесь проверялось, что выбор стороны панели есть в оформлении.

        Страницы оформления больше нет — раздел убран из продукта, а
        сама страница была скрыта и весила 1800 строк. Настройка
        осталась в хранилище и продолжает читаться (проверка ниже);
        органа управления у неё теперь нет, и это осознанно.
        """
        self.assertFalse((PROJECT_SRC / "ui" / "pages" / "appearance_page.py").exists())

    def test_setting_survives_a_round_trip(self) -> None:
        import tempfile

        import settings.store as settings_store

        original = settings_store.MAIN_DIRECTORY
        settings_store.MAIN_DIRECTORY = tempfile.mkdtemp()
        try:
            self.assertEqual(settings_store.get_advanced_panel_side(), "left")

            settings_store.set_advanced_panel_side("top")
            self.assertEqual(settings_store.get_advanced_panel_side(), "top")

            settings_store.set_advanced_panel_side("сбоку")
            self.assertEqual(settings_store.get_advanced_panel_side(), "left")
        finally:
            settings_store.MAIN_DIRECTORY = original


if __name__ == "__main__":
    unittest.main()
