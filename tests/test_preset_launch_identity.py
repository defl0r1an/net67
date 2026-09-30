"""Пресет — точка истины: запуск передаёт winws ровно то, что написано в пресете.

Для каждого builtin-пресета обоих движков @config, который реально получает
winws, разбирается обратно (shlex.split) и сравнивается с аргументами из
текста пресета (launch_args_from_preset_text). Разрешённые отличия — только
из presets.preset_contract: winws1 заменяет относительные пути к спискам и
bin-файлам абсолютными путями к ТЕМ ЖЕ файлам; процесс проверки получает
ровно флаги *_DRY_RUN_EXTRA_ARGS; быстрая смена пресета — ровно
FAST_SWITCH_HANDOFF_EXTRA_ARGS.
"""

from __future__ import annotations

import os
import shlex
import tempfile
import unittest
from pathlib import Path
from threading import RLock

from presets.preset_contract import (
    FAST_SWITCH_HANDOFF_EXTRA_ARGS,
    WINWS2_DRY_RUN_EXTRA_ARGS,
)
from winws_runtime.runners.preset_runner_support import launch_args_from_preset_text


PUBLIC_ROOT = Path(__file__).resolve().parents[1]
BUILTIN_ROOT = PUBLIC_ROOT / "src" / "presets" / "builtin"


def _builtin_paths(engine: str) -> list[Path]:
    return sorted((BUILTIN_ROOT / engine).glob("*.txt"))


def _config_args(launch_args: tuple[str, ...], root: Path | None = None) -> list[str]:
    assert len(launch_args) == 1 and launch_args[0].startswith("@"), launch_args
    # net67 передаёт winws2 путь к @config относительно корня программы:
    # абсолютный путь с пробелом в «Program Files» движок разрывал надвое.
    path = Path(launch_args[0][1:])
    if not path.is_absolute() and root is not None:
        path = root / path
    return shlex.split(path.read_text(encoding="utf-8"))


def _runner(runner_cls, root: Path):
    runner = object.__new__(runner_cls)
    runner._state_lock = RLock()
    runner._prepared_preset_cache = {}
    runner.work_dir = str(root)
    runner.lists_dir = str(root / "lists")
    runner.bin_dir = str(root / "bin")
    return runner


class Winws2LaunchIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        from winws_runtime.runners.zapret2_runner import Winws2StrategyRunner

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.runner = _runner(Winws2StrategyRunner, self.root)

    def test_at_config_args_equal_preset_args_for_every_builtin(self) -> None:
        paths = _builtin_paths("winws2")
        self.assertGreater(len(paths), 100)
        for path in paths:
            with self.subTest(preset=path.name):
                text = path.read_text(encoding="utf-8")
                artifact = self.runner._compile_preset_artifact(str(path))
                self.assertEqual(artifact.normalized_text, text)
                expected = launch_args_from_preset_text(text)
                self.assertEqual(_config_args(artifact.launch_args, self.root), expected)

                dry_run = self.runner._artifact_for_dry_run_locked(artifact)
                self.assertEqual(_config_args(dry_run.launch_args, self.root), [*expected, *WINWS2_DRY_RUN_EXTRA_ARGS])

                handoff = self.runner._artifact_for_handoff_locked(artifact)
                self.assertEqual(_config_args(handoff.launch_args, self.root), [*expected, *FAST_SWITCH_HANDOFF_EXTRA_ARGS])

    def test_quoted_arguments_survive_the_at_config_round_trip(self) -> None:
        preset = self.root / "quoted.txt"
        preset.write_text(
            "# Preset: quoted\n"
            "--wf-tcp-out=443\n"
            "--new\n"
            "--name=youtube.com (QUIC) it's\n"
            "--filter-tcp=443 --hostlist=lists/a b.txt\n"
            '--lua-desync=fake:blob=tls_google:tls_mod="rnd,dupsid"\n',
            encoding="utf-8",
        )
        artifact = self.runner._compile_preset_artifact(str(preset))
        self.assertEqual(
            _config_args(artifact.launch_args, self.root),
            [
                "--wf-tcp-out=443",
                "--new",
                "--name=youtube.com (QUIC) it's",
                "--filter-tcp=443",
                "--hostlist=lists/a b.txt",
                '--lua-desync=fake:blob=tls_google:tls_mod="rnd,dupsid"',
            ],
        )

if __name__ == "__main__":
    unittest.main()
