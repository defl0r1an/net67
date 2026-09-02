"""Правила появления блоков. Без Qt: читаем модуль текстом.

Тесты, поднимающие QtWidgets, в песочнице без графических библиотек
падают на libEGL, а проверять здесь надо не отрисовку, а решения:
откуда берётся порядок, чем задаётся волна и снимается ли слой после
показа. Всё это видно в исходнике.
"""

from __future__ import annotations

import pathlib
import unittest

import ui.reveal as reveal

_SOURCE = pathlib.Path(reveal.__file__).read_text(encoding="utf-8")


class WaveTimingTests(unittest.TestCase):
    def test_neighbours_overlap(self) -> None:
        """Волна получается перекрытием, а не длительностью.

        Если задержка между соседями догонит длительность одного
        появления, блоки перестанут ехать внахлёст и волна распадётся
        на очередь: поехал — доехал — поехал следующий.
        """
        self.assertLess(
            reveal.REVEAL_STAGGER_MS * 2,
            reveal.REVEAL_MS,
            "соседние блоки почти не перекрываются — это очередь, а не волна",
        )

    def test_queue_has_an_end(self) -> None:
        """Задержка перестаёт расти, иначе последний блок опаздывает.

        Полсекунды — примерно столько человек смотрит на изменившийся
        экран. Позже этого блок возникает уже на готовой странице, и
        выглядит это как забытая и дорисованная строка.
        """
        longest = reveal.REVEAL_STAGGER_LIMIT * reveal.REVEAL_STAGGER_MS
        self.assertLessEqual(longest, 500)

    def test_rise_is_small(self) -> None:
        """Сдвиг задаёт направление, а не переносит блок."""
        self.assertLessEqual(reveal.REVEAL_RISE_PX, 24)
        self.assertGreater(reveal.REVEAL_RISE_PX, 0)


class OrderTests(unittest.TestCase):
    def test_order_is_taken_from_the_screen(self) -> None:
        """Очередь строится по координатам, а не по порядку в списке."""

        class _Point:
            def __init__(self, y):
                self._y = y

            def x(self):
                return 0

            def y(self):
                return self._y

        class _Widget:
            def __init__(self, name, y):
                self.name, self._y = name, y

            def window(self):
                return self

            def rect(self):
                return self

            def topLeft(self):
                return None

            def mapTo(self, _window, _point):
                return _Point(self._y)

        given = [_Widget("низ", 900), _Widget("верх", 100), _Widget("середина", 400)]
        self.assertEqual(
            [w.name for w in reveal.order_by_position(given)],
            ["верх", "середина", "низ"],
        )

    def test_unmeasurable_widget_does_not_break_the_queue(self) -> None:
        """Виджет без геометрии остаётся на своём месте, а не роняет показ."""

        class _Broken:
            name = "сломанный"

            def window(self):
                raise RuntimeError("нет окна")

            def rect(self):
                raise RuntimeError("нет геометрии")

        widgets = [_Broken()]
        self.assertEqual(len(reveal.order_by_position(widgets)), 1)


class EffectContractTests(unittest.TestCase):
    def test_layer_is_removed_after_the_show(self) -> None:
        """Слой отрисовки снимается: оставленный, он дорожает каждый кадр."""
        self.assertIn("setGraphicsEffect(None)", _SOURCE)

    def test_movement_avoids_the_layout(self) -> None:
        """Сдвиг не трогает раскладку.

        Отступы и move() заставляют Qt пересчитывать геометрию на каждом
        кадре, и на тяжёлой странице это съедает ровно ту плавность,
        ради которой всё затевалось.
        """
        for forbidden in ("setContentsMargins", ".move("):
            self.assertNotIn(
                forbidden,
                _SOURCE,
                f"движение через {forbidden} возвращает пересчёт раскладки",
            )

    def test_bounding_rect_leaves_room(self) -> None:
        """Пока блок не доехал, он нарисован мимо места — нужен запас."""
        self.assertIn("boundingRectFor", _SOURCE)

    def test_respects_the_animation_switch(self) -> None:
        """Отключил анимации — ничего не появляется и не мигает."""
        self.assertIn("are_animations_enabled", _SOURCE)


if __name__ == "__main__":
    unittest.main()
