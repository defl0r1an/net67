from __future__ import annotations

import subprocess
import sys
import unittest


class AppPackageLazyImportTests(unittest.TestCase):
    def test_importing_ui_texts_does_not_load_runtime_feature_stack(self) -> None:
        script = (
            "import sys\n"
            "import app.ui_texts\n"
            "blocked = [\n"
            "    'app.feature_assembly',\n"
            "    'app.runtime',\n"
            "    'app.feature_facades',\n"
            "]\n"
            "print('\\n'.join(name for name in blocked if name in sys.modules))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            cwd=".",
            env={"PYTHONPATH": "src"},
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
