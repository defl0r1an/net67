"""Окно открывается развёрнутым, а мастер не задаёт лишних вопросов.

Два независимых требования, оба про первые секунды работы: приложение
должно сразу занять экран, а не открываться окошком, и не спрашивать то,
на что ответ уже известен.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _Host:
    """Минимальное окно: только то, что трогает restore_geometry."""

    def __init__(self) -> None:
        self.width_value = 0
        self.height_value = 0
        self.x_value = 0
        self.y_value = 0

    def resize(self, width, height) -> None:
        self.width_value, self.height_value = int(width), int(height)

    def move(self, x, y) -> None:
        self.x_value, self.y_value = int(x), int(y)

    def width(self):
        return self.width_value

    def height(self):
        return self.height_value

    def x(self):
        return self.x_value

    def y(self):
        return self.y_value


class StartMaximizedTests(unittest.TestCase):
    def test_flag_is_on(self) -> None:
        from ui.window_geometry_runtime import START_MAXIMIZED

        self.assertTrue(START_MAXIMIZED)

    def test_restore_requests_maximized_even_without_saved_flag(self) -> None:
        """Свежая установка: сохранённого maximized нет, окно всё равно во весь экран."""
        import ui.window_geometry_runtime as module

        runtime = module.WindowGeometryRuntime.__new__(module.WindowGeometryRuntime)
        runtime.host = _Host()
        runtime.min_width, runtime.min_height = 700, 520
        runtime.default_width, runtime.default_height = 1000, 950
        runtime._restore_in_progress = False
        runtime._last_normal_geometry = None
        runtime._last_non_minimized_zoomed = False
        runtime._pending_restore_maximized = False
        runtime.store = SimpleNamespace(
            load=lambda: module.StoredWindowGeometry(
                position=None,
                size=None,
                maximized=False,
            )
        )

        # QApplication в тесте нет: восстановление уходит в except и
        # применяет запасную ветку — она обязана вести себя так же.
        runtime.restore_geometry()

        self.assertTrue(runtime._pending_restore_maximized)
        self.assertTrue(runtime._last_non_minimized_zoomed)


class WizardStepsTests(unittest.TestCase):
    def test_services_question_is_gone(self) -> None:
        from wizard.plans import WIZARD_STEPS

        keys = [step.key for step in WIZARD_STEPS]

        # Вопрос «чем вы пользуетесь?» убран: обходы включаются все
        # сразу. Вопрос о провайдере, наоборот, добавлен — от него
        # зависит, какой пресет взять за основу.
        self.assertNotIn("services", keys)
        self.assertEqual(keys, ["provider", "detect", "startup"])

    def test_default_selection_covers_all_categories(self) -> None:
        """Раз спрашивать перестали — берём всё, иначе часть обходов пропала бы."""
        from wizard.plans import SERVICE_CHOICES, default_selection

        self.assertEqual(default_selection(), frozenset(c.key for c in SERVICE_CHOICES))

    def test_telegram_proxy_still_requested(self) -> None:
        """Прокси Telegram привязан к категории мессенджеров."""
        from wizard.plans import build_oneclick_request, default_selection

        self.assertTrue(build_oneclick_request(default_selection()).needs_telegram_proxy)

    def test_dialog_has_no_services_page(self) -> None:
        import inspect

        from wizard.ui import dialog

        source = inspect.getsource(dialog)

        self.assertNotIn("_build_services_page", source)
        self.assertNotIn("SERVICE_CHOICES", source)


class SimpleViewExitTests(unittest.TestCase):
    def test_switching_to_simple_view_returns_to_entry_page(self) -> None:
        """Без этого простой вид был ловушкой.

        Боковая панель прячется, а кнопка возврата есть только на главной
        странице управления. Нажав «Простой вид» из диагностики, человек
        оставался в разделе без единого способа выйти.
        """
        import inspect

        from ui.navigation import advanced_toggle

        toggle_source = inspect.getsource(advanced_toggle.toggle_advanced_mode)
        return_source = inspect.getsource(advanced_toggle._return_to_entry_page)

        self.assertIn("_return_to_entry_page", toggle_source)
        self.assertIn("if not next_value:", toggle_source)
        self.assertIn("get_mode_entry_page", return_source)
        self.assertIn("show_page", return_source)


if __name__ == "__main__":
    unittest.main()
