"""В приложение вернулся вход в раздел обновлений.

Вопрос был короткий: «где вообще кнопка проверки версии». Правильный
ответ оказался — нигде.

Раздел обновлений (`PageName.SERVERS`) в навигации помечен скрытым, и
попасть в него можно было только через «О программе». А «О программе»
убрали из меню вместе со ссылками прежнего автора — вход исчез вместе с
ней, сам раздел при этом остался рабочим.

Проверка обновлений при запуске продолжала работать, поэтому пропажу
никто не заметил. Но она идёт не чаще раза в шесть часов: перезапускать
приложение, чтобы посмотреть версию, бесполезно.

Теперь в «Дополнительных действиях» обоих режимов есть карточка
«Обновления». Проверки ниже стерегут именно её наличие: карточку легко
потерять при следующей перетряске секций, а заметить пропажу — снова
только вопросом вроде исходного.

26 октября 2026 «Дополнительные действия» стали плитками «Быстрых
действий» на вкладке «Обход» (presets/ui/control/quick_actions.py), и
карточка — плиткой «Обновления». Проверки стерегут теперь плитку.
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class NavigationTests(unittest.TestCase):
    def test_updates_page_is_still_hidden_from_the_sidebar(self) -> None:
        """Карточка нужна именно потому, что пункта меню нет.

        Появится пункт — карточка станет лишней, и об этом лучше узнать
        от упавшей проверки, чем от двух входов в один раздел.
        """
        from app.page_names import PageName
        from ui.navigation.schema import get_page_spec

        spec = get_page_spec(PageName.SERVERS)

        self.assertTrue(spec.is_hidden)
        self.assertIsNone(spec.sidebar_group)

    def test_open_goes_to_the_updates_page(self) -> None:
        from updater import open_page

        source = inspect.getsource(open_page.open_updates_page)

        self.assertIn("PageName.SERVERS", source)

    def test_open_asks_for_an_internal_page(self) -> None:
        """Без allow_internal переход в скрытый раздел отклоняется."""
        from updater import open_page

        source = inspect.getsource(open_page.open_updates_page)

        self.assertIn("allow_internal=True", source)

    def test_window_key_matches_the_one_that_stores_it(self) -> None:
        """Ключ задаётся в одном месте, читается в другом — разъедутся молча."""
        import inspect as _inspect

        from ui import app_window_locator
        from updater.open_page import WINDOW_PROPERTY

        self.assertIn(
            f'"{WINDOW_PROPERTY}"',
            _inspect.getsource(app_window_locator.register_app_window),
        )

    def test_missing_window_is_not_a_crash(self) -> None:
        """Кнопку могут нажать раньше, чем окно попадёт в свойство."""
        from updater import open_page

        original = open_page.find_main_window
        open_page.find_main_window = lambda: None
        try:
            self.assertFalse(open_page.open_updates_page())
        finally:
            open_page.find_main_window = original


class TileWiringTests(unittest.TestCase):
    """Плитка «Обновления» есть в «Быстрых действиях» и ведёт в раздел обновлений."""

    def test_quick_actions_have_the_tile(self) -> None:
        from presets.ui.control.quick_actions import quick_action_specs

        specs = {spec.key: spec for spec in quick_action_specs("page.winws2_control")}

        self.assertIn("updates", specs)
        self.assertEqual(specs["updates"].title[1], "Обновления")

    def test_page_wires_the_tile_to_the_updates_page(self) -> None:
        from presets.ui.control.control_page_shared import ControlPageActionMixin
        from presets.ui.control.zapret2.page import Zapret2ModeControlPage

        self.assertIn('"updates": self._open_updates', inspect.getsource(Zapret2ModeControlPage._build_ui))
        self.assertIn("open_updates_page()", inspect.getsource(ControlPageActionMixin._open_updates))


class TileAppearanceTests(unittest.TestCase):
    """Плитка строится настоящая, с настоящими надписями."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:  # pragma: no cover - среда без Qt
            raise unittest.SkipTest(f"Qt недоступен: {exc}") from exc
        cls._app = QApplication.instance() or QApplication([])

    def test_tile_says_what_it_does(self) -> None:
        from PyQt6.QtWidgets import QWidget

        from presets.ui.control.quick_actions import build_quick_actions, quick_action_specs

        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        widgets = build_quick_actions(
            tr_fn=lambda _key, default: default,
            text_prefix="page.winws2_control",
            handlers={spec.key: (lambda: None) for spec in quick_action_specs("page.winws2_control")},
            parent=parent,
        )
        tile = widgets.tiles["updates"]

        self.assertEqual(tile.title(), "Обновления")
        self.assertIn("версию", tile.content())

    def test_click_without_a_window_does_not_raise(self) -> None:
        """Окна в тесте нет — нажатие обязано просто ничего не сделать."""
        from presets.ui.control.control_page_shared import ControlPageActionMixin
        from updater import open_page

        original = open_page.find_main_window
        open_page.find_main_window = lambda: None
        try:
            ControlPageActionMixin._open_updates(object())
        finally:
            open_page.find_main_window = original


if __name__ == "__main__":
    unittest.main()
