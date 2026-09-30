"""Метка «Работает / Остановлен» в заголовке окна net67.

Из zapret 21.1.6.45: включить или выключить обход можно из любого
раздела, не возвращаясь на главную. В net67 метка встаёт в свой
заголовок — слева от колокольчика (shell/launch_badge.py).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget  # noqa: E402

from app.state_store import MainWindowStateStore  # noqa: E402
from shell.launch_badge import bind_launch_title_badge  # noqa: E402
from ui.launch_title_badge import LaunchTitleBadge, build_launch_badge_view  # noqa: E402


class LaunchBadgeViewTests(unittest.TestCase):
    def test_texts_follow_phase(self) -> None:
        cases = {
            "running": ("Работает", "net67 v2 работает · нажмите, чтобы остановить"),
            "starting": ("Запуск…", "net67 v2 запускается · нажмите, чтобы остановить"),
            "autostart_pending": ("Запуск…", "net67 v2 запускается · нажмите, чтобы остановить"),
            "stopping": ("Остановка…", "net67 v2 останавливается…"),
            "stopped": ("Остановлен", "net67 v2 остановлен · нажмите, чтобы запустить"),
            "failed": ("Ошибка", "Ошибка запуска net67 v2 · нажмите, чтобы попробовать снова"),
        }
        for phase, (text, tooltip) in cases.items():
            with self.subTest(phase=phase):
                view = build_launch_badge_view(phase=phase, launch_method="zapret2_mode", language="ru")
                self.assertEqual((view.text, view.tooltip), (text, tooltip))


class _Window(QWidget):
    """Заголовок net67 в миниатюре: панель, её раскладка, колокольчик в конце."""

    def __init__(self) -> None:
        super().__init__()
        self.titleBar = QWidget(self)
        self.titleBar.hBoxLayout = QHBoxLayout(self.titleBar)
        self.titleBar.hBoxLayout.addWidget(QPushButton("Обход", self.titleBar))
        self.notificationBell = QPushButton("колокольчик", self.titleBar)
        self.titleBar.hBoxLayout.addWidget(self.notificationBell)


class LaunchTitleBadgeBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _window(self) -> _Window:
        window = _Window()
        self.addCleanup(window.deleteLater)
        return window

    @staticmethod
    def _set_phase(store: MainWindowStateStore, phase: str) -> None:
        store.update(launch_phase=phase, launch_running=phase == "running", launch_method="zapret2_mode")

    def test_badge_follows_launch_phase(self) -> None:
        window = self._window()
        store = MainWindowStateStore()
        badge = bind_launch_title_badge(window, store, Mock())

        self.assertEqual(badge.text(), "Остановлен")
        self._set_phase(store, "starting")
        self.assertEqual(badge.text(), "Запуск…")
        self._set_phase(store, "running")
        self.assertEqual(badge.text(), "Работает")
        self.assertIn("остановить", badge.toolTip())

    def test_click_toggles_through_launch_control(self) -> None:
        window = self._window()
        launch_control = Mock()
        badge = bind_launch_title_badge(window, MainWindowStateStore(), launch_control)

        badge.click()

        launch_control.toggle.assert_called_once_with()

    def test_badge_is_disabled_while_stopping(self) -> None:
        window = self._window()
        store = MainWindowStateStore()
        badge = bind_launch_title_badge(window, store, Mock())

        self._set_phase(store, "stopping")
        self.assertFalse(badge.isEnabled())
        self._set_phase(store, "stopped")
        self.assertTrue(badge.isEnabled())

    def test_badge_shows_one_button_steps_instead_of_running(self) -> None:
        # На сборке: кнопка простого вида — «Запускаем… Подготовка», а метка
        # уже «Работает»: обход поднят, но кнопка ещё проверяет.
        window = self._window()
        store = MainWindowStateStore()
        badge = bind_launch_title_badge(window, store, Mock())

        store.update(oneclick_phase="preparing")
        self.assertEqual(badge.text(), "Запуск…")
        self._set_phase(store, "running")
        store.update(oneclick_phase="checking")
        self.assertEqual(badge.text(), "Проверка…")
        # Посреди шагов кнопки выключать нечем — цепочка осталась бы на полпути.
        self.assertFalse(badge.isEnabled())

        store.update(oneclick_phase="running")
        self.assertEqual(badge.text(), "Работает")
        self.assertTrue(badge.isEnabled())

    def test_badge_shows_oneclick_steps_instead_of_running(self) -> None:
        # Обход уже поднят («running»), а «одна кнопка» ещё проверяет:
        # метка писала «Работает», кнопка — «Запускаем… Проверка».
        window = self._window()
        launch_control = Mock()
        store = MainWindowStateStore()
        badge = bind_launch_title_badge(window, store, launch_control)
        self._set_phase(store, "running")

        store.update(oneclick_phase="preparing")
        self.assertEqual(badge.text(), "Запуск…")
        store.update(oneclick_phase="checking")
        self.assertEqual(badge.text(), "Проверка…")
        # Посреди шагов кнопки выключать обход нельзя.
        self.assertFalse(badge.isEnabled())
        badge.click()
        launch_control.toggle.assert_not_called()

        store.update(oneclick_phase="running")
        self.assertEqual(badge.text(), "Работает")
        self.assertTrue(badge.isEnabled())

    def test_badge_sits_left_of_the_bell(self) -> None:
        window = self._window()
        badge = bind_launch_title_badge(window, MainWindowStateStore(), Mock())
        layout = window.titleBar.hBoxLayout

        self.assertEqual(layout.indexOf(badge) + 1, layout.indexOf(window.notificationBell))

    def test_no_badge_without_launch_control(self) -> None:
        window = self._window()
        self.assertIsNone(bind_launch_title_badge(window, MainWindowStateStore(), None))
        self.assertIsNone(window.titleBar.findChild(LaunchTitleBadge))

    def test_binding_twice_reuses_single_badge(self) -> None:
        window = self._window()
        store = MainWindowStateStore()
        first = bind_launch_title_badge(window, store, Mock())
        second = bind_launch_title_badge(window, store, Mock())

        self.assertIs(first, second)
        self.assertEqual(len(window.titleBar.findChildren(LaunchTitleBadge)), 1)


if __name__ == "__main__":
    unittest.main()
