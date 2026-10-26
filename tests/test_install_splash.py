"""Окно-продолжение установки: от закрытия старой версии до открытия новой.

Между закрытием старой версии и открытием новой экран был пустым или
показывал голое окно установщика. Окно-продолжение — отдельный процесс
PowerShell; эти тесты держат то, что ломается без Windows-окна: скрипт без
не-ASCII символов (PowerShell 5.1 читает его как ANSI), тексты, тихий
установщик только при показанном окне, метку «новая версия открылась»
только у недавнего окна и запись номера процесса установщика.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class SplashScriptTests(unittest.TestCase):
    def test_script_is_plain_ascii(self) -> None:
        from updater.install_splash_script import SPLASH_SCRIPT

        SPLASH_SCRIPT.encode("ascii")

    def test_script_reads_texts_from_utf8_json(self) -> None:
        from updater.install_splash_script import SPLASH_SCRIPT

        self.assertIn("[System.Text.Encoding]::UTF8", SPLASH_SCRIPT)
        self.assertIn("Installation process succeeded", SPLASH_SCRIPT)


class SplashSpecTests(unittest.TestCase):
    def test_texts_name_both_versions(self) -> None:
        from updater.install_splash import texts_for

        texts = texts_for("0.27.67", "0.26.67")
        self.assertIn("0.27.67", texts["title"])
        self.assertIn("0.26.67", texts["subtitle"])
        self.assertEqual(len(texts["stages"]), 3)

    def test_spec_points_the_window_at_its_files(self) -> None:
        from updater.install_splash import build_spec

        directory = Path(tempfile.mkdtemp(prefix="net67-splash-"))
        spec = build_spec(
            version="0.27.67", current_version="0.26.67", directory=directory, center=(10, 20),
            old_pid=123, setup_log_path="C:/setup.log", jokes=["a"],
        )
        self.assertEqual(spec["old_pid"], 123)
        self.assertEqual(spec["ready_path"], str(directory / "ready.txt"))
        self.assertEqual(spec["installer_pid_path"], str(directory / "installer.pid"))
        self.assertEqual((spec["center_x"], spec["center_y"]), (10, 20))


class QuietInstallerTests(unittest.TestCase):
    def test_silent_becomes_very_silent_only_there(self) -> None:
        from updater.update_pipeline import quiet_installer_arguments

        self.assertEqual(
            quiet_installer_arguments(("/AUTOUPDATE", "/SILENT", "/SUPPRESSMSGBOXES")),
            ("/AUTOUPDATE", "/VERYSILENT", "/SUPPRESSMSGBOXES"),
        )

    def test_installer_pid_is_taken_from_powershell_output(self) -> None:
        from updater.update import _write_installer_pid

        path = Path(tempfile.mkdtemp(prefix="net67-splash-")) / "installer.pid"
        _write_installer_pid(str(path), b"\r\n4321\r\n")
        self.assertEqual(path.read_text(encoding="ascii"), "4321")


class ReadyMarkTests(unittest.TestCase):
    def _dir(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="net67-splash-"))
        patcher = patch("updater.install_splash.splash_dir", lambda: directory)
        patcher.start()
        self.addCleanup(patcher.stop)
        return directory

    def test_plain_start_writes_nothing(self) -> None:
        from updater.install_splash import mark_update_app_ready

        directory = self._dir()
        self.assertFalse(mark_update_app_ready())
        self.assertFalse((directory / "ready.txt").exists())

    def test_recent_splash_gets_the_mark(self) -> None:
        from updater.install_splash import mark_update_app_ready

        directory = self._dir()
        (directory / "install_splash.json").write_text("{}", encoding="utf-8")
        self.assertTrue(mark_update_app_ready())
        self.assertTrue((directory / "ready.txt").exists())

    def test_stale_splash_gets_no_mark(self) -> None:
        from updater.install_splash import READY_MARK_MAX_AGE_SECONDS, mark_update_app_ready

        directory = self._dir()
        spec = directory / "install_splash.json"
        spec.write_text("{}", encoding="utf-8")
        old = time.time() - READY_MARK_MAX_AGE_SECONDS - 60
        os.utime(spec, (old, old))
        self.assertFalse(mark_update_app_ready())


if __name__ == "__main__":
    unittest.main()
