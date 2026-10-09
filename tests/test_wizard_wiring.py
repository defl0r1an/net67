"""Мастер первого запуска должен быть подключён к старту приложения.

Логика мастера может быть безупречной и полностью оттестированной, но
если её никто не вызывает, пользователь её не увидит. Ровно так и было:
пакеты oneclick и wizard существовали, а ссылок на них из интерфейса не
было ни одной.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


def _read(*parts: str) -> str:
    return (PROJECT_SRC.joinpath(*parts)).read_text(encoding="utf-8")


class WizardWiringTests(unittest.TestCase):
    def test_wizard_is_installed_in_post_startup(self) -> None:
        source = _read("main", "post_startup.py")

        self.assertIn("install_first_run_wizard", source)

    def test_installer_module_exists_and_parses(self) -> None:
        tree = ast.parse(_read("main", "post_startup_wizard.py"))
        functions = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

        self.assertIn("install_first_run_wizard", functions)

    def test_setup_questions_live_in_the_tour(self) -> None:
        """Окна мастера нет: каждый его вопрос задаёт тур у своего раздела."""
        from ui.onboarding.setup_choices import CHOICE_KEYS
        from ui.onboarding.steps import TOUR_STEPS

        asked = {step.choice for step in TOUR_STEPS if step.choice}
        self.assertEqual(asked, set(CHOICE_KEYS))
        self.assertFalse(PROJECT_SRC.joinpath("wizard", "ui", "dialog.py").exists())

    def test_diagnostics_run_off_the_ui_thread(self) -> None:
        """check_one_domain делает DNS, TCP, ping и HTTP — это долго."""
        source = _read("ui", "onboarding", "setup_detect_worker.py")

        self.assertIn("QThread", source)
        self.assertRegex(source, r"class _DetectWorker\(QThread\)")

    def test_wizard_failure_does_not_break_startup(self) -> None:
        """Мастер — удобство, а не обязательная часть запуска."""
        source = _read("main", "post_startup_wizard.py")

        self.assertIn("except Exception", source)

    def test_every_step_is_rendered(self) -> None:
        source = _read("ui", "onboarding", "setup_choices.py")

        for builder in ("_provider_widget", "_hosts_widget", "_DetectPanel", "_startup_widget"):
            self.assertIn(builder, source)

    def test_step_count_matches_plans(self) -> None:
        from wizard.plans import WIZARD_STEPS

        self.assertEqual(
            [step.key for step in WIZARD_STEPS],
            ["provider", "hosts", "detect", "startup"],
        )


class OneClickWiringTests(unittest.TestCase):
    def test_button_module_is_referenced_by_a_page(self) -> None:
        source = _read("presets", "ui", "control", "zapret2", "page.py")

        self.assertIn("oneclick.ui.button", source)

    def test_button_uses_saved_wizard_answers(self) -> None:
        """Кнопка должна включать то, что человек выбрал в мастере."""
        # Работу кнопки делает её поток (oneclick/ui/oneclick_worker.py).
        source = _read("oneclick", "ui", "oneclick_worker.py")

        self.assertIn("build_request_from_settings", source)


if __name__ == "__main__":
    unittest.main()
