from __future__ import annotations

import inspect
import unittest


class PageFactoryStartupMetricsTests(unittest.TestCase):
    def test_page_factory_logs_import_deps_and_constructor_steps(self) -> None:
        from ui.page_factory import UiPageFactory

        source = inspect.getsource(UiPageFactory.create_page)

        self.assertIn('"factory.import"', source)
        self.assertIn('"factory.deps"', source)
        self.assertIn('"factory.constructor"', source)


if __name__ == "__main__":
    unittest.main()
