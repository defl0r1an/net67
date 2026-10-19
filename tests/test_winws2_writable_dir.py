"""Пресет с --writable запускается и там, где папки user/ ещё нет.

19 октября 2026, 0.24.67: пресет white sni (circular) не запускался —
«Проверка пресета через winws2 не прошла (код 1): bad file 'user/winws2'».
Движок разбирает --writable через realpath_any: несуществующую папку он
создаёт сам, но только если существует её родитель. У zapret папка user/
есть всегда (там их настройки), у net67 настройки в settings/, и user/
появляется, только когда человек добавил свой фейк. Замер: в пустой папке
winws2 --dry-run --writable=user/winws2 пишет «bad file», а с user/ —
проходит и создаёт user/winws2 сам.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from winws_runtime.runners import zapret2_runner  # noqa: E402
from winws_runtime.runners.zapret2_runner import Winws2StrategyRunner  # noqa: E402


class EnsureWritableDirsTests(unittest.TestCase):
    def test_relative_dir_is_created_under_work_dir(self) -> None:
        work_dir = tempfile.mkdtemp(prefix="net67-writable-")

        created = zapret2_runner.ensure_writable_dirs("--lua-init=@lua/x.lua\n--writable=user/winws2\n", work_dir)

        self.assertTrue(os.path.isdir(os.path.join(work_dir, "user", "winws2")))
        self.assertEqual(created, [os.path.join(work_dir, "user", "winws2")])

    def test_text_without_writable_touches_nothing(self) -> None:
        work_dir = tempfile.mkdtemp(prefix="net67-writable-")

        self.assertEqual(zapret2_runner.ensure_writable_dirs("--filter-tcp=443\n", work_dir), [])
        self.assertEqual(os.listdir(work_dir), [])

    def test_bare_writable_has_no_dir_to_make(self) -> None:
        # Без значения движок берёт свою папку по умолчанию — создавать нечего.
        work_dir = tempfile.mkdtemp(prefix="net67-writable-")

        self.assertEqual(zapret2_runner.ensure_writable_dirs("--writable\n", work_dir), [])


class DryRunMakesWritableDirFirstTests(unittest.TestCase):
    def test_dry_run_sees_the_dir_already_made(self) -> None:
        work_dir = tempfile.mkdtemp(prefix="net67-writable-")
        target = os.path.join(work_dir, "user", "winws2")
        runner = object.__new__(Winws2StrategyRunner)
        runner.winws_exe = "winws2.exe"
        runner.work_dir = work_dir
        artifact = SimpleNamespace(
            preset_path="white sni (circular).txt",
            normalized_text="--writable=user/winws2\n--filter-tcp=443\n",
            launch_args=("@tmp/config.txt",),
        )
        runner._artifact_for_dry_run_locked = lambda value: value
        runner._create_startup_info = lambda: None
        runner._decode_process_output = lambda raw: ""
        seen = []

        def _run(*_args, **_kwargs):
            seen.append(os.path.isdir(target))
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        with patch.object(zapret2_runner.subprocess, "run", side_effect=_run):
            ok = runner._run_preset_dry_run_locked(artifact, "white sni", preset_switch=False, notify_failure=False)

        self.assertTrue(ok)
        self.assertEqual(seen, [True])


if __name__ == "__main__":
    unittest.main()
