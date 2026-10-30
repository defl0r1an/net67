from __future__ import annotations

import ast
from pathlib import Path
import unittest


class UpdaterDownloadThreadingImportTests(unittest.TestCase):
    def _source(self, module: str) -> str:
        root = Path(__file__).resolve().parents[1]
        return (root / "src" / "updater" / f"{module}.py").read_text(encoding="utf-8")

    def test_pipeline_imports_threading_for_segments_and_cancellation(self) -> None:
        for module in ("update_pipeline", "download_transfer"):
            with self.subTest(module=module):
                source = self._source(module)
                tree = ast.parse(source)
                imported_names = {
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                }
                self.assertIn("threading", imported_names)
                self.assertIn("threading.Event()", source)
        self.assertIn("threading.Lock()", self._source("download_transfer"))


if __name__ == "__main__":
    unittest.main()
