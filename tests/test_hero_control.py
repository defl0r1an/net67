"""Главный экран: одна крупная кнопка и одно состояние под ней.

Раньше управление было строкой кнопок в углу, а состояние — карточкой
ниже, и они расходились: на скриншоте кнопка предлагала «Включить», а
карточка писала «net67 работает». Здесь заголовок выводится из видимости
кнопок, а не из отдельного источника, поэтому разойтись им не с чем.

Две тонкости Qt, каждая из которых уже стоила пустого круга на экране,
закреплены тестами отдельно — на глаз они не ловятся.
"""

from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class StateTitleTests(unittest.TestCase):
    def test_running_and_stopped_read_plainly(self) -> None:
        from ui.widgets.hero_control import TITLE_RUNNING, TITLE_STOPPED, state_title

        self.assertEqual(state_title(start_visible=False, stop_visible=True), TITLE_RUNNING)
        self.assertEqual(state_title(start_visible=True, stop_visible=False), TITLE_STOPPED)

    def test_switching_says_so_instead_of_guessing(self) -> None:
        """Показать устойчивое состояние в момент перехода — соврать."""
        from ui.widgets.hero_control import TITLE_BUSY, state_title

        self.assertEqual(state_title(start_visible=False, stop_visible=False), TITLE_BUSY)
        self.assertEqual(state_title(start_visible=True, stop_visible=True), TITLE_BUSY)


class IconPlacementTests(unittest.TestCase):
    """qfluentwidgets ставит значок по minimumSizeHint, а не по центру."""

    def test_hint_width_centres_the_icon(self) -> None:
        from ui.widgets.hero_control import (
            HERO_BUTTON_SIZE,
            HERO_ICON_SIZE,
            centering_size_hint_width,
        )

        # Формула самой библиотеки: x = 12 + (ширина - mw) // 2.
        hint = centering_size_hint_width()
        x = 12 + (HERO_BUTTON_SIZE - hint) // 2

        self.assertEqual(x, (HERO_BUTTON_SIZE - HERO_ICON_SIZE) // 2)

    def test_button_text_would_push_the_icon_out(self) -> None:
        """Ради этого и заведён подкласс: с текстом круг оставался пустым."""
        from ui.widgets.hero_control import HERO_BUTTON_SIZE

        wide_hint = 160  # примерно «Запустить net67»
        x = 12 + (HERO_BUTTON_SIZE - wide_hint) // 2

        self.assertLess(x, 0, "значок и так попадал бы в круг — подкласс не нужен")

    def test_subclass_is_used_because_qt_calls_from_cpp(self) -> None:
        """Присвоение метода экземпляру в PyQt до C++ не доходит."""
        from ui.widgets.hero_control import make_round_button_class

        source = inspect.getsource(make_round_button_class)

        self.assertIn("minimumSizeHint", source)
        self.assertIn("class _RoundButton(base_cls)", source)

    def test_show_to_parent_is_watched(self) -> None:
        """Show не приходит ребёнку ещё не показанного окна, ToParent — да."""
        from ui.widgets.hero_control import _VISIBILITY_EVENTS
        from PyQt6.QtCore import QEvent

        self.assertIn(QEvent.Type.ShowToParent, _VISIBILITY_EVENTS)
        self.assertIn(QEvent.Type.HideToParent, _VISIBILITY_EVENTS)

    def test_icon_uses_the_opposite_theme(self) -> None:
        """Тема осветляет акцент: белый значок на белой кнопке не виден."""
        from ui.widgets import hero_control

        source = inspect.getsource(hero_control._apply_contrasting_icon)

        self.assertIn("Theme.LIGHT if isDarkTheme() else Theme.DARK", source)


class VisibilitySourceTests(unittest.TestCase):
    def test_hidden_flag_is_used_not_visibility(self) -> None:
        """isVisible() отвечает «нет», пока окно не показано.

        На этапе сборки экрана обе кнопки выглядели бы спрятанными, и
        заголовок навсегда застревал на «Меняем состояние…».
        """
        import ast

        from ui.widgets.hero_control import HeroControlCard

        source = inspect.getsource(HeroControlCard.refresh_state)
        tree = ast.parse(source.lstrip())
        # Ищем вызовы, а не слова: isVisible упомянут в комментарии
        # намеренно — он объясняет, почему его тут нет.
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        self.assertIn("isHidden", called)
        self.assertNotIn("isVisible", called)


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class CardBehaviourTests(unittest.TestCase):
    def _card(self):
        from qfluentwidgets import (
            CaptionLabel,
            IndeterminateProgressBar,
            PrimaryPushButton,
            PushButton,
        )

        from presets.ui.control.zapret2.build import build_winws2_pages_management_section
        from ui.widgets.hero_control import make_round_button_class

        noop = lambda *args, **kwargs: None
        widgets = build_winws2_pages_management_section(
            add_section_title=lambda **kwargs: None,
            tr_fn=lambda key, default: default,
            caption_label_cls=CaptionLabel,
            indeterminate_progress_bar_cls=IndeterminateProgressBar,
            big_action_button_cls=make_round_button_class(PrimaryPushButton),
            stop_button_cls=make_round_button_class(PushButton),
            on_start=noop,
            on_stop=noop,
            on_stop_and_exit=noop,
            parent=None,
        )
        self.addCleanup(widgets.card.deleteLater)
        return widgets

    def test_page_gets_the_new_card(self) -> None:
        from ui.widgets.hero_control import HeroControlCard

        self.assertIsInstance(self._card().card, HeroControlCard)

    def test_title_follows_the_buttons(self) -> None:
        from ui.widgets.hero_control import TITLE_RUNNING, TITLE_STOPPED

        widgets = self._card()

        self.assertEqual(widgets.card._title_label.text(), TITLE_STOPPED)

        widgets.start_btn.hide()
        widgets.stop_winws_btn.show()

        self.assertEqual(widgets.card._title_label.text(), TITLE_RUNNING)

    def test_button_is_a_circle(self) -> None:
        from ui.widgets.hero_control import HERO_BUTTON_SIZE

        widgets = self._card()

        self.assertEqual(widgets.start_btn.width(), HERO_BUTTON_SIZE)
        self.assertEqual(widgets.start_btn.height(), HERO_BUTTON_SIZE)

    def test_button_keeps_its_text_for_screen_readers(self) -> None:
        """Текст скрыт цветом, а не удалён: его читают вслух."""
        widgets = self._card()

        self.assertTrue(widgets.start_btn.text().strip())

    def test_handlers_survive_the_restyling(self) -> None:
        """Кнопки приходят готовыми — оформление не вправе их ломать."""
        calls = []
        from qfluentwidgets import (
            CaptionLabel,
            IndeterminateProgressBar,
            PrimaryPushButton,
            PushButton,
        )

        from presets.ui.control.zapret2.build import build_winws2_pages_management_section
        from ui.widgets.hero_control import make_round_button_class

        widgets = build_winws2_pages_management_section(
            add_section_title=lambda **kwargs: None,
            tr_fn=lambda key, default: default,
            caption_label_cls=CaptionLabel,
            indeterminate_progress_bar_cls=IndeterminateProgressBar,
            big_action_button_cls=make_round_button_class(PrimaryPushButton),
            stop_button_cls=make_round_button_class(PushButton),
            on_start=lambda: calls.append("start"),
            on_stop=lambda: calls.append("stop"),
            on_stop_and_exit=lambda: calls.append("exit"),
            parent=None,
        )
        self.addCleanup(widgets.card.deleteLater)

        widgets.start_btn.click()

        self.assertEqual(calls, ["start"])


if __name__ == "__main__":
    unittest.main()
