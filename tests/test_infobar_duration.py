from __future__ import annotations

import inspect
import unittest


class SuccessInfoBarDurationTests(unittest.TestCase):
    def test_success_infobar_duration_is_at_least_five_seconds(self) -> None:
        from ui.infobar_duration import install_success_infobar_min_duration

        calls: list[dict[str, object]] = []

        class FakeInfoBar:
            @classmethod
            def success(cls, *args, **kwargs):
                calls.append({"args": args, "kwargs": kwargs})
                return "bar"

        install_success_infobar_min_duration(FakeInfoBar)

        self.assertEqual(FakeInfoBar.success("Готово", "Настройка сохранена", duration=2000), "bar")
        self.assertEqual(calls[-1]["kwargs"]["duration"], 5000)

        FakeInfoBar.success("Готово", "Настройка сохранена")
        self.assertEqual(calls[-1]["kwargs"]["duration"], 5000)

    def test_success_infobar_keeps_long_and_persistent_duration(self) -> None:
        from ui.infobar_duration import install_success_infobar_min_duration

        calls: list[dict[str, object]] = []

        class FakeInfoBar:
            @classmethod
            def success(cls, *args, **kwargs):
                calls.append({"args": args, "kwargs": kwargs})
                return "bar"

        install_success_infobar_min_duration(FakeInfoBar)

        FakeInfoBar.success("Готово", "Долго", duration=10000)
        self.assertEqual(calls[-1]["kwargs"]["duration"], 10000)

        FakeInfoBar.success("Готово", "Постоянно", duration=-1)
        self.assertEqual(calls[-1]["kwargs"]["duration"], -1)

    def test_success_infobar_clamps_positional_duration_argument(self) -> None:
        from ui.infobar_duration import install_success_infobar_min_duration

        calls: list[dict[str, object]] = []

        class FakeInfoBar:
            @classmethod
            def success(cls, *args, **kwargs):
                calls.append({"args": args, "kwargs": kwargs})
                return "bar"

        install_success_infobar_min_duration(FakeInfoBar)

        FakeInfoBar.success("Готово", "Позиционно", "orient", True, 3000)
        self.assertEqual(calls[-1]["args"][4], 5000)

    def test_qt_runtime_installs_success_infobar_duration_hook(self) -> None:
        from main.qt_runtime import ensure_qt_runtime

        source = inspect.getsource(ensure_qt_runtime)

        self.assertIn("install_success_infobar_min_duration", source)


if __name__ == "__main__":
    unittest.main()
