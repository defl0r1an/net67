from __future__ import annotations

import importlib.util
import inspect
import unittest

import about.plans as about_plans


class AboutActionsArchitectureTests(unittest.TestCase):
    def test_about_open_actions_live_in_commands_not_plans(self) -> None:
        spec = importlib.util.find_spec("about.commands")

        self.assertIsNotNone(spec)

        import about.commands as about_commands

        plans_source = inspect.getsource(about_plans)
        commands_source = inspect.getsource(about_commands)

        self.assertNotIn("about.commands", plans_source)
        self.assertNotIn("open_support_discussions", plans_source)
        self.assertNotIn("open_telegram", plans_source)
        self.assertNotIn("open_discord", plans_source)
        self.assertNotIn("open_github", plans_source)
        self.assertNotIn("open_help_folder", plans_source)
        self.assertNotIn("subprocess", plans_source)
        self.assertNotIn("webbrowser.open", plans_source)
        self.assertNotIn("open_help_folder", commands_source)
        self.assertIn("webbrowser.open", commands_source)
        self.assertNotIn("subprocess.Popen", commands_source)


if __name__ == "__main__":
    unittest.main()
