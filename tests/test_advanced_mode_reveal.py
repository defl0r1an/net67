"""Переход в расширенный вид: вкладки и блоки настроек появляются плавно.

Просьба была такая: «при нажатии расширенного режима дополнительные
вкладки сверху плавно выезжали, а дополнительные параметры тоже
появлялись с анимацией на главной странице».

В простом виде из четырёх разделов остаётся один, а на странице
управления спрятано семь блоков. При переключении всё это возникало
разом — глаз не успевает понять, что именно добавилось.

Два правила, которые тут легко нарушить.

Анимируется только появившееся. Проявлять заново то, что и так на
экране, — значит моргать им на ровном месте.

Эффект прозрачности снимается после показа. Он рисует виджет в
отдельный слой, и оставленный навсегда удорожает каждую последующую
перерисовку.
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


class TimingTests(unittest.TestCase):
    """Числа проверяются без Qt."""

    def test_tab_reveal_reads_as_smooth_not_as_a_wait(self) -> None:
        from shell.tabs import TAB_REVEAL_MS

        self.assertGreaterEqual(TAB_REVEAL_MS, 120)
        self.assertLessEqual(TAB_REVEAL_MS, 320)

    def test_tabs_appear_one_after_another(self) -> None:
        """Разом — это рывок; очередь читается как «раздел за разделом»."""
        from shell.tabs import TAB_STAGGER_MS

        self.assertGreater(TAB_STAGGER_MS, 0)

    def test_tail_does_not_outlast_the_reveal_itself(self) -> None:
        """Четыре раздела: последний не должен проявляться в тишине."""
        from shell.tabs import TAB_REVEAL_MS, TAB_STAGGER_MS

        self.assertLessEqual(TAB_STAGGER_MS * 4, TAB_REVEAL_MS * 2)

    def test_settings_blocks_have_their_own_pace(self) -> None:
        from presets.ui.control.simple_view import REVEAL_MS, REVEAL_STAGGER_MS

        self.assertGreaterEqual(REVEAL_MS, 120)
        self.assertGreater(REVEAL_STAGGER_MS, 0)


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class TabRevealTests(unittest.TestCase):
    def _bar(self):
        from shell.tabs import GroupTabBar

        bar = GroupTabBar()
        self.addCleanup(bar.deleteLater)
        return bar

    def _settle(self, seconds: float = 0.6) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            _APP.processEvents()
            time.sleep(0.01)

    def test_new_tabs_start_invisible(self) -> None:
        bar = self._bar()
        bar.set_groups(["root"])
        _APP.processEvents()

        bar.set_groups(["root", "system", "diagnostics"])

        effect = bar.tabs["system"].graphicsEffect()
        self.assertIsNotNone(effect)
        self.assertLess(effect.opacity(), 0.2)

    def test_existing_tabs_are_left_alone(self) -> None:
        """Проявлять то, что и так на экране, — моргание на ровном месте."""
        bar = self._bar()
        bar.set_groups(["root"])
        # Ждём: первая вкладка тоже появилась и тоже проявляется. Нас
        # интересует второй заход, когда она уже стоит на экране.
        self._settle()

        bar.set_groups(["root", "system"])

        self.assertIsNone(bar.tabs["root"].graphicsEffect())

    def test_effect_is_removed_when_the_reveal_ends(self) -> None:
        bar = self._bar()
        bar.set_groups(["root"])
        _APP.processEvents()
        bar.set_groups(["root", "system", "diagnostics"])

        self._settle()

        for name in ("system", "diagnostics"):
            with self.subTest(tab=name):
                self.assertIsNone(bar.tabs[name].graphicsEffect())

    def test_reveal_obeys_the_animation_switch(self) -> None:
        """Кто выключил анимации, не должен их видеть."""
        import inspect

        from shell import tabs

        source = inspect.getsource(tabs.reveal_tabs)

        self.assertIn("are_animations_enabled", source)
        self.assertIn("start_managed_animation", source)


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class SettingsRevealTests(unittest.TestCase):
    """Блоки на странице управления."""

    def _page(self):
        from PyQt6.QtWidgets import QLabel, QWidget

        page = QWidget()
        self.addCleanup(page.deleteLater)
        for attr in ("control_section_label", "control_card_card", "extra_card"):
            widget = QLabel(attr, page)
            widget.hide()
            setattr(page, attr, widget)
        return page

    def test_hidden_blocks_are_revealed(self) -> None:
        from presets.ui.control.simple_view import _reveal

        page = self._page()
        blocks = [page.control_section_label, page.control_card_card]
        for block in blocks:
            block.show()

        _reveal(blocks)

        effect = blocks[0].graphicsEffect()
        self.assertIsNotNone(effect)
        self.assertLess(effect.opacity(), 0.2)

    def test_reveal_uses_opacity_not_movement(self) -> None:
        """Сдвиг блока в раскладке — это пересчёт всей страницы на кадр.

        Страница настроек для этого слишком тяжёлая: ровно на таком
        пересчёте интерфейс уже шёл «пятнадцатью кадрами».
        """
        import inspect

        from presets.ui.control import simple_view

        source = inspect.getsource(simple_view._reveal)

        self.assertIn("QGraphicsOpacityEffect", source)
        self.assertNotIn("setContentsMargins", source)
        self.assertNotIn(".move(", source)

    def test_only_appearing_blocks_are_collected(self) -> None:
        import inspect

        from presets.ui.control import simple_view

        source = inspect.getsource(simple_view.apply_simple_view)

        self.assertIn("isHidden()", source)
        self.assertLess(source.index("appearing"), source.index("_set_visible"))


if __name__ == "__main__":
    unittest.main()
