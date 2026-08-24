"""Никаких мелькающих окон при запуске.

Жалоба была такая: приложение стартует не из трея, окно на секунду
выскакивает, а если это первый запуск — следом его накрывает мастер. И
если успеть нажать на выбор провайдера в этот промежуток, мастер
закрывался вместе с нажатием.

Причина в порядке действий. Окно показывалось сразу, как только собран
интерфейс, а мастер открывался отдельным таймером через 1200 мс. Между
этими двумя событиями человек видел готовое окно, успевал к нему
потянуться — и получал модальный диалог поверх своего клика.

Теперь обычный путь показа на первом запуске молчит, а окно открывает
сам мастер — непосредственно перед собой, в соседнем кадре. Промежутка,
в который можно попасть мышью, не остаётся.

Порядок «сначала окно, потом мастер» здесь принципиален, и это вторая
половина истории. Мастер qfluentwidgets — диалог с маской: он читает
размеры родителя в момент показа и запоминает их. Открытый над
спрятанным окном, он получал размеры, которых на экране никогда не
было, — затемнение накрывало левый верхний угол, а сам диалог стоял не
по центру.
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _Window:
    """Окно ровно в том объёме, в каком его трогает запуск."""

    def __init__(self, *, start_in_tray: bool = False, visible: bool = False):
        self.start_in_tray = start_in_tray
        self._visible = visible
        self.show = Mock(side_effect=self._on_show)
        self.raise_ = Mock()
        self.activateWindow = Mock()
        # Двойник обязан уметь то же, что настоящее окно.
        #
        # Этих трёх методов здесь не было, и двойник молча ронял показ на
        # AttributeError — то есть проверял сам себя, а не приложение.
        self.setWindowOpacity = Mock()
        self.ensurePolished = Mock()
        self.layout = Mock(return_value=None)
        self.window_geometry_runtime = None

    def _on_show(self) -> None:
        self._visible = True

    def isVisible(self) -> bool:  # noqa: N802 (сигнатура Qt)
        return self._visible


class _Host:
    def __init__(self, window):
        self._window = window


class InitialShowTests(unittest.TestCase):
    """Кто и когда показывает окно в обычном запуске."""

    def _show(self, window, *, wizard_pending: bool):
        from main import window_startup_signal_setup as setup

        original = setup.is_first_run_wizard_pending
        setup.is_first_run_wizard_pending = lambda: wizard_pending
        try:
            setup.show_initial_window_if_needed(window)
        finally:
            setup.is_first_run_wizard_pending = original

    def test_ordinary_start_shows_the_window(self) -> None:
        window = _Window()

        self._show(window, wizard_pending=False)

        window.show.assert_called_once()

    def test_first_run_keeps_the_window_hidden(self) -> None:
        """То самое мелькание: окно выскакивало перед мастером."""
        window = _Window()

        self._show(window, wizard_pending=True)

        window.show.assert_not_called()

    def test_tray_start_shows_nothing(self) -> None:
        window = _Window(start_in_tray=True)

        self._show(window, wizard_pending=False)

        window.show.assert_not_called()

    def test_already_visible_window_is_not_shown_twice(self) -> None:
        window = _Window(visible=True)

        self._show(window, wizard_pending=False)

        window.show.assert_not_called()

    def test_broken_check_does_not_leave_the_person_without_a_window(self) -> None:
        """Поломка в настройках не повод прятать интерфейс совсем."""
        from main import window_startup_signal_setup as setup

        def explode():
            raise OSError("настройки недоступны")

        original = setup.is_wizard_needed if hasattr(setup, "is_wizard_needed") else None
        _ = original

        # Проверяем саму обёртку: внутри она ловит любое исключение.
        source = inspect.getsource(setup.is_first_run_wizard_pending)
        self.assertIn("except Exception", source)
        self.assertIn("return False", source)


class WizardRevealTests(unittest.TestCase):
    """Мастер обязан открыть окно за собой."""

    def _reveal(self, window):
        from main.post_startup_wizard import _reveal_main_window

        _reveal_main_window(_Host(window))

    def test_window_appears_after_the_wizard(self) -> None:
        window = _Window()

        self._reveal(window)

        window.show.assert_called_once()
        window.activateWindow.assert_called_once()

    def test_tray_start_stays_in_the_tray(self) -> None:
        """В трее окна и не должно быть: человек откроет его из значка."""
        window = _Window(start_in_tray=True)

        self._reveal(window)

        window.show.assert_not_called()

    def test_visible_window_is_left_alone(self) -> None:
        window = _Window(visible=True)

        self._reveal(window)

        window.show.assert_not_called()

    def test_missing_window_is_not_an_error(self) -> None:
        from main.post_startup_wizard import _reveal_main_window

        _reveal_main_window(_Host(None))


class DialogGeometryTests(unittest.TestCase):
    """Затемнение мастера должно накрывать окно целиком.

    На снимке было видно обратное: тёмный прямоугольник в левом верхнем
    углу и диалог не по центру. Причина в том, что диалог с маской
    запоминает размеры родителя в момент создания, а на первом запуске
    окно в этот момент ещё не показано и раскладку не считало.
    """

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:  # pragma: no cover - среда без Qt
            raise unittest.SkipTest(f"Qt недоступен: {exc}") from exc
        cls._app = QApplication.instance() or QApplication([])

    def _pair(self, *, show_window_first: bool):
        import qfluentwidgets

        from shell.app_window import AppShellWindow
        from wizard.ui.dialog import WizardDialog

        qfluentwidgets.setTheme(qfluentwidgets.Theme.DARK)
        window = AppShellWindow()
        window.resize(1200, 900)
        self.addCleanup(window.deleteLater)

        if show_window_first:
            window.show()
            self._settle()

        dialog = WizardDialog(window)
        self.addCleanup(dialog.deleteLater)

        if not show_window_first:
            window.show()
            self._settle()

        dialog.show()
        self._settle()
        return window, dialog

    def _settle(self) -> None:
        for _ in range(3):
            self._app.processEvents()

    def test_mask_covers_the_whole_window(self) -> None:
        window, dialog = self._pair(show_window_first=True)

        self.assertEqual(dialog.size(), window.size())

    def test_mask_is_right_even_if_the_dialog_was_built_earlier(self) -> None:
        """Ровно случай первого запуска: диалог создан до показа окна."""
        window, dialog = self._pair(show_window_first=False)

        self.assertEqual(dialog.size(), window.size())

    def test_dialog_sits_in_the_middle(self) -> None:
        window, dialog = self._pair(show_window_first=True)
        inner = dialog.widget

        centre_x = inner.x() + inner.width() // 2
        centre_y = inner.y() + inner.height() // 2

        self.assertLessEqual(abs(centre_x - window.width() // 2), 2)
        self.assertLessEqual(abs(centre_y - window.height() // 2), 2)

    def test_mask_catches_up_when_the_window_grows_after_the_dialog(self) -> None:
        """Ровно случай первого запуска, и он не ловился двумя правками.

        Мастер открывается над окном размера простого вида, а геометрия
        восстанавливается из настроек позже — окно вырастает, маска
        остаётся прежней и накрывает угол.

        Ловим сторожем по таймеру, а не фильтром событий: фильтр ставит
        библиотека, порядок доставки нам не подчиняется, и две попытки
        поймать Resize через него результата не дали.
        """
        import time

        window, dialog = self._pair(show_window_first=True)
        window.resize(1439, 1028)

        deadline = time.time() + 1.0
        while time.time() < deadline and dialog.size() != window.size():
            self._app.processEvents()
            time.sleep(0.02)

        self.assertEqual(dialog.size(), window.size())

    def test_watchdog_stops_with_the_dialog(self) -> None:
        """Пять кадров в секунду впустую — мелочь, но бессмысленная."""
        window, dialog = self._pair(show_window_first=True)
        _ = window

        dialog.hide()
        self._app.processEvents()

        self.assertFalse(dialog._mask_watchdog.isActive())

    def test_mask_follows_a_resized_window(self) -> None:
        """Диалог открывают и на развёрнутом окне, и на восстановленном."""
        window, dialog = self._pair(show_window_first=True)

        window.resize(800, 600)
        self._settle()
        dialog.hide()
        dialog.show()
        self._settle()

        self.assertEqual(dialog.size(), window.size())


class WiringTests(unittest.TestCase):
    def test_reveal_runs_even_if_the_wizard_fails(self) -> None:
        """Иначе приложение осталось бы работать без единого окна.

        Мастер может упасть, его могут закрыть крестиком — окно всё
        равно должно открыться, потому что показ был отложен ради него.
        """
        from main import post_startup_wizard

        source = inspect.getsource(post_startup_wizard.install_first_run_wizard)

        self.assertIn("finally:", source)
        self.assertIn("_reveal_main_window", source)

    def test_wizard_no_longer_waits_a_second_and_a_half(self) -> None:
        """Задержка была нужна, пока окно показывалось раньше мастера.

        Теперь ждать нечего, а полторы секунды пустого экрана человек
        читает как «программа не запустилась».
        """
        from main.post_startup_wizard import WIZARD_DELAY_MS

        self.assertLessEqual(WIZARD_DELAY_MS, 400)

    def test_window_opens_before_the_wizard_not_after(self) -> None:
        """Диалог с маской читает размеры родителя при показе.

        У спрятанного окна раскладка ещё не отработала, и мастер получал
        размеры, которых на экране никогда не было. Поэтому окно
        открывается первым, а мастер накрывает его в соседнем кадре.
        """
        from main import post_startup_wizard

        source = inspect.getsource(post_startup_wizard.install_first_run_wizard)

        self.assertLess(
            source.index("_reveal_main_window(startup_host)"),
            source.index("show_wizard_if_needed(window)"),
        )

    def test_startup_asks_about_the_wizard_before_showing(self) -> None:
        from main import window_startup_signal_setup as setup

        source = inspect.getsource(setup.show_initial_window_if_needed)

        self.assertIn("is_first_run_wizard_pending", source)
        self.assertLess(
            source.index("is_first_run_wizard_pending"), source.index("window.show()")
        )


if __name__ == "__main__":
    unittest.main()
