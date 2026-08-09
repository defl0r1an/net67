"""Лента песчинок на страницах: живая, но не мешающая.

Слой заводится в BasePage, поэтому лента появляется на всех страницах
сразу. Тесты стерегут не вид, а три вещи, каждая из которых уже была
сломана и каждую из которых на глаз не поймать.
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

BASE_PAGE = PROJECT_SRC / "ui" / "pages" / "base_page.py"


class WiringTests(unittest.TestCase):
    def test_layer_is_shown_explicitly(self) -> None:
        """Ребёнок, созданный после показа родителя, скрыт по умолчанию.

        Слой существовал, имел верную геометрию и полный набор
        песчинок, а его paintEvent не вызывался ни разу.
        """
        source = BASE_PAGE.read_text(encoding="utf-8")

        self.assertIn("layer.show()", source)

    def test_ribbon_lives_below_the_content(self) -> None:
        """Ни поверх содержимого, ни под ним — в свободной полосе.

        Под прозрачным viewport лента заставляла Qt перерисовывать всё
        содержимое над собой тридцать раз в секунду: человек получал
        «пятнадцать кадров» на всём интерфейсе.
        """
        source = BASE_PAGE.read_text(encoding="utf-8")

        self.assertIn("content_bottom", source)
        self.assertIn("MIN_BAND_HEIGHT", source)

    def test_ribbon_disappears_when_there_is_no_room(self) -> None:
        """Узкая полоска песка под текстом читается как грязь."""
        from shell.particles import BAND_HEIGHT, MIN_BAND_HEIGHT

        self.assertGreater(MIN_BAND_HEIGHT, 0)
        self.assertLess(MIN_BAND_HEIGHT, BAND_HEIGHT)

    def test_viewport_is_made_transparent(self) -> None:
        """Без этого viewport закрашивает себя и прячет всё, что ниже."""
        source = BASE_PAGE.read_text(encoding="utf-8")

        self.assertIn('viewport.setStyleSheet("background: transparent;")', source)
        self.assertIn("viewport.setAutoFillBackground(False)", source)

    def test_timer_stops_on_hidden_pages(self) -> None:
        """Сорок спрятанных страниц — сорок пересчётов впустую."""
        from ui.pages.base_page import BasePage

        self.assertIn("_stop_particles", inspect.getsource(BasePage.hideEvent))
        self.assertIn("_stop_particles", inspect.getsource(BasePage.cleanup))

    def test_failure_does_not_break_the_page(self) -> None:
        """Оформление не вправе ронять страницу."""
        from ui.pages.base_page import BasePage

        self.assertIn("except Exception", inspect.getsource(BasePage._ensure_particle_layer))


class MainPageTests(unittest.TestCase):
    """На главной должен остаться один источник правды о состоянии."""

    PAGE = (
        PROJECT_SRC / "presets" / "ui" / "control" / "zapret2" / "page.py"
    )

    def test_status_card_is_not_in_the_layout(self) -> None:
        """Она писала «net67 работает», пока кнопка звала «Включить»."""
        source = self.PAGE.read_text(encoding="utf-8")

        self.assertNotIn("self.add_widget(status_widgets.card)", source)

    def test_second_start_button_is_not_in_the_layout(self) -> None:
        source = self.PAGE.read_text(encoding="utf-8")

        self.assertNotIn("self.add_widget(management_widgets.card)", source)

    def test_hidden_widgets_stay_alive(self) -> None:
        """Их видимость читает apply_status_plan и на ней строит решения."""
        source = self.PAGE.read_text(encoding="utf-8")

        self.assertIn("status_widgets.card.setParent(self._offscreen_holder)", source)
        self.assertIn("management_widgets.card.setParent(self._offscreen_holder)", source)

    def test_duplicates_live_in_an_unshowable_holder(self) -> None:
        """setVisible(False) не хватило: карточка всплыла над заголовком.

        Ребёнок навсегда скрытого контейнера показаться не может, кто бы
        ни вызвал ему show().
        """
        source = self.PAGE.read_text(encoding="utf-8")

        self.assertIn("self._offscreen_holder", source)
        self.assertIn("status_widgets.card.setParent(self._offscreen_holder)", source)
        self.assertIn("management_widgets.card.setParent(self._offscreen_holder)", source)

    def test_one_click_button_is_the_main_action(self) -> None:
        """Именно она применяет hosts и делает WhatsApp рабочим."""
        source = self.PAGE.read_text(encoding="utf-8")

        self.assertIn("self.add_widget(self.oneclick_button)", source)


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class RibbonSwitchTests(unittest.TestCase):
    """Лента выключена, но код её оставлен рабочим.

    Просьба была прямой: «эту полосу частиц снизу надо убрать». Роль
    заполнения пустого низа взял слой свечения из shell/ambient.py — он
    лежит под всем окном, дышит медленнее и не притягивает взгляд к
    нижнему краю.

    Удалять код не стали: он рабочий, обвешан тестами и стоил нескольких
    заходов с замерами. Проверки ниже держат его в живом состоянии,
    поэтому и остаются в наборе.
    """

    def test_ribbon_is_off(self) -> None:
        from ui.pages.base_page import BasePage

        self.assertFalse(BasePage.PARTICLES_ENABLED)

    def test_layer_is_not_created_while_it_is_off(self) -> None:
        """Выключённая лента не должна тратить память и такты."""
        import inspect

        from ui.pages.base_page import BasePage

        source = inspect.getsource(BasePage._ensure_particle_layer)

        # Выход по флагу должен стоять раньше создания слоя, иначе
        # выключённая лента всё равно занимала бы память под две тысячи
        # песчинок.
        self.assertIn("if not self.PARTICLES_ENABLED:", source)
        self.assertLess(
            source.index("if not self.PARTICLES_ENABLED:"),
            source.index("ParticleLayer"),
        )


@unittest.skipUnless(
    __import__("ui.pages.base_page", fromlist=["BasePage"]).BasePage.PARTICLES_ENABLED,
    "лента песчинок выключена, см. RibbonSwitchTests",
)
class LivePageTests(unittest.TestCase):
    def _page(self):
        def stub(*args, **kwargs):
            class _Any:
                def __getattr__(self, name):
                    return stub

            return _Any()

        from ui.pages.support_page import SupportPage

        page = SupportPage(create_open_action_worker=stub)
        page.resize(900, 600)
        self.addCleanup(page.deleteLater)
        page.show()
        _APP.processEvents()
        return page

    def test_page_gets_a_visible_ribbon(self) -> None:
        page = self._page()

        layer = page._particle_layer

        self.assertTrue(layer)
        self.assertTrue(layer.isVisible(), "слой создан, но ни разу не показан")
        self.assertTrue(layer.particles)

    def test_ribbon_sits_at_the_bottom(self) -> None:
        page = self._page()
        layer = page._particle_layer

        if layer.isVisible():
            self.assertEqual(layer.geometry().bottom() + 1, page.height())

    def test_ribbon_actually_moves(self) -> None:
        """Неподвижная лента — не оформление, а мусор на экране.

        Настройка animations_enabled стояла в False, а её переключатель
        из интерфейса убран: анимации были выключены у всех и включить
        их было нечем.
        """
        page = self._page()
        layer = page._particle_layer

        self.assertTrue(layer._animations_enabled(), "анимации выключены по умолчанию")
        if layer.isVisible():
            self.assertTrue(layer._timer.isActive(), "таймер ленты не запустился")

    def test_ribbon_does_not_eat_clicks(self) -> None:
        """Красивый фон, съедающий нажатия, — неработающее приложение."""
        from PyQt6.QtCore import Qt

        page = self._page()

        self.assertTrue(
            page._particle_layer.testAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
        )

    def test_hidden_page_stops_the_timer(self) -> None:
        page = self._page()
        layer = page._particle_layer
        layer._animations_enabled = lambda: True
        layer.start()

        page.hide()
        _APP.processEvents()

        self.assertFalse(layer._timer.isActive())


if __name__ == "__main__":
    unittest.main()
