from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _FakePoint:
    def __init__(self, x: int, y: int) -> None:
        self._x = x
        self._y = y

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y


class _FakeRect:
    def __init__(self, left: int, top: int, width: int, height: int) -> None:
        self._left = left
        self._top = top
        self._width = width
        self._height = height

    def left(self) -> int:
        return self._left

    def right(self) -> int:
        return self._left + self._width - 1

    def top(self) -> int:
        return self._top

    def bottom(self) -> int:
        return self._top + self._height - 1

    def center(self) -> _FakePoint:
        return _FakePoint(self._left + self._width // 2, self._top + self._height // 2)


class _FakeScreen:
    def __init__(self, rect: _FakeRect) -> None:
        self._rect = rect

    def availableGeometry(self) -> _FakeRect:  # noqa: N802 (Qt-style API)
        return self._rect


class _FakeQApplication:
    fake_screens: list[_FakeScreen] = []

    @classmethod
    def screens(cls) -> list[_FakeScreen]:
        return cls.fake_screens

    @classmethod
    def primaryScreen(cls) -> _FakeScreen:  # noqa: N802 (Qt-style API)
        return cls.fake_screens[0]


class _FakeHost:
    def __init__(self, *, visible: bool = False, stale_maximized: bool = False) -> None:
        self.calls: list[tuple] = []
        self._visible = visible
        self._stale_maximized = stale_maximized
        self._width = 0
        self._height = 0

    def isVisible(self) -> bool:  # noqa: N802 (Qt-style API)
        return self._visible

    def isMaximized(self) -> bool:  # noqa: N802 (Qt-style API)
        return self._stale_maximized

    def isFullScreen(self) -> bool:  # noqa: N802 (Qt-style API)
        return False

    def windowState(self):  # noqa: N802 (Qt-style API)
        from PyQt6.QtCore import Qt

        if self._stale_maximized:
            return Qt.WindowState.WindowMaximized
        return Qt.WindowState.WindowNoState

    def setWindowState(self, state) -> None:  # noqa: N802 (Qt-style API)
        self.calls.append(("setWindowState", state))

    def resize(self, width: int, height: int) -> None:
        self.calls.append(("resize", width, height))
        self._width = width
        self._height = height

    def move(self, x: int, y: int) -> None:
        self.calls.append(("move", x, y))

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height


def _make_runtime(host, *, zoomed: bool, geometry):
    import ui.window_geometry_runtime as runtime_module

    runtime = runtime_module.WindowGeometryRuntime.__new__(runtime_module.WindowGeometryRuntime)
    runtime.host = host
    runtime.min_width = 600
    runtime.min_height = 500
    runtime._last_non_minimized_zoomed = zoomed
    runtime._last_normal_geometry = geometry
    runtime._restore_in_progress = False
    runtime.request_zoom_state = Mock()
    runtime.remembered_zoom_state = Mock(return_value=zoomed)
    return runtime


def _patch_screens(*rects: _FakeRect):
    import ui.window_geometry_runtime as runtime_module

    _FakeQApplication.fake_screens = [_FakeScreen(rect) for rect in rects]
    return patch.object(runtime_module, "QApplication", _FakeQApplication)


PRIMARY_SCREEN = _FakeRect(0, 0, 1920, 1040)


class ShowFromHiddenTests(unittest.TestCase):
    """AC1/AC2: скрытое maximized-окно не мутируется; normal — только геометрия; один запрос режима.

    Скрытому maximized-окну нельзя менять состояние или геометрию: Qt на
    Windows откладывает setWindowState() для скрытых окон, а resize()/move()
    пересинхронизируют Qt-состояние из нативного WS_MAXIMIZE — showMaximized()
    после этого становится no-op и окно показывается обрезанным.
    """

    def test_hidden_maximized_is_not_mutated_and_requests_maximized(self) -> None:
        host = _FakeHost(visible=False, stale_maximized=True)
        runtime = _make_runtime(host, zoomed=True, geometry=(100, 120, 900, 700))

        with _patch_screens(PRIMARY_SCREEN):
            runtime.show_from_hidden()

        self.assertEqual(host.calls, [])
        runtime.request_zoom_state.assert_called_once_with(True)

    def test_hidden_with_stale_maximized_flag_but_normal_target_skips_geometry(self) -> None:
        host = _FakeHost(visible=False, stale_maximized=True)
        runtime = _make_runtime(host, zoomed=False, geometry=(100, 120, 900, 700))

        with _patch_screens(PRIMARY_SCREEN):
            runtime.show_from_hidden()

        self.assertEqual(host.calls, [])
        runtime.request_zoom_state.assert_called_once_with(False)

    def test_hidden_normal_restores_same_geometry_and_requests_normal(self) -> None:
        host = _FakeHost(visible=False)
        runtime = _make_runtime(host, zoomed=False, geometry=(50, 60, 800, 650))

        with _patch_screens(PRIMARY_SCREEN):
            runtime.show_from_hidden()

        self.assertIn(("resize", 800, 650), host.calls)
        self.assertIn(("move", 50, 60), host.calls)
        self.assertNotIn("setWindowState", [call[0] for call in host.calls])
        runtime.request_zoom_state.assert_called_once_with(False)

    def test_geometry_smaller_than_minimum_is_clamped(self) -> None:
        host = _FakeHost(visible=False)
        runtime = _make_runtime(host, zoomed=False, geometry=(50, 60, 300, 200))

        with _patch_screens(PRIMARY_SCREEN):
            runtime.show_from_hidden()

        self.assertIn(("resize", 600, 500), host.calls)

    def test_target_zoom_state_is_captured_before_window_mutations(self) -> None:
        """AC1: целевой режим снимается ДО мутаций — гонка с обработчиками state-change не влияет."""
        host = _FakeHost(visible=False)
        runtime = _make_runtime(host, zoomed=False, geometry=(100, 120, 900, 700))

        original_resize = host.resize

        def resize_with_side_effect(width: int, height: int) -> None:
            original_resize(width, height)
            runtime._last_non_minimized_zoomed = True

        host.resize = resize_with_side_effect

        with _patch_screens(PRIMARY_SCREEN):
            runtime.show_from_hidden()

        runtime.request_zoom_state.assert_called_once_with(False)

    def test_offscreen_remembered_position_is_recentered_on_primary_screen(self) -> None:
        """AC3: позиция вне всех экранов — окно центрируется на primary."""
        host = _FakeHost(visible=False)
        runtime = _make_runtime(host, zoomed=False, geometry=(-5000, -5000, 800, 650))

        with _patch_screens(PRIMARY_SCREEN):
            runtime.show_from_hidden()

        expected_x = PRIMARY_SCREEN.center().x() - 800 // 2
        expected_y = PRIMARY_SCREEN.center().y() - 650 // 2
        self.assertIn(("move", expected_x, expected_y), host.calls)

    def test_visible_window_only_reasserts_mode_without_geometry_changes(self) -> None:
        """AC5: видимое окно — только повторное подтверждение режима, без resize/move/setWindowState."""
        host = _FakeHost(visible=True)
        runtime = _make_runtime(host, zoomed=True, geometry=(100, 120, 900, 700))

        with _patch_screens(PRIMARY_SCREEN):
            runtime.show_from_hidden()

        self.assertEqual(host.calls, [])
        runtime.request_zoom_state.assert_called_once_with(True)

    def test_missing_remembered_geometry_still_requests_mode(self) -> None:
        host = _FakeHost(visible=False)
        runtime = _make_runtime(host, zoomed=False, geometry=None)

        with _patch_screens(PRIMARY_SCREEN):
            runtime.show_from_hidden()

        self.assertEqual(host.calls, [])
        runtime.request_zoom_state.assert_called_once_with(False)


class SharedVisibilityHelperTests(unittest.TestCase):
    """AC3: проверка видимости — общий хелпер, без дублирования цикла по экранам."""

    def test_restore_geometry_uses_shared_position_helper(self) -> None:
        import inspect

        import ui.window_geometry_runtime as runtime_module

        restore_source = inspect.getsource(runtime_module.WindowGeometryRuntime.restore_geometry)
        self.assertIn("_position_visible_on_any_screen", restore_source)

        apply_source = inspect.getsource(
            runtime_module.WindowGeometryRuntime._apply_remembered_normal_geometry
        )
        self.assertIn("_position_visible_on_any_screen", apply_source)

    def test_position_helper_detects_visibility(self) -> None:
        import ui.window_geometry_runtime as runtime_module

        with _patch_screens(PRIMARY_SCREEN, _FakeRect(1920, 0, 1920, 1040)):
            helper = runtime_module.WindowGeometryRuntime._position_visible_on_any_screen
            self.assertTrue(helper(100, 100))
            self.assertTrue(helper(2500, 300))
            self.assertFalse(helper(-5000, -5000))


class ShowWindowAdapterContractTests(unittest.TestCase):
    """AC4: show_window() — тонкий делегат без танца show()/showNormal()/re-maximize."""

    ADAPTER_PATH = PROJECT_SRC / "ui" / "window_adapter.py"

    def test_show_window_delegates_to_show_from_hidden(self) -> None:
        source = self.ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("show_from_hidden", source)
        self.assertIn("raise_()", source)
        self.assertIn("activateWindow()", source)

    def test_show_window_has_no_geometry_dance(self) -> None:
        source = self.ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("showNormal", source)
        self.assertNotIn("restore_geometry", source)
        self.assertNotIn("_restore_geometry_before_hidden_show", source)
        self.assertNotIn("remembered_zoom_state", source)


if __name__ == "__main__":
    unittest.main()
