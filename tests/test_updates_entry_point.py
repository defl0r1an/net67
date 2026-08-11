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


class CardWiringTests(unittest.TestCase):
    """Карточка добавлена в оба режима, а не только в тот, что открыт."""

    def _extra_card_source(self, module_name: str) -> str:
        import importlib

        module = importlib.import_module(module_name)
        builder = next(
            value
            for name, value in vars(module).items()
            if name.startswith("build_winws") and callable(value)
        )
        return inspect.getsource(builder)

    def test_winws1_has_the_card(self) -> None:
        source = self._extra_card_source("presets.ui.control.zapret1.sections_build")

        self.assertIn("build_updates_card(", source)
        self.assertIn("extra_card.addSettingCard(updates_card)", source)

    def test_winws2_has_the_card(self) -> None:
        source = self._extra_card_source("presets.ui.control.zapret2.sections_build")

        self.assertIn("build_updates_card(", source)
        self.assertIn("extra_card.addSettingCard(updates_card)", source)

    def test_both_modes_build_the_same_card(self) -> None:
        """Иначе разойдутся подписи, и одна из них станет неправильной."""
        from presets.ui.control.zapret1 import sections_build as winws1
        from presets.ui.control.zapret2 import sections_build as winws2

        self.assertIs(winws1.build_updates_card, winws2.build_updates_card)


class CardAppearanceTests(unittest.TestCase):
    """Карточка строится настоящая, с настоящими надписями."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:  # pragma: no cover - среда без Qt
            raise unittest.SkipTest(f"Qt недоступен: {exc}") from exc
        cls._app = QApplication.instance() or QApplication([])

    def _card(self):
        from PyQt6.QtWidgets import QWidget
        from qfluentwidgets import PushSettingCard

        from presets.ui.control.shared_builders import build_updates_card

        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        return build_updates_card(
            push_setting_card_cls=PushSettingCard,
            tr_fn=lambda _key, default: default,
            parent=parent,
        )

    def test_card_says_what_it_does(self) -> None:
        card = self._card()

        self.assertEqual(card.titleLabel.text(), "Обновления")
        self.assertIn("версию", card.contentLabel.text())

    def test_click_without_a_window_does_not_raise(self) -> None:
        """Окна в тесте нет — нажатие обязано просто ничего не сделать."""
        card = self._card()

        card.button.click()
        self._app.processEvents()


if __name__ == "__main__":
    unittest.main()
