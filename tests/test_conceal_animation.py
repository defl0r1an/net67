"""Правила ухода блоков: обратная волна при переходе в простой вид.

Появление блоки уже получили, уход — нет: они просто пропадали. На
экране это выглядело так, будто расширенный вид показывают бережно, а
убирают рывком.

Проверяется здесь не картинка, а четыре решения, каждое из которых уже
было сломано хотя бы раз в песочнице:

* блок прячется в конце своего пути, а не в начале — иначе ухода никто
  не увидит;
* волна идёт снизу вверх, обратно появлению;
* раскладка смыкается после всех, иначе группы схлопнутся под ещё
  уезжающими строками;
* прерванный уход не прячет блок задним числом и не стреляет по
  удалённому слою.

Последнее — не выдумка про запас: отложенный старт переживал отмену и
ронял процесс с «wrapped C/C++ object has been deleted».
"""

from __future__ import annotations

import os
import pathlib
import sys
import time
import unittest


PROJECT_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ui.reveal as reveal  # noqa: E402

_SOURCE = pathlib.Path(reveal.__file__).read_text(encoding="utf-8")


class ConcealRulesTests(unittest.TestCase):
    """Решения видны в исходнике и проверяются без окна."""

    def test_conceal_is_shorter_than_reveal(self) -> None:
        """Уход не разглядывают: та же длительность читается как ожидание."""
        self.assertLessEqual(reveal.CONCEAL_MS, reveal.REVEAL_MS)
        self.assertGreater(reveal.CONCEAL_MS, 0)

    def test_conceal_is_still_a_wave(self) -> None:
        """Задержка меньше длительности — иначе это очередь, а не волна."""
        self.assertLess(reveal.REVEAL_STAGGER_MS * 2, reveal.CONCEAL_MS)

    def test_wave_runs_backwards(self) -> None:
        """Тот же порядок, что у появления, читался бы как повтор."""
        import inspect

        source = inspect.getsource(reveal.conceal_widgets)

        self.assertIn("reversed(order_by_position", source)

    def test_hiding_happens_at_the_end_of_the_path(self) -> None:
        """Спрятать сразу — значит не показать ухода вовсе."""
        import inspect

        source = inspect.getsource(reveal.conceal_widgets)
        finish = inspect.getsource(reveal._finish_conceal)

        self.assertNotIn("setVisible(False)", source)
        self.assertIn("setVisible(False)", finish)

    def test_delayed_start_is_guarded(self) -> None:
        """Отложенный старт переживал отмену и бил по удалённому слою."""
        self.assertIn("_start_if_current", _SOURCE)
        self.assertEqual(
            _SOURCE.count("lambda target=animation: start_managed_animation(target)"),
            0,
            "остался незащищённый отложенный старт",
        )


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class ConcealBehaviourTests(unittest.TestCase):
    def _rows(self, count: int = 5):
        from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

        host = QWidget()
        host.resize(400, 500)
        layout = QVBoxLayout(host)
        rows = []
        for index in range(count):
            row = QLabel(f"строка {index}")
            row.setFixedHeight(60)
            layout.addWidget(row)
            rows.append(row)
        host.show()
        _APP.processEvents()
        self.addCleanup(host.deleteLater)
        return host, rows

    @staticmethod
    def _drain(seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            _APP.processEvents()
            time.sleep(0.01)

    def test_blocks_stay_on_screen_while_they_leave(self) -> None:
        _, rows = self._rows()

        self.assertTrue(reveal.conceal_widgets(rows, on_finished=lambda: None))
        _APP.processEvents()

        self.assertTrue(all(not row.isHidden() for row in rows))
        self.assertTrue(all(row.graphicsEffect() is not None for row in rows))

    def test_bottom_leaves_first_and_top_last(self) -> None:
        _, rows = self._rows()
        reveal.conceal_widgets(rows, on_finished=lambda: None)

        order = []
        deadline = time.time() + 2.0
        while time.time() < deadline and len(order) < len(rows):
            _APP.processEvents()
            for row in rows:
                if row.isHidden() and row not in order:
                    order.append(row)
            time.sleep(0.005)

        self.assertEqual(len(order), len(rows))
        self.assertIs(order[0], rows[-1])
        self.assertIs(order[-1], rows[0])

    def test_layer_is_removed_after_the_block_is_hidden(self) -> None:
        """Оставленный слой всплыл бы полупрозрачностью при следующем показе."""
        _, rows = self._rows()
        reveal.conceal_widgets(rows, on_finished=lambda: None)
        self._drain(1.5)

        self.assertTrue(all(row.graphicsEffect() is None for row in rows))

    def test_layout_closes_up_once_and_at_the_end(self) -> None:
        _, rows = self._rows()
        calls = []

        reveal.conceal_widgets(rows, on_finished=lambda: calls.append(True))
        self._drain(1.5)

        self.assertEqual(calls, [True])
        self.assertTrue(all(row.isHidden() for row in rows))

    def test_cancelled_conceal_does_not_hide_afterwards(self) -> None:
        """Быстрое переключение туда-обратно прятало только что показанное."""
        _, rows = self._rows()
        reveal.conceal_widgets(rows, on_finished=lambda: None)
        self._drain(0.05)

        for row in rows:
            reveal.stop_motion(row)
        visible = [not row.isHidden() for row in rows]
        self._drain(1.0)

        self.assertEqual([not row.isHidden() for row in rows], visible)
        self.assertTrue(all(row.graphicsEffect() is None for row in rows))

    def test_nothing_to_conceal_starts_nothing(self) -> None:
        self.assertFalse(reveal.conceal_widgets([], on_finished=lambda: None))
        self.assertFalse(reveal.conceal_widgets(None, on_finished=lambda: None))

    def test_disabled_animations_hand_the_job_back(self) -> None:
        """Вернуть False и ничего не спрятать — значит соврать вызывающему."""
        from ui import animation_policy

        _, rows = self._rows()
        original = animation_policy.are_animations_enabled
        animation_policy.are_animations_enabled = lambda: False
        self.addCleanup(
            setattr, animation_policy, "are_animations_enabled", original
        )

        self.assertFalse(reveal.conceal_widgets(rows, on_finished=lambda: None))
        self.assertTrue(all(not row.isHidden() for row in rows))


class SimpleViewWiringTests(unittest.TestCase):
    def test_simple_view_uses_the_wave(self) -> None:
        """Иначе уход остался бы мёртвым кодом."""
        source = (
            PROJECT_SRC / "presets" / "ui" / "control" / "simple_view.py"
        ).read_text(encoding="utf-8")

        self.assertIn("conceal_widgets", source)
        self.assertIn("_stop_pending_motion", source)

    def test_layout_closes_up_after_the_wave(self) -> None:
        """Сомкни раскладку раньше — группы схлопнутся под уезжающими строками."""
        source = (
            PROJECT_SRC / "presets" / "ui" / "control" / "simple_view.py"
        ).read_text(encoding="utf-8")

        self.assertIn("if on_screen and _conceal(changing, _settled):", source)

    def test_the_window_waits_for_the_layout(self) -> None:
        """На хвосте висит размер окна: сожми его до смыкания — и оно дрогнет дважды."""
        source = (
            PROJECT_SRC / "presets" / "ui" / "control" / "simple_view.py"
        ).read_text(encoding="utf-8")
        settled = source[source.index("def _settled() -> None:"):]

        self.assertLess(
            settled.index("_close_up_layout(page, visible)"),
            settled.index("on_settled()"),
        )

    def test_invisible_page_is_not_animated(self) -> None:
        """Переход в простой вид уводит на главную: волна играла бы в пустоту.

        Хуже, что на её конце висит размер окна — он менялся бы через
        полсекунды после нажатия, без всякой видимой причины.
        """
        source = (
            PROJECT_SRC / "presets" / "ui" / "control" / "simple_view.py"
        ).read_text(encoding="utf-8")

        self.assertIn("on_screen = bool(page.isVisible())", source)
        self.assertIn("if changing and on_screen:", source)


if __name__ == "__main__":
    unittest.main()
