from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


def _writers(record: dict, *, fail_on: str = ""):
    from wizard.apply import WizardWriters

    def make(name: str):
        def write(value):
            if name == fail_on:
                raise OSError("нет доступа к настройкам")
            record[name] = value
            return True

        return write

    return WizardWriters(
        set_gui_autostart_enabled=make("gui_autostart"),
        set_dpi_autostart=make("dpi_autostart"),
        set_tray_close_mode=make("tray_mode"),
        apply_hosts=lambda entries: "",
        set_wizard_services=make("services"),
        set_wizard_completed=make("completed"),
    )


class WizardApplyTests(unittest.TestCase):
    def test_all_settings_are_written(self) -> None:
        from wizard.apply import apply_wizard

        record: dict = {}
        result = apply_wizard(
            selection={"video", "messengers"},
            autostart_with_windows=True,
            minimize_to_tray=True,
            writers=_writers(record),
        )

        self.assertTrue(result.saved)
        self.assertTrue(record["gui_autostart"])
        self.assertTrue(record["dpi_autostart"])
        self.assertEqual(record["tray_mode"], "minimize_and_close")
        self.assertEqual(record["services"], ["messengers", "video"])
        self.assertTrue(record["completed"])

    def test_request_matches_selection(self) -> None:
        from wizard.apply import apply_wizard

        result = apply_wizard(
            selection={"adobe"},
            autostart_with_windows=False,
            minimize_to_tray=False,
            writers=_writers({}),
        )

        self.assertIn("adobe", result.request.services)
        self.assertTrue(result.request.hosts_entries)

    def test_completion_flag_is_written_last(self) -> None:
        """Иначе сбой записи оставит мастер «пройденным» без настроек."""
        from wizard.apply import apply_wizard

        order: list[str] = []

        from wizard.apply import WizardWriters

        def make(name: str):
            def write(_value):
                order.append(name)
                return True

            return write

        apply_wizard(
            selection={"video"},
            autostart_with_windows=False,
            minimize_to_tray=False,
            writers=WizardWriters(
                set_gui_autostart_enabled=make("gui_autostart"),
                set_dpi_autostart=make("dpi_autostart"),
                set_tray_close_mode=make("tray_mode"),
                apply_hosts=lambda entries: "",
                set_wizard_services=make("services"),
                        set_wizard_completed=make("completed"),
            ),
        )

        self.assertEqual(order[-1], "completed")

    def test_write_failure_does_not_mark_wizard_completed(self) -> None:
        from wizard.apply import apply_wizard

        record: dict = {}
        result = apply_wizard(
            selection={"video"},
            autostart_with_windows=True,
            minimize_to_tray=False,
            writers=_writers(record, fail_on="tray_mode"),
        )

        self.assertFalse(result.saved)
        self.assertNotIn("completed", record)
        self.assertIn("Не удалось сохранить", result.message)

    def test_unknown_services_are_not_persisted(self) -> None:
        from wizard.apply import apply_wizard

        record: dict = {}
        apply_wizard(
            selection={"video", "выдуманный"},
            autostart_with_windows=False,
            minimize_to_tray=False,
            writers=_writers(record),
        )

        self.assertEqual(record["services"], ["video"])


class WizardNeededTests(unittest.TestCase):
    def test_request_from_settings_is_always_usable(self) -> None:
        from oneclick.plans import OneClickRequest
        from wizard.apply import build_request_from_settings

        self.assertIsInstance(build_request_from_settings(), OneClickRequest)


if __name__ == "__main__":
    unittest.main()


class AutostartRegistrationTests(unittest.TestCase):
    """Галочка «Запускать вместе с Windows» должна создавать задачу.

    Мастер вызывал settings.store.set_gui_autostart_enabled — она лишь
    пишет флаг в settings.json. Одноимённая функция из
    program_settings.commands регистрирует задачу в планировщике. Из-за
    совпадения имён галочка сохранялась, а автозапуска не появлялось.
    """

    def test_default_writer_registers_task_not_just_flag(self) -> None:
        import wizard.apply as apply_module

        source = Path(apply_module.__file__).read_text(encoding="utf-8")

        self.assertIn("from program_settings.commands import", source)
        self.assertNotIn(
            "    set_gui_autostart_enabled,\n",
            source,
            "мастер снова импортирует запись флага из settings.store",
        )

    def test_autostart_failure_becomes_warning_not_lost(self) -> None:
        from wizard.apply import WizardWriters, apply_wizard

        calls: list = []
        writers = WizardWriters(
            set_gui_autostart_enabled=lambda value: "Политика запрещает автозапуск",
            set_dpi_autostart=lambda value: calls.append(("dpi", value)),
            set_tray_close_mode=lambda value: calls.append(("tray", value)),
            apply_hosts=lambda entries: "",
            set_wizard_services=lambda value: calls.append(("services", value)),
            set_wizard_completed=lambda value: calls.append(("done", value)),
        )

        result = apply_wizard(
            selection=["video"],
            autostart_with_windows=True,
            minimize_to_tray=True,
            writers=writers,
        )

        # Остальные настройки сохранены, мастер пройден.
        self.assertTrue(result.saved)
        self.assertIn(("done", True), calls)
        # Но о проблеме сообщено.
        self.assertEqual(result.warnings, ("Политика запрещает автозапуск",))

    def test_successful_autostart_has_no_warnings(self) -> None:
        from wizard.apply import WizardWriters, apply_wizard

        writers = WizardWriters(
            set_gui_autostart_enabled=lambda value: "",
            set_dpi_autostart=lambda value: None,
            set_tray_close_mode=lambda value: None,
            apply_hosts=lambda entries: "",
            set_wizard_services=lambda value: None,
            set_wizard_completed=lambda value: None,
        )

        result = apply_wizard(
            selection=["video"],
            autostart_with_windows=True,
            minimize_to_tray=False,
            writers=writers,
        )

        self.assertTrue(result.saved)
        self.assertEqual(result.warnings, ())
