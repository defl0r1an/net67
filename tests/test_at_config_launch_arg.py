"""Путь к @config не должен содержать пробелов.

winws и winws2 — cygwin-бинарники. Аргумент вида
``@C:\\Program Files\\net67\\tmp\\winws2_at_x.txt`` они не разбирают:
процесс печатает баннер версии и выходит с кодом 1, ни слова о пути.

Поймано на разнице между машинами. Один и тот же пресет, один и тот же
@config (совпал sha1 и размер в байтах):

    C:\\Users\\User\\Downloads\\...\\artifact   — запускается
    C:\\Program Files\\net67                    — «код 1»

Пробел был единственным отличием. Поэтому аргумент строится относительно
рабочего каталога — winws всё равно запускается с cwd=work_dir.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class RelativeArgTests(unittest.TestCase):
    def test_config_inside_work_dir_becomes_relative(self) -> None:
        from winws_runtime.runners.preset_runner_support import at_config_launch_arg

        arg = at_config_launch_arg(
            os.path.join("C:", os.sep, "Program Files", "net67", "tmp", "winws2_at_config", "a.txt"),
            os.path.join("C:", os.sep, "Program Files", "net67"),
        )

        self.assertTrue(arg.startswith("@"))
        self.assertNotIn(" ", arg)
        self.assertIn("winws2_at_config", arg)

    def test_no_spaces_for_any_install_path(self) -> None:
        """Пробел может быть где угодно: и в Program Files, и в имени пользователя."""
        from winws_runtime.runners.preset_runner_support import at_config_launch_arg

        for root in (
            os.path.join("C:", os.sep, "Program Files", "net67"),
            os.path.join("C:", os.sep, "Users", "Иван Петров", "net 67"),
            os.path.join("D:", os.sep, "net67"),
        ):
            with self.subTest(root=root):
                arg = at_config_launch_arg(os.path.join(root, "tmp", "cfg.txt"), root)
                self.assertNotIn(" ", arg, f"пробел уцелел для {root}")

    def test_config_outside_work_dir_is_not_faked_into_relative(self) -> None:
        """«..\\..\\что-то» зависит от cwd не меньше абсолютного пути."""
        from winws_runtime.runners.preset_runner_support import at_config_launch_arg

        arg = at_config_launch_arg(
            os.path.join("C:", os.sep, "elsewhere", "cfg.txt"),
            os.path.join("C:", os.sep, "net67"),
        )

        self.assertNotIn("..", arg)

    def test_empty_path_gives_empty_arg(self) -> None:
        from winws_runtime.runners.preset_runner_support import at_config_launch_arg

        self.assertEqual(at_config_launch_arg("", "C:\\net67"), "")


class RunnersUseTheHelperTests(unittest.TestCase):
    """Прямая сборка «@» + путь не должна вернуться ни в один запуск."""

    FILES = (
        "winws_runtime/runners/zapret1_runner.py",
        "winws_runtime/runners/zapret2_runner.py",
    )

    def test_no_raw_at_prefix_left(self) -> None:
        for name in self.FILES:
            source = (PROJECT_SRC / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertNotIn('f"@{', source, "путь снова склеивается вручную")
                self.assertIn("at_config_launch_arg", source)

    def test_dry_run_logs_arguments_and_cwd(self) -> None:
        """Без них баннер версии в логе ничего не объясняет."""
        import inspect

        from winws_runtime.runners.zapret2_runner import Winws2StrategyRunner

        source = inspect.getsource(Winws2StrategyRunner._run_preset_dry_run_locked)

        self.assertIn("args=", source)
        self.assertIn("cwd=", source)


if __name__ == "__main__":
    unittest.main()
