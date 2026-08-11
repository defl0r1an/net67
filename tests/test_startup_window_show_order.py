"""Окно выходит на экран один раз и сразу готовым.

Жалоба звучала так: «маленькое чёрное окно при запуске», и держалась она
несколько заходов, потому что я лечил не ту причину.

Причина оказалась в порядке. Окно показывалось до сборки интерфейса —
ради ощущения быстрого запуска, — а Windows создаёт и закрашивает окно
фоном оконного класса раньше, чем Qt успевает нарисовать первый кадр. До
сборки у окна ещё и размер по умолчанию. Отсюда ровно то, что человек и
описал: маленький чёрный прямоугольник на долю секунды.

Прозрачность не лечит: setWindowOpacity применяется к уже созданному
окну. Лечит только отсутствие окна до готовности.

Второй кадр брался из разворота. `showEvent` разворачивал окно на весь
экран, то есть уже на экране: сначала сохранённый размер, следом прыжок.
Пока показ был прозрачным, прыжок прятался вместе с ошибкой; убери
прозрачность — и он вылезет вместо неё.

Здесь закреплены оба правила. Проверки читают исходный код, потому что
речь именно о порядке вызовов, а не о результате: собрать настоящее окно
в тестах нельзя, а порядок ломается тихо и незаметно.
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


def _code_only(source: str) -> str:
    """Исходник без строк документации.

    Проверки на «этого вызова здесь быть не должно» иначе спотыкаются о
    комментарий, который объясняет, почему вызова быть не должно.
    """
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if isinstance(first.value.value, str):
                    node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


class ShowOrderTests(unittest.TestCase):
    def test_window_is_not_shown_before_ui_is_built(self) -> None:
        """Показ убран из сборки рантайма — там окно ещё пустое."""
        from main import window_runtime_setup

        source = inspect.getsource(window_runtime_setup.attach_app_runtime_to_window)

        self.assertNotIn("show_initial_window_if_needed(", source)
        self.assertIn("start_window_deferred_init(window)", source)

    def test_deferred_init_shows_the_window_after_build_ui(self) -> None:
        from main.window_startup import WindowStartupMixin

        source = inspect.getsource(WindowStartupMixin._deferred_init)

        self.assertIn("self.build_ui(", source)
        self.assertIn("self._reveal_when_ready()", source)
        self.assertLess(
            source.index("self.build_ui("),
            source.rindex("self._reveal_when_ready()"),
            "окно должно показываться после сборки интерфейса, а не до",
        )

    def test_failed_build_still_shows_a_window(self) -> None:
        """Иначе поломка сборки оставляет процесс без единого окна."""
        from main.window_startup import WindowStartupMixin

        source = inspect.getsource(WindowStartupMixin._deferred_init)
        after_failure = source[source.index("build_ui failed") :]

        self.assertIn("self._reveal_when_ready()", after_failure)

    def test_reveal_goes_through_the_single_show_point(self) -> None:
        from main.window_startup import WindowStartupMixin

        source = inspect.getsource(WindowStartupMixin._reveal_when_ready)

        self.assertIn("show_initial_window_if_needed", source)

    def test_show_does_not_rely_on_transparency(self) -> None:
        """setWindowOpacity(0) не прячет первый кадр — он уже нарисован."""
        from main import window_startup_signal_setup

        source = inspect.getsource(window_startup_signal_setup.show_initial_window_if_needed)

        self.assertNotIn("setWindowOpacity(0", _code_only(source))
        self.assertIn("prepare_window_for_show(window)", source)

    def test_preparation_happens_before_show(self) -> None:
        from main import window_startup_signal_setup

        source = inspect.getsource(window_startup_signal_setup.show_initial_window_if_needed)

        self.assertLess(
            source.index("prepare_window_for_show(window)"),
            source.index("window.show()"),
        )

    def test_preparation_applies_the_maximized_state(self) -> None:
        from main import window_startup_signal_setup

        source = inspect.getsource(window_startup_signal_setup.prepare_window_for_show)

        self.assertIn("apply_pending_maximized_before_show", source)

    def test_wizard_path_also_prepares_before_showing(self) -> None:
        """Первый запуск открывает окно своим путём — правило то же."""
        from main import post_startup_wizard

        source = inspect.getsource(post_startup_wizard._reveal_main_window)

        self.assertIn("prepare_window_for_show(window)", source)
        self.assertNotIn("setWindowOpacity(0", source)
        self.assertLess(
            source.index("prepare_window_for_show(window)"),
            source.index("window.show()"),
        )


class FakeHost:
    """Ровно та часть окна, которую трогает разворот до показа."""

    def __init__(self, *, visible: bool = False) -> None:
        from PyQt6.QtCore import Qt

        self._visible = bool(visible)
        self._state = Qt.WindowState.WindowNoState
        self.shown_maximized = False

    def isVisible(self) -> bool:  # noqa: N802 (Qt API)
        return self._visible

    def windowState(self):  # noqa: N802 (Qt API)
        return self._state

    def setWindowState(self, state) -> None:  # noqa: N802 (Qt API)
        self._state = state

    def showMaximized(self) -> None:  # noqa: N802 (Qt API)
        self.shown_maximized = True
        self._visible = True


class PendingMaximizeTests(unittest.TestCase):
    """Поведение разворота до показа — без Qt-приложения и без окна."""

    def _runtime(self, host, *, pending: bool, applied: bool = False):
        from ui.window_geometry_runtime import WindowGeometryRuntime

        runtime = object.__new__(WindowGeometryRuntime)
        runtime.host = host
        runtime._pending_restore_maximized = pending
        runtime._applied_saved_maximize_state = applied
        runtime._last_non_minimized_zoomed = False
        return runtime

    def test_hidden_window_gets_the_state_without_being_shown(self) -> None:
        from PyQt6.QtCore import Qt

        host = FakeHost()
        runtime = self._runtime(host, pending=True)

        self.assertTrue(runtime.apply_pending_maximized_before_show())
        self.assertTrue(host.windowState() & Qt.WindowState.WindowMaximized)
        # Главное: окно не показано. Показ — дело вызывающего кода.
        self.assertFalse(host.shown_maximized)
        self.assertFalse(host.isVisible())

    def test_it_does_not_run_twice(self) -> None:
        host = FakeHost()
        runtime = self._runtime(host, pending=True)

        runtime.apply_pending_maximized_before_show()

        self.assertFalse(runtime.apply_pending_maximized_before_show())

    def test_visible_window_is_left_to_the_usual_path(self) -> None:
        """У показанного окна разворот отрабатывает showEvent."""
        host = FakeHost(visible=True)
        runtime = self._runtime(host, pending=True)

        self.assertFalse(runtime.apply_pending_maximized_before_show())

    def test_nothing_pending_means_nothing_happens(self) -> None:
        from PyQt6.QtCore import Qt

        host = FakeHost()
        runtime = self._runtime(host, pending=False)

        self.assertFalse(runtime.apply_pending_maximized_before_show())
        self.assertFalse(host.windowState() & Qt.WindowState.WindowMaximized)

    def test_minimized_flag_is_dropped(self) -> None:
        """Свёрнутое и развёрнутое одновременно — окно не откроется."""
        from PyQt6.QtCore import Qt

        host = FakeHost()
        host.setWindowState(Qt.WindowState.WindowMinimized)
        runtime = self._runtime(host, pending=True)

        runtime.apply_pending_maximized_before_show()

        self.assertFalse(host.windowState() & Qt.WindowState.WindowMinimized)
        self.assertTrue(host.windowState() & Qt.WindowState.WindowMaximized)

    def test_showEvent_path_is_a_no_op_afterwards(self) -> None:
        """Разворот уже применён — повторять его на экране нечего."""
        host = FakeHost()
        runtime = self._runtime(host, pending=True)

        runtime.apply_pending_maximized_before_show()
        runtime.apply_saved_maximized_state_if_needed()

        self.assertFalse(host.shown_maximized)


if __name__ == "__main__":
    unittest.main()
