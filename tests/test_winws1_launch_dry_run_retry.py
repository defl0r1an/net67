import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


class Winws1LaunchDryRunRetryTests(unittest.TestCase):
    def _runner(self, root: Path):
        from winws_runtime.runners.zapret1_runner import Winws1StrategyRunner

        exe = root / "exe" / "winws.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("", encoding="utf-8")

        runner = object.__new__(Winws1StrategyRunner)
        runner.winws_exe = str(exe)
        runner.work_dir = str(root)
        runner.lists_dir = str(root / "lists")
        runner.bin_dir = str(root / "bin")
        runner._state_lock = threading.RLock()
        runner._prepared_preset_cache = {}
        runner.running_process = None
        runner._preset_file_path = ""
        runner.last_error = None
        runner._last_spawn_exit_code = None
        runner._last_spawn_stderr = ""
        runner._set_last_error = Mock()
        runner._set_runner_state_locked = Mock()
        runner._prepare_cleanup_before_spawn_locked = Mock()
        runner._ensure_windivert_ready_before_spawn = Mock(return_value=True)
        return runner

    def test_start_does_not_spawn_when_dry_run_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            preset_path = root / "selected.txt"
            config_path = root / "tmp" / "winws1_at_config" / "selected.txt"
            config_path.parent.mkdir(parents=True)
            preset_path.write_text("--wf-tcp=443", encoding="utf-8")
            config_path.write_text("--wf-tcp=443\n", encoding="utf-8")

            runner = self._runner(root)
            runner._compile_preset_artifact = Mock(
                return_value=SimpleNamespace(
                    validation_ok=True,
                    validation_report="",
                    preset_path=str(preset_path),
                    launch_args=(f"@{config_path}",),
                )
            )
            runner._run_preset_dry_run_locked = Mock(return_value=False)
            runner._spawn_process_locked = Mock(return_value=True)

            ok = runner._start_from_preset_file_locked(
                str(preset_path),
                "Selected",
                retry_count=0,
                max_retries=2,
            )

            self.assertFalse(ok)
            runner._run_preset_dry_run_locked.assert_called_once()
            runner._spawn_process_locked.assert_not_called()

    def test_start_retries_code_one_without_stderr_after_successful_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            preset_path = root / "selected.txt"
            config_path = root / "tmp" / "winws1_at_config" / "selected.txt"
            config_path.parent.mkdir(parents=True)
            preset_path.write_text("--wf-tcp=443", encoding="utf-8")
            config_path.write_text("--wf-tcp=443\n", encoding="utf-8")

            runner = self._runner(root)
            runner._compile_preset_artifact = Mock(
                return_value=SimpleNamespace(
                    validation_ok=True,
                    validation_report="",
                    preset_path=str(preset_path),
                    launch_args=(f"@{config_path}",),
                )
            )
            runner._run_preset_dry_run_locked = Mock(return_value=True)

            def spawn_then_success(*_args, **_kwargs):
                if runner._spawn_process_locked.call_count == 1:
                    runner._last_spawn_exit_code = 1
                    runner._last_spawn_stderr = ""
                    return False
                return True

            runner._spawn_process_locked = Mock(side_effect=spawn_then_success)

            ok = runner._start_from_preset_file_locked(
                str(preset_path),
                "Selected",
                retry_count=0,
                max_retries=2,
            )

            self.assertTrue(ok)
            self.assertEqual(runner._spawn_process_locked.call_count, 2)
            runner._prepare_cleanup_before_spawn_locked.assert_any_call(retry_count=0)
            runner._prepare_cleanup_before_spawn_locked.assert_any_call(retry_count=1)


if __name__ == "__main__":
    unittest.main()
