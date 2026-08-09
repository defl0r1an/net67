"""Пошаговый замер сборки интерфейса: молчит на быстром, кричит на медленном.

Метрики страниц показывают, что конструктор главной страницы идёт
9,7 секунды при бюджете 200 мс, и почти всё это — сборка секций настроек.
Та же сборка на другой машине занимает 91 мс, то есть код не виноват.
Замер нужен, чтобы следующий запуск на медленной машине назвал виновный
виджет сам, а не по догадке.

Два требования к нему одинаково важны. Он обязан молчать, пока всё
быстро: два десятка строк «0 мс» на каждый запуск — и в нужный момент
этот лог никто не прочитает. И он обязан не глотать исключения: замер,
который прячет падение сборки, хуже отсутствия замера.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

SECTIONS_BUILD = (
    PROJECT_SRC / "presets" / "ui" / "control" / "zapret2" / "sections_build.py"
)


def _timer(threshold_ms=1000.0):
    from ui.build_timing import BuildStepTimer

    lines: list[str] = []
    timer = BuildStepTimer(
        "тест",
        threshold_ms=threshold_ms,
        log_fn=lambda message, level="INFO": lines.append(message),
    )
    return timer, lines


class SilenceTests(unittest.TestCase):
    def test_fast_steps_write_nothing(self) -> None:
        """Иначе лог засоряется и перестаёт читаться."""
        timer, lines = _timer()

        for name in ("a", "b", "c"):
            with timer.step(name):
                pass
        timer.finish()

        self.assertEqual(lines, [])

    def test_slow_step_is_named(self) -> None:
        timer, lines = _timer(threshold_ms=0.0)

        with timer.step("тяжёлый виджет"):
            pass

        self.assertTrue(lines)
        self.assertIn("тяжёлый виджет", lines[0])

    def test_total_lists_the_worst_steps(self) -> None:
        """Итог должен сразу называть виновника, а не только сумму."""
        timer, lines = _timer(threshold_ms=0.0)

        with timer.step("быстрый"):
            pass
        with timer.step("медленный"):
            pass
        timer.finish()

        self.assertIn("медленный", lines[-1])
        self.assertIn("всего", lines[-1])


class FailureTests(unittest.TestCase):
    def test_exception_is_not_swallowed(self) -> None:
        """Замер, прячущий падение сборки, хуже отсутствия замера."""
        timer, _ = _timer()

        with self.assertRaises(ValueError):
            with timer.step("падучий"):
                raise ValueError("виджет не собрался")

    def test_failed_step_is_still_measured(self) -> None:
        timer, _ = _timer()

        try:
            with timer.step("падучий"):
                raise ValueError("виджет не собрался")
        except ValueError:
            pass

        self.assertEqual([name for name, _ in timer.steps], ["падучий"])

    def test_broken_logger_does_not_break_the_build(self) -> None:
        """Сломанный лог не должен ронять построение интерфейса."""
        from ui.build_timing import BuildStepTimer

        def _boom(*_args, **_kwargs):
            raise OSError("лог недоступен")

        timer = BuildStepTimer("тест", threshold_ms=0.0, log_fn=_boom)

        with self.assertRaises(OSError):
            with timer.step("шаг"):
                pass


class WiringTests(unittest.TestCase):
    """Замер обязан стоять там, где медленно, иначе он бесполезен."""

    def test_sections_build_is_instrumented(self) -> None:
        source = SECTIONS_BUILD.read_text(encoding="utf-8")

        self.assertIn("BuildStepTimer", source)
        self.assertIn("timer.finish()", source)

    def test_the_mdi_icons_are_measured_separately(self) -> None:
        """Первый запрос второго набора иконок — отдельный подозреваемый.

        Почти все значки страницы берутся из fa5s, и только два — из mdi.
        Если время съедает загрузка второго шрифта, разделённые шаги
        покажут это сразу.
        """
        source = SECTIONS_BUILD.read_text(encoding="utf-8")

        self.assertIn('timer.step("discord_restart_toggle (mdi)")', source)
        self.assertIn('timer.step("debug_log_toggle (mdi)")', source)

    def test_every_widget_group_is_covered(self) -> None:
        source = SECTIONS_BUILD.read_text(encoding="utf-8")

        for name in (
            "gui_autostart_toggle",
            "auto_dpi_toggle",
            "tray_close_mode_combo",
            "windows_feature_toggles",
            "additional_settings_section",
            "test_card",
            "internet_cleanup_card",
            "folder_card",
            "docs_card",
            "state_media_block_toggle",
        ):
            with self.subTest(step=name):
                self.assertIn(f'timer.step("{name}")', source)

    def test_threshold_is_visible_to_a_human(self) -> None:
        """Порог должен ловить задержку, которую человек уже замечает."""
        from ui.build_timing import DEFAULT_STEP_THRESHOLD_MS

        self.assertGreaterEqual(DEFAULT_STEP_THRESHOLD_MS, 50.0)
        self.assertLessEqual(DEFAULT_STEP_THRESHOLD_MS, 250.0)


if __name__ == "__main__":
    unittest.main()
