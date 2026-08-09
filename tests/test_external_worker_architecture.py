from __future__ import annotations

import inspect
import unittest

from app.feature_facades.external import ExternalActionsFeature
import app.external_workers as external_workers


class ExternalWorkerArchitectureTests(unittest.TestCase):
    def test_open_url_worker_receives_feature_action_not_feature_object(self) -> None:
        feature_source = inspect.getsource(ExternalActionsFeature)
        worker_source = inspect.getsource(external_workers.ExternalOpenUrlWorker)

        self.assertNotIn("external_actions_feature=self", feature_source)
        self.assertNotIn("self._external_actions", worker_source)
        self.assertIn("open_url=self.open_url", feature_source)
        self.assertIn("_open_url", worker_source)
        self.assertNotIn("external_commands", worker_source)
        self.assertIn("def _commands", feature_source)
        self.assertNotIn("def _actions", feature_source)


if __name__ == "__main__":
    unittest.main()
