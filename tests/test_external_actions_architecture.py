from __future__ import annotations

import inspect
import unittest

import app.external_actions as external_actions
import app.external_commands as external_commands
from app.feature_facades.external import ExternalActionsFeature


class ExternalActionsArchitectureTests(unittest.TestCase):
    def test_external_open_url_system_action_lives_in_commands(self) -> None:
        actions_source = inspect.getsource(external_actions)
        commands_source = inspect.getsource(external_commands)
        feature_source = inspect.getsource(ExternalActionsFeature)

        self.assertNotIn("webbrowser", actions_source)
        self.assertIn("webbrowser.open", commands_source)
        self.assertIn("def _commands", feature_source)
        self.assertNotIn("def _actions", feature_source)


if __name__ == "__main__":
    unittest.main()
