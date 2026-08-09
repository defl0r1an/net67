"""Разделы вынесены во вкладки полосы заголовка.

Раньше всё лежало одним столбцом слева: пять заголовков групп и под ними
полтора десятка пунктов. Столбец приходилось держать шириной в 288
пикселей — иначе «Управление net67 v2» обрывалось на полубукве, — и он
всё равно занимал четверть окна ради списка, в который заглядывают раз в
неделю.

Теперь верхний уровень поднят наверх строкой, а слева остаются страницы
выбранного раздела. Эти тесты стерегут три вещи, на которых такая схема
обычно и ломается: вкладки берутся из самой панели, а не из второго
описания навигации; пустых вкладок не бывает; вкладка догоняет страницу,
открытую мимо неё.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TitleTests(unittest.TestCase):
    """Названия проверяются без Qt: это отображение имён."""

    def test_every_schema_group_has_a_title(self) -> None:
        """Иначе вкладка называлась бы служебным словом вроде «system»."""
        from shell.tabs import GROUP_TITLES, merge_group
        from ui.navigation.schema import SIDEBAR_GROUP_ORDER

        for group in SIDEBAR_GROUP_ORDER:
            with self.subTest(group=group):
                self.assertIn(merge_group(group), GROUP_TITLES)

    def test_main_group_is_named_after_the_button(self) -> None:
        """На кнопке написано «Включить обход» — раздел зовётся так же."""
        from shell.tabs import group_title

        self.assertEqual(group_title("root"), "Обход")

    def test_settings_and_diagnostics_are_one_section(self) -> None:
        """Для человека это одно занятие: посмотреть, что происходит."""
        from shell.tabs import GROUP_TITLES, merge_group

        self.assertEqual(merge_group("appearance"), "diagnostics")
        self.assertNotIn("appearance", GROUP_TITLES)

    def test_merging_does_not_touch_other_sections(self) -> None:
        from shell.tabs import merge_group

        for group in ("root", "settings", "system", "diagnostics"):
            with self.subTest(group=group):
                self.assertEqual(merge_group(group), group)

    def test_unknown_group_is_shown_as_is(self) -> None:
        """Новая группа в схеме не должна давать пустую вкладку."""
        from shell.tabs import group_title

        self.assertEqual(group_title("что-то новое"), "что-то новое")


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class RailGroupingTests(unittest.TestCase):
    """Панель обязана знать, какому разделу принадлежит пункт."""

    def _nav(self):
        from shell.nav_compat import NavigationCompat

        nav = NavigationCompat()
        self.addCleanup(nav.deleteLater)
        return nav

    def test_items_before_any_header_belong_to_the_root_group(self) -> None:
        """Над главной страницей режима подписи нет — и не должно быть."""
        from shell.nav_compat import DEFAULT_GROUP

        nav = self._nav()
        nav.addItem(routeKey="CTL", text="Управление")

        self.assertEqual(nav.group_of("CTL"), DEFAULT_GROUP)

    def test_header_opens_a_new_group(self) -> None:
        nav = self._nav()
        nav.addItem(routeKey="CTL", text="Управление")
        nav.addItemHeader("ИНСТРУМЕНТЫ", group="system")
        nav.addItem(routeKey="DNS", text="Настройка DNS")

        self.assertEqual(nav.group_of("DNS"), "system")

    def test_group_name_wins_over_the_caption(self) -> None:
        """Подпись переводится, имя группы — нет.

        Опираться на подпись значило бы ломать вкладки при смене языка.
        """
        nav = self._nav()
        nav.addItemHeader("ЧТО УГОДНО", group="diagnostics")
        nav.addItem(routeKey="BC", text="BlockCheck")

        self.assertEqual(nav.group_of("BC"), "diagnostics")

    def test_empty_groups_are_not_offered(self) -> None:
        """Вкладка, за которой ничего нет, — это тупик."""
        nav = self._nav()
        nav.addItem(routeKey="CTL", text="Управление")
        nav.addItemHeader("ПУСТО", group="appearance")

        self.assertNotIn("appearance", nav.groups())

    def test_open_group_is_remembered(self) -> None:
        nav = self._nav()
        nav.addItemHeader("ИНСТРУМЕНТЫ", group="system")
        nav.addItem(routeKey="DNS", text="Настройка DNS")

        nav.show_only_group("system")

        self.assertEqual(nav.visible_group, "system")

    def test_filter_does_not_touch_item_visibility(self) -> None:
        """Скрытость пункта — признак простого режима, и только его.

        Панель с экрана убрана, показывают всё вкладки. Пряча пункты ещё
        и по разделу, мы затирали бы этот признак — и вкладки перестали
        бы исчезать в простом виде.
        """
        # Панель не показываем: в приложении она и не показывается.
        # Показанная, она вела бы себя иначе — Qt прячет ребёнка,
        # добавленного к уже показанному родителю, пока ему не скажут
        # show(). У спрятанной панели такого не происходит, и isHidden()
        # у пунктов честно отвечает про простой режим, а не про порядок
        # сборки.
        nav = self._nav()
        nav.addItem(routeKey="CTL", text="Управление")
        nav.addItemHeader("ИНСТРУМЕНТЫ", group="system")
        nav.addItem(routeKey="DNS", text="Настройка DNS")

        nav.show_only_group("system")

        self.assertFalse(nav.items["CTL"].isHidden())
        self.assertFalse(nav.items["DNS"].isHidden())

    def test_hidden_items_drop_their_group_from_the_tabs(self) -> None:
        """В простом виде разделы пустеют, и вкладки обязаны исчезнуть."""
        nav = self._nav()
        nav.addItem(routeKey="CTL", text="Управление")
        nav.addItemHeader("ИНСТРУМЕНТЫ", group="system")
        nav.addItem(routeKey="DNS", text="Настройка DNS")

        nav.items["DNS"].hide()

        self.assertNotIn("system", nav.groups())


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class WindowTests(unittest.TestCase):
    def _window(self):
        import qfluentwidgets
        from PyQt6.QtWidgets import QLabel

        from shell.app_window import AppShellWindow

        qfluentwidgets.setTheme(qfluentwidgets.Theme.DARK)
        window = AppShellWindow()
        window.resize(1100, 700)
        window.show()
        self.addCleanup(window.deleteLater)

        # Режим задаём явно. По умолчанию он простой, а в простом виде
        # вкладка остаётся одна — проверки ниже про расширенный.
        window._advanced_mode_enabled = staticmethod(lambda: True)

        nav = window.navigationInterface

        def add(key: str, title: str) -> None:
            nav.addItem(routeKey=key, text=title)
            page = QLabel(title)
            page.setObjectName(key)
            window.stackedWidget.addWidget(page)

        add("CTL", "Управление net67 v2")
        nav.addItemHeader("НАСТРОЙКИ", group="settings")
        add("PRESETS", "Мои пресеты")
        nav.addItemHeader("ИНСТРУМЕНТЫ", group="system")
        add("DNS", "Настройка DNS")
        add("VPN", "VPN")

        for _ in range(3):
            _APP.processEvents()
        window._refresh_group_tabs()
        _APP.processEvents()
        return window

    def test_tabs_come_from_the_rail(self) -> None:
        """Второе описание навигации разошлось бы с первым."""
        window = self._window()

        self.assertEqual(
            tuple(window.groupTabs.tabs), window.navigationInterface.groups()
        )

    def test_first_group_is_open_at_start(self) -> None:
        window = self._window()

        self.assertEqual(window.groupTabs.current, "root")

    def test_choosing_a_tab_opens_its_first_page(self) -> None:
        window = self._window()

        window.groupTabs.select("system")
        _APP.processEvents()

        self.assertEqual(window.stackedWidget.currentWidget().objectName(), "DNS")

    def test_choosing_a_tab_fills_the_page_row(self) -> None:
        window = self._window()

        window.groupTabs.select("system")
        _APP.processEvents()

        self.assertEqual(set(window.pageTabs.tabs), {"DNS", "VPN"})

    def test_tab_follows_a_page_opened_elsewhere(self) -> None:
        """Страницу открывают поиском и кнопками с других страниц.

        Без этого подчёркнут один раздел, а открыт другой.
        """
        window = self._window()
        presets = window.stackedWidget.widget(1)

        window.switchTo(presets)
        _APP.processEvents()

        self.assertEqual(window.groupTabs.current, "settings")

    def test_clicking_the_open_tab_keeps_the_page(self) -> None:
        """Иначе повторное нажатие сбрасывает на первую страницу раздела."""
        window = self._window()
        window.groupTabs.select("system")
        _APP.processEvents()
        window.switchTo(window.stackedWidget.widget(3))
        _APP.processEvents()

        window.groupTabs.select("system")
        _APP.processEvents()

        self.assertEqual(window.stackedWidget.currentWidget().objectName(), "VPN")

    def test_rail_is_gone_for_good(self) -> None:
        """Боковой панели на экране нет вообще.

        Она осталась в коде как источник знаний о навигации — какие есть
        разделы и какие в них страницы, — но показывать её больше нечему:
        всё переехало в две строки вкладок. Убирать её насовсем значило
        бы переписывать сборщик навигации, поиск и маршрутизацию.
        """
        window = self._window()

        for group in ("root", "system"):
            window.groupTabs.select(group)
            _APP.processEvents()
            with self.subTest(group=group):
                self.assertFalse(window.navigationInterface.isVisible())

    def test_content_takes_the_whole_width(self) -> None:
        window = self._window()

        window.groupTabs.select("root")
        _APP.processEvents()

        self.assertEqual(window.stackedWidget.width(), window.width())

    def test_page_row_lists_the_pages_of_the_group(self) -> None:
        window = self._window()

        window.groupTabs.select("system")
        _APP.processEvents()

        self.assertEqual(set(window.pageTabs.tabs), {"DNS", "VPN"})

    def test_page_row_hides_when_there_is_one_page(self) -> None:
        """Строка с единственной вкладкой — та же пустая полоса."""
        window = self._window()

        window.groupTabs.select("root")
        _APP.processEvents()

        self.assertFalse(window.pageTabs.isVisible())

    def test_choosing_a_page_opens_it(self) -> None:
        window = self._window()
        window.groupTabs.select("system")
        _APP.processEvents()

        window.pageTabs.select("VPN")
        _APP.processEvents()

        self.assertEqual(window.stackedWidget.currentWidget().objectName(), "VPN")

    def test_page_row_follows_a_page_opened_elsewhere(self) -> None:
        window = self._window()
        window.groupTabs.select("system")
        _APP.processEvents()

        window.switchTo(window.stackedWidget.widget(3))
        _APP.processEvents()

        self.assertEqual(window.pageTabs.current, "VPN")

    def test_advanced_toggle_appears_only_when_it_exists(self) -> None:
        """До сборки навигации кнопка вела бы в никуда."""
        window = self._window()

        self.assertFalse(window.advancedButton.isVisible())

    def test_advanced_toggle_calls_the_navigation_item(self) -> None:
        """У пункта уже подключена вся логика смены режима."""
        from shell.app_window import ADVANCED_TOGGLE_ROUTE_KEY

        window = self._window()
        calls = []
        window.navigationInterface.addItem(
            routeKey=ADVANCED_TOGGLE_ROUTE_KEY,
            text="Расширенные настройки",
            onClick=lambda: calls.append(1),
            selectable=False,
        )
        _APP.processEvents()
        window._refresh_group_tabs()
        _APP.processEvents()

        self.assertTrue(window.advancedButton.isVisible())
        window.advancedButton.click()

        self.assertEqual(calls, [1])

    def test_advanced_toggle_is_not_a_page(self) -> None:
        """В строке страниц он был бы пунктом, который ничего не открывает."""
        from shell.app_window import ADVANCED_TOGGLE_ROUTE_KEY

        window = self._window()
        window.navigationInterface.addItem(
            routeKey=ADVANCED_TOGGLE_ROUTE_KEY,
            text="Расширенные настройки",
            selectable=False,
        )
        _APP.processEvents()
        window._refresh_group_tabs()
        window.groupTabs.select("root")
        _APP.processEvents()

        self.assertNotIn(ADVANCED_TOGGLE_ROUTE_KEY, window.pageTabs.tabs)

    def test_simple_view_leaves_one_tab(self) -> None:
        """На первом заходе панель собирается по частям.

        Часть пунктов ещё не успевает получить скрытость от простого
        режима, и вкладки показывались все, хотя режим простой. Поэтому
        в простом виде состав режется по самому режиму, а не только по
        видимости пунктов.
        """
        window = self._window()
        window._advanced_mode_enabled = staticmethod(lambda: False)

        window._refresh_group_tabs()
        _APP.processEvents()

        self.assertEqual(len(window.groupTabs.tabs), 1)

    def test_simple_view_keeps_the_open_section(self) -> None:
        """Иначе вкладка увела бы с открытой страницы при первом же обновлении."""
        window = self._window()
        window.switchTo(window.stackedWidget.widget(2))
        _APP.processEvents()
        window._advanced_mode_enabled = staticmethod(lambda: False)

        window._refresh_group_tabs()
        _APP.processEvents()

        self.assertEqual(list(window.groupTabs.tabs), ["system"])

    def test_search_box_is_gone_from_the_title_bar(self) -> None:
        """Искать не в чем: четыре раздела и по три-четыре страницы.

        Поиск оставлен рабочим — на нём держатся подсказки и переход по
        результату, — но из заголовка убран: места он занимал больше
        всех остальных элементов вместе взятых.
        """
        from ui.navigation.search import SEARCH_IN_TITLEBAR

        self.assertFalse(SEARCH_IN_TITLEBAR)

    def test_removing_search_did_not_split_the_window_buttons(self) -> None:
        """Поиск вставлялся в раскладку заголовка и тянул за собой растяжку.

        Именно на этом «свернуть» и «развернуть» уезжали в середину
        полосы. Проверка сторожит, что после его удаления тройка кнопок
        осталась последней.
        """
        window = self._window()
        layout = window.titleBar.hBoxLayout

        self.assertEqual(
            layout.indexOf(window.titleBar.buttons_host), layout.count() - 1
        )

    def test_version_stays_at_the_left_edge(self) -> None:
        """Название всплывало к середине после удаления поиска.

        Строка поиска держала раскладку: за ней шла растяжка, и без неё
        название оставалось между двумя пустотами.
        """
        window = self._window()
        title_bar = window.titleBar

        self.assertEqual(title_bar.hBoxLayout.indexOf(title_bar.title_label), 0)
        self.assertLess(title_bar.title_label.x(), 40)

    def test_mode_button_is_outlined_not_filled(self) -> None:
        """Заливка спорила бы с залитой вкладкой в той же строке."""
        from shell.theme import DARK, shell_qss

        block = shell_qss(DARK).split("QPushButton#net67AdvancedToggle {")[1]
        block = block[: block.index("}")]

        self.assertIn("border: 1px solid", block)
        self.assertIn("background: transparent", block)

    def test_mode_button_sinks_under_the_press(self) -> None:
        """Без отклика палец не чувствует, что попал, и человек жмёт дважды."""
        import time

        from shell.app_window import ADVANCED_TOGGLE_ROUTE_KEY

        window = self._window()
        window.navigationInterface.addItem(
            routeKey=ADVANCED_TOGGLE_ROUTE_KEY, text="Расширенные", selectable=False
        )
        _APP.processEvents()
        window._refresh_group_tabs()
        _APP.processEvents()

        window.advancedButton.pressed.emit()
        shifts = []
        deadline = time.time() + 0.3
        while time.time() < deadline:
            _APP.processEvents()
            shifts.append(window.advancedButton.contentsMargins().top())
            time.sleep(0.01)

        self.assertGreater(max(shifts), 0)

        window.advancedButton.released.emit()
        deadline = time.time() + 0.3
        while time.time() < deadline:
            _APP.processEvents()
            time.sleep(0.01)

        self.assertEqual(window.advancedButton.contentsMargins().top(), 0)

    def test_press_is_short_enough_to_keep_up_with_the_finger(self) -> None:
        """Дольше сотни миллисекунд читается уже как задержка."""
        from shell.app_window import AppShellWindow

        self.assertLessEqual(AppShellWindow.PRESS_MS, 120)
        self.assertLessEqual(AppShellWindow.PRESS_SHIFT_PX, 3)

    def test_every_clickable_thing_answers_the_press(self) -> None:
        from shell.theme import DARK, shell_qss

        qss = shell_qss(DARK)

        for selector in (
            "QPushButton#net67GroupTab:pressed",
            "QPushButton#net67PageTab:pressed",
            "QPushButton#net67NavItem:pressed",
            "QWidget PushButton:pressed",
            "QWidget PrimaryPushButton:pressed",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, qss)

    def test_tabs_live_before_the_window_buttons(self) -> None:
        """Иначе строка вкладок растащила бы «свернуть» и «закрыть»."""
        window = self._window()
        layout = window.titleBar.hBoxLayout

        self.assertLess(
            layout.indexOf(window.groupTabs),
            layout.indexOf(window.titleBar.buttons_host),
        )


if __name__ == "__main__":
    unittest.main()
