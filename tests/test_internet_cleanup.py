from __future__ import annotations

import unittest
from types import SimpleNamespace


class InternetCleanupTests(unittest.TestCase):
    def test_reset_command_plan_uses_system_executables_without_cmd_shell(self) -> None:
        from windows_features.internet_cleanup import build_internet_cleanup_commands

        commands = build_internet_cleanup_commands(
            resolve_system_exe=lambda name: f"C:/Windows/System32/{name}",
        )

        args_list = [command.args for command in commands]
        self.assertEqual(
            args_list,
            [
                ("C:/Windows/System32/netsh.exe", "int", "ip", "reset"),
                ("C:/Windows/System32/netsh.exe", "winhttp", "reset", "proxy"),
                ("C:/Windows/System32/netsh.exe", "winsock", "reset"),
                ("C:/Windows/System32/netsh.exe", "interface", "ipv4", "reset"),
                ("C:/Windows/System32/netsh.exe", "interface", "ipv6", "reset"),
                (
                    "C:/Windows/System32/netsh.exe",
                    "int",
                    "ipv4",
                    "set",
                    "dynamicport",
                    "tcp",
                    "start=10000",
                    "num=30000",
                ),
            ],
        )
        self.assertFalse(any("cmd.exe" in part.lower() for args in args_list for part in args))
        self.assertTrue(all(command.timeout_seconds > 0 for command in commands))

    def test_run_internet_cleanup_reports_success_and_uses_native_dns_flush(self) -> None:
        from windows_features.internet_cleanup import run_internet_cleanup

        calls: list[tuple[str, ...]] = []
        statuses: list[str] = []
        dns_flush_calls: list[bool] = []

        def command_runner(args, **_kwargs):
            calls.append(tuple(args))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        result = run_internet_cleanup(
            command_runner=command_runner,
            flush_dns_cache=lambda: dns_flush_calls.append(True) or True,
            status_callback=statuses.append,
            resolve_system_exe=lambda name: f"C:/Windows/System32/{name}",
        )

        self.assertEqual(result.level, "success")
        self.assertIn("перезагруз", result.content.lower())
        self.assertEqual(len(calls), 6)
        self.assertEqual(dns_flush_calls, [True])
        self.assertTrue(statuses[0].startswith("Сброс TCP/IP"))

    def test_run_internet_cleanup_decodes_command_error_bytes(self) -> None:
        from windows_features.internet_cleanup import run_internet_cleanup

        def command_runner(_args, **_kwargs):
            return SimpleNamespace(
                returncode=1,
                stdout="требуется повышение прав\n".encode("utf-8"),
                stderr=b"",
            )

        result = run_internet_cleanup(
            command_runner=command_runner,
            flush_dns_cache=lambda: True,
            resolve_system_exe=lambda name: f"C:/Windows/System32/{name}",
        )

        self.assertEqual(result.level, "warning")
        self.assertIn("требуется повышение прав", result.content)
        self.assertNotIn("\\xd1", result.content)

    def test_run_internet_cleanup_prefers_error_line_over_ok_line(self) -> None:
        from windows_features.internet_cleanup import run_internet_cleanup

        output = "Сброс глобальных параметров - OK!\nОтказано в доступе.\n"

        def command_runner(_args, **_kwargs):
            return SimpleNamespace(returncode=1, stdout=output.encode("cp866"), stderr=b"")

        result = run_internet_cleanup(
            command_runner=command_runner,
            flush_dns_cache=lambda: True,
            resolve_system_exe=lambda name: f"C:/Windows/System32/{name}",
        )

        self.assertIn("Отказано в доступе.", result.content)
        self.assertNotIn("код 1, Сброс глобальных параметров - OK!", result.content)

    def test_run_internet_cleanup_repairs_predecoded_netsh_mojibake(self) -> None:
        from windows_features.internet_cleanup import run_internet_cleanup

        def command_runner(_args, **_kwargs):
            return SimpleNamespace(
                returncode=1,
                stdout="Сброс - сбой.".encode("cp1251").decode("cp866"),
                stderr="",
            )

        result = run_internet_cleanup(
            command_runner=command_runner,
            flush_dns_cache=lambda: True,
            resolve_system_exe=lambda name: f"C:/Windows/System32/{name}",
        )

        self.assertIn("Сброс - сбой.", result.content)
        self.assertNotIn("сЁюё", result.content)

    def test_run_internet_cleanup_stops_between_commands(self) -> None:
        from windows_features.internet_cleanup import run_internet_cleanup

        calls: list[tuple[str, ...]] = []
        stop_checks = 0

        def command_runner(args, **_kwargs):
            calls.append(tuple(args))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        def should_stop() -> bool:
            nonlocal stop_checks
            stop_checks += 1
            return bool(calls)

        result = run_internet_cleanup(
            command_runner=command_runner,
            flush_dns_cache=lambda: True,
            should_stop=should_stop,
            resolve_system_exe=lambda name: f"C:/Windows/System32/{name}",
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(result.level, "error")
        self.assertIn("остановлен", result.content)
        self.assertGreaterEqual(stop_checks, 2)

    def test_internet_cleanup_confirmation_plan_warns_about_reboot(self) -> None:
        import presets.ui.control.control_runtime as control_runtime

        plan = control_runtime.build_internet_cleanup_start_plan(language="ru")

        self.assertFalse(plan.blocked)
        self.assertEqual(plan.start_status, "Сброс сети Windows...")
        self.assertEqual(len(plan.confirmations), 1)
        self.assertIn("перезагрузка", plan.confirmations[0].content.lower())


if __name__ == "__main__":
    unittest.main()
