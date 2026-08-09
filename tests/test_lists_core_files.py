from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


class ListsCoreFilesTests(unittest.TestCase):
    def test_write_text_file_keeps_existing_file_when_prepare_fails(self) -> None:
        from lists.core import files

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "ipset-amazon.txt"
            target.write_text("old\n", encoding="utf-8")

            with patch("lists.core.files.normalize_newlines", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    files.write_text_file(str(target), "new\n")

            self.assertEqual(target.read_text(encoding="utf-8"), "old\n")

    def test_write_text_file_skips_replace_when_content_is_unchanged(self) -> None:
        from lists.core import files

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "cloudflare.txt"
            target.write_text("cloudflare.com\n", encoding="utf-8")

            with patch("lists.core.files.os.replace", side_effect=PermissionError("locked")) as replace:
                files.write_text_file(str(target), "cloudflare.com\n")

            replace.assert_not_called()
            self.assertEqual(target.read_text(encoding="utf-8"), "cloudflare.com\n")


if __name__ == "__main__":
    unittest.main()
