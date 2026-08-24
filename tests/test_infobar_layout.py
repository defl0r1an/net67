from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

from PyQt6.QtCore import Qt


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


def _measure_by_chars(text: str, *, semibold: bool = False) -> int:
    return len(str(text or "")) * 8


class InfoBarOrientationDecisionTests(unittest.TestCase):
    def test_empty_content_stays_horizontal(self) -> None:
        from ui.infobar_layout import should_use_vertical_orientation

        self.assertFalse(should_use_vertical_orientation("Готово", "", 300, _measure_by_chars))

    def test_multiline_content_uses_vertical(self) -> None:
        from ui.infobar_layout import should_use_vertical_orientation

        self.assertTrue(
            should_use_vertical_orientation("Готово", "строка 1\nстрока 2", 1920, _measure_by_chars)
        )

    def test_long_content_uses_vertical_even_on_wide_window(self) -> None:
        from ui.infobar_layout import should_use_vertical_orientation

        self.assertTrue(
            should_use_vertical_orientation("Готово", "х" * 81, 1920, _measure_by_chars)
        )

    def test_medium_content_in_narrow_window_uses_vertical(self) -> None:
        from ui.infobar_layout import should_use_vertical_orientation

        # Регрессия: тост "Обновлений нет" в окне ~555px зажимал content
        # в узкую колонку рядом с заголовком и обрезал текст.
        self.assertTrue(
            should_use_vertical_orientation(
                "Обновлений нет",
                "Установлена актуальная версия 21.1.2.11",
                555,
                _measure_by_chars,
            )
        )

    def test_short_content_in_wide_window_stays_horizontal(self) -> None:
        from ui.infobar_layout import should_use_vertical_orientation

        self.assertFalse(
            should_use_vertical_orientation("Готово", "Настройка сохранена", 1200, _measure_by_chars)
        )

    def test_unknown_parent_width_uses_default_budget(self) -> None:
        from ui.infobar_layout import should_use_vertical_orientation

        self.assertFalse(
            should_use_vertical_orientation("Готово", "Настройка сохранена", 0, _measure_by_chars)
        )


class InfoBarAdaptiveLayoutInstallTests(unittest.TestCase):
    @staticmethod
    def _make_fake_infobar(calls: list[dict[str, object]]) -> type:
        class FakeInfoBar:
            @classmethod
            def new(cls, *args, **kwargs):
                calls.append({"args": args, "kwargs": kwargs})
                return "bar"

        return FakeInfoBar

    def test_upgrades_horizontal_to_vertical_for_long_content(self) -> None:
        from ui.infobar_layout import install_infobar_adaptive_layout

        calls: list[dict[str, object]] = []
        fake = self._make_fake_infobar(calls)
        install_infobar_adaptive_layout(fake)

        result = fake.new(
            "icon",
            "Заголовок",
            "х" * 100,
            Qt.Orientation.Horizontal,
            True,
            5000,
            "position",
            None,
        )

        self.assertEqual(result, "bar")
        self.assertEqual(calls[-1]["args"][3], Qt.Orientation.Vertical)

    def test_keeps_explicit_vertical_orientation(self) -> None:
        from ui.infobar_layout import install_infobar_adaptive_layout

        calls: list[dict[str, object]] = []
        fake = self._make_fake_infobar(calls)
        install_infobar_adaptive_layout(fake)

        fake.new("icon", "Заголовок", "Ок", Qt.Orientation.Vertical, True, 5000, "position", None)

        self.assertEqual(calls[-1]["args"][3], Qt.Orientation.Vertical)

    def test_keeps_horizontal_when_text_fits(self) -> None:
        from ui.infobar_layout import install_infobar_adaptive_layout

        calls: list[dict[str, object]] = []
        fake = self._make_fake_infobar(calls)
        install_infobar_adaptive_layout(fake)

        fake.new("icon", "Готово", "Ок", Qt.Orientation.Horizontal, True, 5000, "position", None)

        self.assertEqual(calls[-1]["args"][3], Qt.Orientation.Horizontal)

    def test_upgrades_orientation_passed_via_kwargs(self) -> None:
        from ui.infobar_layout import install_infobar_adaptive_layout

        calls: list[dict[str, object]] = []
        fake = self._make_fake_infobar(calls)
        install_infobar_adaptive_layout(fake)

        fake.new("icon", title="Заголовок", content="х" * 100)

        self.assertEqual(calls[-1]["kwargs"]["orient"], Qt.Orientation.Vertical)

    def test_narrow_parent_window_switches_to_vertical(self) -> None:
        from ui.infobar_layout import install_infobar_adaptive_layout

        calls: list[dict[str, object]] = []
        fake = self._make_fake_infobar(calls)
        install_infobar_adaptive_layout(fake)

        class NarrowParent:
            @staticmethod
            def width() -> int:
                return 320

        fake.new(
            "icon",
            "Обновлений нет",
            "Установлена актуальная версия 21.1.2.11",
            Qt.Orientation.Horizontal,
            True,
            5000,
            "position",
            NarrowParent(),
        )

        self.assertEqual(calls[-1]["args"][3], Qt.Orientation.Vertical)

    def test_install_is_idempotent(self) -> None:
        from ui.infobar_layout import install_infobar_adaptive_layout

        calls: list[dict[str, object]] = []
        fake = self._make_fake_infobar(calls)
        install_infobar_adaptive_layout(fake)
        first_new = fake.new
        install_infobar_adaptive_layout(fake)

        self.assertIs(fake.new.__func__, first_new.__func__)

        fake.new("icon", "Готово", "Ок")
        self.assertEqual(len(calls), 1)


class QtRuntimeInfoBarLayoutContractTests(unittest.TestCase):
    def test_qt_runtime_installs_adaptive_layout_hook(self) -> None:
        from main.qt_runtime import ensure_qt_runtime

        source = inspect.getsource(ensure_qt_runtime)

        self.assertIn("install_infobar_adaptive_layout", source)


if __name__ == "__main__":
    unittest.main()
