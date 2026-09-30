"""Прерывание движения: новое начинается там, где застали старое.

Это главное правило плавного интерфейса и единственное, которое здесь
нарушалось. Блок, пойманный на середине ухода, терял свой слой вместе с
прогрессом, и переключение обратно начинало путь с нуля: строка,
уехавшая наполовину вниз, мгновенно возвращалась в начало и ехала
заново. Рывок тем заметнее, чем плавнее всё остальное.

Проверяется здесь четыре вещи, и каждая ломалась по дороге:

* класс слоя один на всё приложение — собирался он заново на каждый
  вызов, и подхват не узнавал собственный же слой;
* прогресс переживает смену направления;
* длительность считается по остатку пути, а не берётся полная — иначе
  подхваченный на девяти десятых блок ползёт последние пиксели столько
  же, сколько ехал бы весь путь;
* блок в движении считается меняющимся всегда. Уезжающая строка ещё
  видима, и по одной видимости переключение обратно сочло бы её «уже на
  месте»: движение доехало бы до конца и спрятало её.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ui.reveal as reveal  # noqa: E402


class TakeoverDurationTests(unittest.TestCase):
    """Чистая арифметика: окна для неё не нужно."""

    def test_full_path_keeps_full_duration(self) -> None:
        self.assertEqual(reveal._takeover_duration(320, 1.0), 320)

    def test_half_path_takes_half_the_time(self) -> None:
        """Скорость при подхвате должна остаться прежней, а не упасть вдвое."""
        self.assertEqual(reveal._takeover_duration(320, 0.5), 160)

    def test_a_sliver_still_reads_as_motion(self) -> None:
        """Пропорция от остатка в один процент — это мигание, а не движение."""
        self.assertEqual(
            reveal._takeover_duration(320, 0.01), reveal.MIN_TAKEOVER_MS
        )

    def test_out_of_range_is_clamped(self) -> None:
        self.assertEqual(reveal._takeover_duration(320, 2.0), 320)
        self.assertEqual(reveal._takeover_duration(320, -1.0), reveal.MIN_TAKEOVER_MS)


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class TakeoverTests(unittest.TestCase):
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
            time.sleep(0.005)

    @staticmethod
    def _progress(widget):
        effect = widget.graphicsEffect()
        return None if effect is None else effect.progress()

    def _catch_mid_flight(self, rows):
        """Ждёт, пока хоть один блок окажется на середине пути."""
        deadline = time.time() + 1.0
        while time.time() < deadline:
            _APP.processEvents()
            for row in rows:
                value = self._progress(row)
                if value is not None and 0.15 < value < 0.85:
                    return row, value
            time.sleep(0.005)
        self.fail("ни один блок не оказался на середине пути")

    def test_effect_class_is_stable(self) -> None:
        """Новый класс на каждый вызов — и подхват слеп: isinstance не сработает."""
        self.assertIs(reveal._effect_class(), reveal._effect_class())

    def test_reveal_picks_up_where_conceal_was_caught(self) -> None:
        _, rows = self._rows()
        reveal.conceal_widgets(rows, on_finished=lambda: None)
        caught, before = self._catch_mid_flight(rows)

        reveal.reveal_widgets(rows)
        _APP.processEvents()

        self.assertAlmostEqual(self._progress(caught), before, delta=0.15)

    def test_conceal_picks_up_where_reveal_was_caught(self) -> None:
        _, rows = self._rows()
        reveal.reveal_widgets(rows)
        caught, before = self._catch_mid_flight(rows)

        reveal.conceal_widgets(rows, on_finished=lambda: None)
        _APP.processEvents()

        self.assertAlmostEqual(self._progress(caught), before, delta=0.15)

    def test_interrupted_reveal_still_arrives(self) -> None:
        """Подхват не должен оставлять блок висеть на полпути."""
        _, rows = self._rows()
        reveal.conceal_widgets(rows, on_finished=lambda: None)
        self._catch_mid_flight(rows)

        reveal.reveal_widgets(rows)
        self._drain(1.2)

        self.assertTrue(all(self._progress(row) is None for row in rows))
        self.assertTrue(all(not row.isHidden() for row in rows))

    def test_interrupted_conceal_still_hides(self) -> None:
        _, rows = self._rows()
        reveal.reveal_widgets(rows)
        self._catch_mid_flight(rows)

        reveal.conceal_widgets(rows, on_finished=lambda: None)
        self._drain(1.2)

        self.assertTrue(all(row.isHidden() for row in rows))
        self.assertTrue(all(self._progress(row) is None for row in rows))

    def test_stopping_motion_still_settles(self) -> None:
        """Снятое движение обязано вернуть блок в покой, а не оставить слой."""
        _, rows = self._rows()
        reveal.conceal_widgets(rows, on_finished=lambda: None)
        self._catch_mid_flight(rows)

        for row in rows:
            reveal.stop_motion(row)
        visible = [not row.isHidden() for row in rows]
        self._drain(0.8)

        self.assertTrue(all(self._progress(row) is None for row in rows))
        self.assertEqual([not row.isHidden() for row in rows], visible)


class SimpleViewTakeoverTests(unittest.TestCase):
    """Проводка подхвата на странице. Читаем исходник: окна тут не нужно."""

    def _source(self) -> str:
        return (
            PROJECT_SRC / "presets" / "ui" / "control" / "simple_view.py"
        ).read_text(encoding="utf-8")

    def test_moving_block_counts_as_changing(self) -> None:
        """Уезжающая строка ещё видима — по видимости её сочли бы «на месте»."""
        source = self._source()

        self.assertIn("in_motion or bool(widget.isHidden()) == visible", source)

    def test_motion_is_kept_on_blocks_about_to_move(self) -> None:
        """Снять слой со всех подряд — значит убить подхват."""
        source = self._source()

        self.assertIn("_settle_motion_outside(page, changing)", source)
        self.assertNotIn("_stop_pending_motion(page)", source)


if __name__ == "__main__":
    unittest.main()
