"""Нажатие кнопки в записи колокольчика: запись уходит, а не пропадает за кадр.

Раньше кнопка («Восстановить права» и др.) убирала запись пересборкой
списка: строка исчезала мгновенно, соседи прыгали вверх, нижний край
панели дёргался на 86 точек. Выглядело как сбой отрисовки, а не как
ответ на нажатие.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtWidgets import QApplication  # noqa: E402


def _wait(seconds: float, probe=None) -> list:
    samples = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if probe is not None:
            samples.append(probe())
        time.sleep(0.005)
    return samples


class BellDismissMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self, *, animations: bool):
        from ui.notification_inbox import NotificationInbox
        from ui.widgets.notification_bell import NotificationPanel

        switch = patch("ui.animation_policy.are_animations_enabled", return_value=animations)
        switch.start()
        self.addCleanup(switch.stop)
        inbox = NotificationInbox()
        for title in ("DNS от провайдера", "Не удалось записать hosts"):
            inbox.add({"level": "warning", "title": title, "content": "текст", "source": "test"})
        panel = NotificationPanel(inbox, build_action=lambda *_a: None, on_changed=lambda: None)
        panel.show()
        QApplication.processEvents()
        self.addCleanup(panel.deleteLater)
        return inbox, panel

    def test_dismissed_row_fades_then_its_place_closes_smoothly(self) -> None:
        from ui.reveal import ROW_CLOSE_MS, ROW_FADE_MS

        inbox, panel = self._panel(animations=True)
        entry = inbox.entries()[0]
        row = panel._rows[id(entry)]
        start_height = row.height()

        panel._dismiss(entry)

        # Из истории ушла сразу — счётчик не ждёт анимации, — а строка ещё на экране.
        self.assertEqual(len(inbox.entries()), 1)
        self.assertTrue(row.isVisible())
        self.assertIsNotNone(row._row_dismiss_animation)

        def height() -> int:
            # После смыкания список пересобран, и строки уже нет.
            try:
                return 0 if row.isHidden() else row.height()
            except RuntimeError:
                return 0

        heights = _wait((ROW_FADE_MS + ROW_CLOSE_MS) / 1000 + 0.25, probe=height)
        # Место смыкается через промежуточные высоты, а не прыжком в ноль.
        between = {h for h in heights if 0 < h < start_height}
        self.assertGreaterEqual(len(between), 3, heights)
        self.assertEqual(heights, sorted(heights, reverse=True))
        self.assertEqual(len(panel._rows), 1)

    def test_without_animations_row_goes_at_once(self) -> None:
        inbox, panel = self._panel(animations=False)
        entry = inbox.entries()[0]

        panel._dismiss(entry)

        self.assertEqual(len(inbox.entries()), 1)
        self.assertEqual(len(panel._rows), 1)
        self.assertNotIn(id(entry), panel._rows)

    def test_second_press_on_leaving_row_does_not_restart_it(self) -> None:
        from ui.reveal import dismiss_row

        _inbox, panel = self._panel(animations=True)
        row = next(iter(panel._rows.values()))
        calls: list[int] = []
        self.assertTrue(dismiss_row(row, on_finished=lambda: calls.append(1)))
        first = row._row_dismiss_animation
        self.assertTrue(dismiss_row(row, on_finished=lambda: calls.append(2)))
        self.assertIs(row._row_dismiss_animation, first)
        _wait(0.6)
        self.assertEqual(calls, [1])

    def test_panel_height_follows_list_without_jump(self) -> None:
        from ui.reveal import ROW_CLOSE_MS, ROW_FADE_MS

        inbox, panel = self._panel(animations=True)
        tall = panel.height()

        panel._dismiss(inbox.entries()[0])
        heights = _wait((ROW_FADE_MS + 2 * ROW_CLOSE_MS) / 1000 + 0.3, probe=panel.height)

        self.assertLess(heights[-1], tall)
        self.assertTrue(any(heights[-1] < h < tall for h in heights), heights)

    def test_clear_takes_rows_away_in_a_wave_and_leaves_empty_note(self) -> None:
        from PyQt6.QtWidgets import QLabel

        inbox, panel = self._panel(animations=True)
        rows = list(panel._rows.values())

        panel._clear()

        self.assertEqual(inbox.entries(), [])
        self.assertTrue(all(row.isVisible() for row in rows))
        _wait(0.8)
        texts = [label.text() for label in panel.findChildren(QLabel) if label.isVisible()]
        self.assertTrue(any("Пока тихо" in text for text in texts), texts)


if __name__ == "__main__":
    unittest.main()
