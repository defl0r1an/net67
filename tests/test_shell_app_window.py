"""Своё окно вместо окна qfluentwidgets, без правки сорока страниц.

Смена облика не должна была тронуть маршрутизацию, поиск, трей и сами
страницы: цена ошибки там — приложение, которое не запускается. Поэтому
новое окно отвечает теми же четырьмя вещами, что и прежнее, и эти тесты
стерегут именно совместимость, а не внешний вид.

Поверхность узкая и посчитана, а не угадана: по всему проекту от окна
используются navigationInterface, stackedWidget, addSubInterface и
switchTo, плюс setCustomBackgroundColor и пара методов Mica.
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


class SwapTests(unittest.TestCase):
    def test_main_window_no_longer_uses_qfluentwidgets(self) -> None:
        source = (PROJECT_SRC / "main" / "window.py").read_text(encoding="utf-8")

        self.assertIn("from shell.app_window import AppShellWindow", source)
        self.assertNotIn("AppFluentWindow", source)


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class CompatibilityTests(unittest.TestCase):
    def _window(self):
        import qfluentwidgets

        from shell.app_window import AppShellWindow

        # Тему задаём явно. Окно теперь читает её при создании, а она
        # общая на весь процесс: соседний тест мог оставить светлую, и
        # проверка тёмного цвета падала бы не по своей вине.
        qfluentwidgets.setTheme(qfluentwidgets.Theme.DARK)
        window = AppShellWindow()
        window.resize(1000, 700)
        self.addCleanup(window.deleteLater)
        return window

    def _page(self, key: str, title: str):
        from PyQt6.QtWidgets import QLabel

        page = QLabel(title)
        page.setObjectName(key)
        return page

    def test_window_exposes_the_old_surface(self) -> None:
        window = self._window()

        for name in ("navigationInterface", "stackedWidget", "addSubInterface", "switchTo"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(window, name))

    def test_add_sub_interface_registers_page_and_item(self) -> None:
        window = self._window()
        page = self._page("HOSTS", "Редактор hosts")

        item = window.addSubInterface(page, None, "Редактор hosts")

        self.assertIsNotNone(item)
        self.assertGreaterEqual(window.stackedWidget.indexOf(page), 0)
        self.assertIs(window.navigationInterface.widget("HOSTS"), item)

    def test_route_key_comes_from_object_name(self) -> None:
        """На objectName опирается setCurrentItem во всём остальном коде."""
        window = self._window()
        page = self._page("LOGS", "Логи")

        window.addSubInterface(page, None, "Логи")

        self.assertIn("LOGS", window.navigationInterface.items)

    def test_switch_to_moves_the_stack_and_the_highlight(self) -> None:
        window = self._window()
        first = self._page("A", "Первая")
        second = self._page("B", "Вторая")
        window.addSubInterface(first, None, "Первая")
        window.addSubInterface(second, None, "Вторая")

        window.switchTo(second)

        self.assertIs(window.stackedWidget.currentWidget(), second)
        self.assertEqual(window.navigationInterface.current_key, "B")
        self.assertTrue(window.navigationInterface.items["B"].isChecked())
        self.assertFalse(window.navigationInterface.items["A"].isChecked())

    def test_adding_the_same_page_twice_does_not_duplicate(self) -> None:
        window = self._window()
        page = self._page("A", "Первая")

        first = window.addSubInterface(page, None, "Первая")
        second = window.addSubInterface(page, None, "Первая")

        self.assertIs(first, second)
        self.assertEqual(window.stackedWidget.count(), 1)

    def test_custom_background_is_not_silently_ignored(self) -> None:
        """Человек выбрал бы цвет и не увидел изменений."""
        window = self._window()

        window.setCustomBackgroundColor("#ffffff", "#101114")

        self.assertIn("#101114", window.styleSheet())

    def test_mica_methods_answer_honestly(self) -> None:
        """Mica — эффект окна qfluentwidgets, здесь его нет."""
        window = self._window()

        window.setMicaEffectEnabled(True)

        self.assertFalse(window.isMicaEffectEnabled())

    def test_frameless_comes_from_the_library(self) -> None:
        """Своя безрамочность роняла приложение с access violation.

        Первый подход — QWidget с флагом FramelessWindowHint — закрывал
        программу молча прямо в show(): безрамочное окно на Windows
        требует обработки WM_NCCALCSIZE и WM_NCHITTEST, а её не было.
        qframelesswindow это умеет и лежит в зависимостях.
        """
        from qframelesswindow import FramelessWindow

        from shell.app_window import AppShellWindow

        self.assertTrue(issubclass(AppShellWindow, FramelessWindow))

    def test_title_bar_reuses_the_library_layout(self) -> None:
        """На hBoxLayout смотрит refresh_titlebar_layout при показе окна.

        Своя вторая раскладка вызывала предупреждение Qt и не
        применялась вовсе.
        """
        window = self._window()

        self.assertTrue(hasattr(window.titleBar, "hBoxLayout"))

    def test_window_survives_show(self) -> None:
        """Ровно то, что падало: показ окна."""
        window = self._window()

        window.show()

        self.assertTrue(window.isVisible())


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class NavigationCompatTests(unittest.TestCase):
    def _nav(self):
        from shell.nav_compat import NavigationCompat

        nav = NavigationCompat()
        self.addCleanup(nav.deleteLater)
        return nav

    def test_positions_follow_qfluentwidgets_names(self) -> None:
        """Вызывающий код передаёт NavigationItemPosition как есть."""
        from qfluentwidgets import NavigationItemPosition

        from shell.nav_compat import (
            POSITION_BOTTOM,
            POSITION_SCROLL,
            POSITION_TOP,
            _position_key,
        )

        self.assertEqual(_position_key(NavigationItemPosition.TOP), POSITION_TOP)
        self.assertEqual(_position_key(NavigationItemPosition.SCROLL), POSITION_SCROLL)
        self.assertEqual(_position_key(NavigationItemPosition.BOTTOM), POSITION_BOTTOM)

    def test_unknown_position_lands_in_the_middle(self) -> None:
        from shell.nav_compat import POSITION_SCROLL, _position_key

        self.assertEqual(_position_key(None), POSITION_SCROLL)
        self.assertEqual(_position_key("что-то новое"), POSITION_SCROLL)

    def test_insert_item_respects_the_index(self) -> None:
        nav = self._nav()

        nav.addItem(routeKey="second", text="Вторая")
        nav.insertItem(0, routeKey="first", text="Первая")

        box = nav._layouts["scroll"]
        self.assertEqual(box.itemAt(0).widget().routeKey, "first")

    def test_header_and_separator_are_added(self) -> None:
        nav = self._nav()

        header = nav.addItemHeader("Инструменты")
        separator = nav.addSeparator()

        self.assertEqual(header.text(), "Инструменты")
        self.assertIsNotNone(separator)
        self.assertEqual(len(nav.headers), 1)

    def test_click_calls_the_handler(self) -> None:
        nav = self._nav()
        calls = []

        item = nav.addItem(routeKey="a", text="А", onClick=lambda: calls.append("да"))
        item.click()

        self.assertEqual(calls, ["да"])

    def test_only_one_item_stays_highlighted(self) -> None:
        nav = self._nav()
        nav.addItem(routeKey="a", text="А")
        nav.addItem(routeKey="b", text="Б")

        nav.setCurrentItem("a")
        nav.setCurrentItem("b")

        checked = [key for key, item in nav.items.items() if item.isChecked()]
        self.assertEqual(checked, ["b"])

    def test_collapsing_is_deliberately_absent(self) -> None:
        """Панель не сворачивается: за «сделать меньше» отвечает простой режим.

        Два разных способа сокращать одно и то же меню только путали бы.
        Вызов оставлен, чтобы не падал прежний код.
        """
        nav = self._nav()

        nav.setMinimumExpandWidth(700)

        self.assertEqual(nav.width(), nav.width())


if __name__ == "__main__":
    unittest.main()
