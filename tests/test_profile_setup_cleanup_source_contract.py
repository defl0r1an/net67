from __future__ import annotations

import ast
from pathlib import Path
import unittest


class ProfileSetupCleanupSourceContractTests(unittest.TestCase):
    def test_profile_setup_cleanup_waits_only_for_write_workers(self) -> None:
        source_path = Path(__file__).resolve().parents[1] / "src" / "profile" / "ui" / "profile_setup_page.py"
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        cleanup_table = None
        for node in module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "_PROFILE_SETUP_CLEANUP_RUNTIMES":
                        cleanup_table = ast.literal_eval(node.value)
                        break
            if cleanup_table is not None:
                break

        self.assertIsNotNone(cleanup_table)
        cleanup_by_attr = {entry[0]: entry[2] for entry in cleanup_table}

        for attr in (
            "_setup_load_runtime",
            "_list_file_load_runtime",
            "_list_file_validation_runtime",
        ):
            self.assertIs(cleanup_by_attr[attr], False)

        for attr in (
            "_list_file_save_runtime",
            "_settings_save_runtime",
            "_raw_profile_save_runtime",
            "_enabled_save_runtime",
            "_user_profile_update_runtime",
            "_user_profile_delete_runtime",
            "_strategy_apply_runtime",
            "_strategy_feedback_save_runtime",
        ):
            self.assertIs(cleanup_by_attr[attr], True)


if __name__ == "__main__":
    unittest.main()
