"""Перенос настроек: свои пресеты, слияние без потерь, применение в системе, перезапуск.

Раздел «Конфигурации» был собран, но выключен: файл переноса не нёс своих
пресетов (настройки помнили имя выбранного пресета, а на другом компьютере
файла не было), слияние по верхним ключам затирало реестр пресетов этого
компьютера, а запись шла только в settings.json — автозапуск и hosts
оставались как были, хотя экран говорил «включено».
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SELECTED = "selected_source_preset_file_name_winws2"


def _settings(**sections):
    base = {
        "version": 1,
        "program": {SELECTED: "Офис.txt", "gui_autostart_enabled": False, "dpi_autostart": True},
        "window": {"x": 10},
        "updater": {"release_cache": {"tag": "v0.19.67"}},
        "hosts": {"selection": {"ChatGPT": "geohide", "Claude": "geohide"}, "active_domains": ["a"]},
        "preset_registry": {"winws2": {"Офис.txt": "uid-office"}, "winws1": {}},
        "remote_presets": {"winws2": {}, "winws1": {}},
        "folders": {"presets": {"winws2": {"items": {"Офис.txt": {"folder_key": "common"}}}}},
    }
    base.update(sections)
    return base


class ExportTests(unittest.TestCase):
    def test_export_carries_own_presets_and_drops_unsafe_names(self) -> None:
        from configsets.plans import build_export

        document, report = build_export(
            _settings(), presets={"Офис.txt": "--name=Office", "../evil.txt": "x", "Дом.txt": "--new"}
        )
        self.assertEqual(sorted(document["presets"]), ["Дом.txt", "Офис.txt"])
        self.assertEqual(report.presets, ["Дом.txt", "Офис.txt"])

    def test_updater_cache_is_not_transferred(self) -> None:
        from configsets.plans import build_export

        document, report = build_export(_settings())
        self.assertNotIn("updater", document["sections"])
        self.assertIn("updater", report.skipped_sections)


class PresetPlanTests(unittest.TestCase):
    def test_new_same_and_conflicting_presets(self) -> None:
        from configsets.plans import plan_preset_import

        document = {"presets": {"Новый.txt": "a", "Офис.txt": "line\r\n", "Дом.txt": "чужой"}}
        existing = {"Офис.txt": "line\n", "Дом.txt": "свой", "Дом (из файла).txt": "занято"}

        plan = plan_preset_import(document, existing=existing)

        self.assertEqual(plan.same, ["Офис.txt"])
        self.assertEqual(plan.renamed, {"Дом.txt": "Дом (из файла) 2.txt"})
        self.assertEqual(plan.writes, {"Новый.txt": "a", "Дом (из файла) 2.txt": "чужой"})

    def test_unsafe_and_oversized_presets_are_rejected(self) -> None:
        from configsets.plans import MAX_PRESET_BYTES, plan_preset_import

        document = {"presets": {"..\\x.txt": "a", "big.txt": "x" * (MAX_PRESET_BYTES + 1), "ok.txt": 5}}
        plan = plan_preset_import(document, existing={})
        self.assertEqual(plan.writes, {})
        self.assertEqual(sorted(plan.rejected), ["..\\x.txt", "big.txt", "ok.txt"])


class ImportMergeTests(unittest.TestCase):
    def _document(self, sections, presets=None):
        from configsets.plans import CONFIG_FORMAT_VERSION

        document = {"format": "net67-config", "format_version": CONFIG_FORMAT_VERSION, "sections": sections}
        if presets is not None:
            document["presets"] = presets
        return document

    def test_renamed_preset_moves_references_and_keeps_own_entries(self) -> None:
        from configsets.plans import build_import_patch

        current = _settings()
        document = self._document(
            {
                "program": {SELECTED: "Офис.txt"},
                "preset_registry": {"winws2": {"Офис.txt": "uid-from-file"}},
                "folders": {"presets": {"winws2": {"items": {"Офис.txt": {"folder_key": "work"}}}}},
            }
        )
        result, report = build_import_patch(
            document, current=current, renamed_presets={"Офис.txt": "Офис (из файла).txt"}
        )

        self.assertTrue(report.ok)
        self.assertEqual(result["program"][SELECTED], "Офис (из файла).txt")
        # Свой «Офис.txt» этого компьютера сохранил свою привязку к оценкам.
        self.assertEqual(result["preset_registry"]["winws2"]["Офис.txt"], "uid-office")
        self.assertEqual(result["preset_registry"]["winws2"]["Офис (из файла).txt"], "uid-from-file")
        items = result["folders"]["presets"]["winws2"]["items"]
        self.assertEqual(items["Офис.txt"], {"folder_key": "common"})
        self.assertEqual(items["Офис (из файла).txt"], {"folder_key": "work"})

    def test_registry_merges_deep_but_hosts_selection_is_replaced(self) -> None:
        from configsets.plans import build_import_patch

        document = self._document(
            {
                "preset_registry": {"winws2": {"Дом.txt": "uid-home"}},
                "hosts": {"selection": {"ChatGPT": "dns_ai"}},
            }
        )
        result, _report = build_import_patch(document, current=_settings())

        self.assertEqual(result["preset_registry"]["winws2"], {"Офис.txt": "uid-office", "Дом.txt": "uid-home"})
        # «Сделай как там»: Claude в файле выключен — выключается и здесь.
        self.assertEqual(result["hosts"]["selection"], {"ChatGPT": "dns_ai"})
        self.assertEqual(result["hosts"]["active_domains"], ["a"])


class PostApplyActionsTests(unittest.TestCase):
    def test_changes_that_live_outside_settings_are_detected(self) -> None:
        from configsets.plans import post_apply_actions

        before = _settings()
        after = _settings(
            program={SELECTED: "Офис.txt", "gui_autostart_enabled": True},
            hosts={"selection": {"ChatGPT": "dns_ai"}},
        )
        actions = post_apply_actions(before, after)
        self.assertEqual(actions.hosts_selection, {"ChatGPT": "dns_ai"})
        self.assertIs(actions.gui_autostart, True)
        self.assertTrue(actions.any)

    def test_nothing_to_do_when_nothing_changed(self) -> None:
        from configsets.plans import post_apply_actions

        self.assertFalse(post_apply_actions(_settings(), _settings()).any)


class EffectsTests(unittest.TestCase):
    def test_hosts_go_through_the_one_hosts_writer(self) -> None:
        from configsets.effects import apply_post_actions
        from configsets.plans import PostApplyActions

        with patch("hosts.commands.apply_hosts_draft") as draft:
            draft.return_value.success = True
            problems = apply_post_actions(PostApplyActions(hosts_selection={"ChatGPT": "dns_ai"}))
        draft.assert_called_once_with({"ChatGPT": "dns_ai"})
        self.assertEqual(problems, [])

    def test_failed_autostart_puts_the_setting_back(self) -> None:
        from configsets.effects import apply_post_actions
        from configsets.plans import PostApplyActions

        failed = Mock(level="error", content="Политика запрещает задачи планировщика")
        with (
            patch("program_settings.commands.set_gui_autostart_enabled", return_value=failed),
            patch("autostart.public.save_gui_autostart_enabled") as save,
        ):
            problems = apply_post_actions(PostApplyActions(gui_autostart=True))
        save.assert_called_once_with(False)
        self.assertEqual(problems, ["Политика запрещает задачи планировщика"])


class PresetFilesTests(unittest.TestCase):
    def test_written_presets_are_lf_and_stay_inside_the_folder(self) -> None:
        from configsets.storage import read_preset_files, write_preset_files

        with TemporaryDirectory() as temp:
            folder = Path(temp) / "winws2"
            failed = write_preset_files(folder, {"Офис.txt": "a\r\nb\r\n", "../evil.txt": "x"})
            self.assertEqual(failed, ["../evil.txt"])
            self.assertEqual((folder / "Офис.txt").read_bytes(), "a\nb\n".encode("utf-8"))
            self.assertFalse((Path(temp) / "evil.txt").exists())
            self.assertEqual(read_preset_files(folder), {"Офис.txt": "a\nb\n"})


class RestartTests(unittest.TestCase):
    def test_frozen_and_source_command_lines(self) -> None:
        from app.restart import AFTER_RESTART_ARG, RESUME_BYPASS_ARG, relaunch_command

        frozen = relaunch_command(
            executable="C:/net67/_internal/net67.exe", argv=["net67.exe", "--tray", "--x"], frozen=True, resume_bypass=True
        )
        self.assertEqual(frozen, ["C:/net67/_internal/net67.exe", "--x", AFTER_RESTART_ARG, RESUME_BYPASS_ARG])
        source = relaunch_command(
            executable="python.exe", argv=["main.py", AFTER_RESTART_ARG], frozen=False, resume_bypass=False
        )
        self.assertEqual(source, ["python.exe", "main.py", AFTER_RESTART_ARG])

    def test_new_instance_waits_for_old_one_and_closes_its_handle_each_time(self) -> None:
        from main.shell import wait_for_mutex_release

        answers = iter([("h2", True), ("h3", True), ("h4", False)])
        released: list[str] = []
        handle, busy = wait_for_mutex_release(
            "net67SingleInstance",
            "h1",
            create_mutex=lambda _name: next(answers),
            release_mutex=released.append,
            sleep=lambda _s: None,
        )
        self.assertEqual((handle, busy), ("h4", False))
        self.assertEqual(released, ["h1", "h2", "h3"])

    def test_wait_gives_up_after_timeout(self) -> None:
        from main.shell import wait_for_mutex_release

        now = [0.0]

        def clock() -> float:
            now[0] += 5.0
            return now[0]

        _handle, busy = wait_for_mutex_release(
            "n", "h", create_mutex=lambda _n: ("h", True), release_mutex=lambda _h: None,
            sleep=lambda _s: None, clock=clock, timeout=12.0,
        )
        self.assertTrue(busy)

    def test_resume_flag_starts_bypass_even_without_autostart(self) -> None:
        from app.initial_ui_state import build_initial_ui_state
        from app.restart import RESUME_BYPASS_ARG

        settings = {"program": {"dpi_autostart": False, "strategy_launch_method": "zapret2_mode"}}
        with patch("settings.store.read_settings", return_value=settings):
            with patch.object(sys, "argv", ["net67.exe"]):
                self.assertEqual(build_initial_ui_state().launch_phase, "stopped")
            with patch.object(sys, "argv", ["net67.exe", RESUME_BYPASS_ARG]):
                self.assertEqual(build_initial_ui_state().launch_phase, "autostart_pending")


class PageNotificationTests(unittest.TestCase):
    def test_applied_settings_end_with_restart_button(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from qfluentwidgets import InfoBar, PushButton

        from configsets.ui.page import ConfigsPage

        _app = QApplication.instance() or QApplication([])
        with patch.object(ConfigsPage, "_reload"):
            page = ConfigsPage()
        self.addCleanup(page.deleteLater)
        page.resize(800, 600)
        page.show()

        with patch.object(ConfigsPage, "_restart") as restart:
            page._notify_applied("Применено разделов: 3", [])
            buttons = [
                button
                for bar in page.findChildren(InfoBar)
                for button in bar.findChildren(PushButton)
                if button.text() == "Перезапустить"
            ]
            self.assertEqual(len(buttons), 1)
            buttons[0].click()
        restart.assert_called_once()


class RoundTripThroughPageTests(unittest.TestCase):
    """Выгрузка на одном «компьютере» и загрузка на другом — через саму страницу."""

    def _machine(self, temp: Path, name: str):
        from settings import store

        root = temp / name
        (root / "presets" / "winws2").mkdir(parents=True)
        patcher = patch("settings.store.MAIN_DIRECTORY", str(root))
        patcher.start()
        store.prepare_settings_database()
        return root, patcher

    def test_presets_and_choices_reach_the_other_machine(self) -> None:
        import json

        from PyQt6.QtWidgets import QApplication

        from configsets.ui import page as page_module
        from settings import store

        _app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            export_path = temp / "net67-config.json"

            # Компьютер А: свой пресет выбран, ChatGPT и Claude в hosts.
            root_a, patcher = self._machine(temp, "a")
            try:
                (root_a / "presets" / "winws2" / "Офис.txt").write_bytes("--name=Office\n".encode("utf-8"))
                store.replace_settings(
                    {
                        **store.read_settings(),
                        "program": {**store.read_settings()["program"], SELECTED: "Офис.txt"},
                        "hosts": {"selection": {"ChatGPT": "geohide"}},
                    }
                )
                with (
                    patch.object(page_module, "user_presets_dir", return_value=root_a / "presets" / "winws2"),
                    patch.object(page_module, "_settings_root", return_value=root_a / "settings"),
                    patch.object(page_module.QFileDialog, "getSaveFileName", return_value=(str(export_path), "")),
                ):
                    page = page_module.ConfigsPage()
                    page._on_export()
                    page.deleteLater()
            finally:
                store.close_settings_database()
                patcher.stop()

            document = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(document["presets"], {"Офис.txt": "--name=Office\n"})

            # Компьютер Б: свой «Офис.txt» с другим текстом — его не трогаем.
            root_b, patcher = self._machine(temp, "b")
            try:
                own = root_b / "presets" / "winws2" / "Офис.txt"
                own.write_bytes("--name=Своё\n".encode("utf-8"))
                with (
                    patch.object(page_module, "user_presets_dir", return_value=root_b / "presets" / "winws2"),
                    patch.object(page_module, "_settings_root", return_value=root_b / "settings"),
                    patch.object(page_module.QFileDialog, "getOpenFileName", return_value=(str(export_path), "")),
                    patch("configsets.effects.apply_post_actions", return_value=[]) as effects,
                ):
                    page = page_module.ConfigsPage()
                    page._on_import()
                    deadline = __import__("time").monotonic() + 3
                    while effects.call_count == 0 and __import__("time").monotonic() < deadline:
                        QApplication.processEvents()
                    page.deleteLater()

                self.assertEqual(own.read_bytes(), "--name=Своё\n".encode("utf-8"))
                imported = root_b / "presets" / "winws2" / "Офис (из файла).txt"
                self.assertEqual(imported.read_bytes(), "--name=Office\n".encode("utf-8"))
                settings = store.read_settings()
                self.assertEqual(settings["program"][SELECTED], "Офис (из файла).txt")
                self.assertEqual(settings["hosts"]["selection"], {"ChatGPT": "geohide"})
                # hosts отдан писателю hosts, а не только записан в settings.json.
                effects.assert_called_once()
                self.assertEqual(effects.call_args.args[0].hosts_selection, {"ChatGPT": "geohide"})
            finally:
                store.close_settings_database()
                patcher.stop()


if __name__ == "__main__":
    unittest.main()
