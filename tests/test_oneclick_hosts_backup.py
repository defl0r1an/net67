from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class HostsBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.written: list[str] = []

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, content: str) -> bool:
        self.written.append(content)
        return True

    def test_backup_creates_both_copies(self) -> None:
        from oneclick.hosts_backup import create_backup, has_backup

        ok, _ = create_backup(root=self.root, read_hosts=lambda: "127.0.0.1 localhost\n")

        self.assertTrue(ok)
        self.assertTrue(has_backup(self.root))
        self.assertTrue(has_backup(self.root, original=True))

    def test_original_is_never_overwritten(self) -> None:
        """Иначе после первой же правки исходник потерян навсегда."""
        from oneclick.hosts_backup import create_backup, original_backup_path, last_backup_path

        create_backup(root=self.root, read_hosts=lambda: "ORIGINAL\n")
        create_backup(root=self.root, read_hosts=lambda: "ALREADY MODIFIED\n")

        self.assertEqual(original_backup_path(self.root).read_text(encoding="utf-8"), "ORIGINAL\n")
        self.assertEqual(last_backup_path(self.root).read_text(encoding="utf-8"), "ALREADY MODIFIED\n")

    def test_restore_writes_last_backup(self) -> None:
        from oneclick.hosts_backup import create_backup, restore_backup

        create_backup(root=self.root, read_hosts=lambda: "BEFORE\n")
        ok, _ = restore_backup(root=self.root, write_hosts=self._write)

        self.assertTrue(ok)
        self.assertEqual(self.written, ["BEFORE\n"])

    def test_restore_original_returns_first_state(self) -> None:
        from oneclick.hosts_backup import create_backup, restore_backup

        create_backup(root=self.root, read_hosts=lambda: "ORIGINAL\n")
        create_backup(root=self.root, read_hosts=lambda: "MODIFIED\n")

        restore_backup(root=self.root, write_hosts=self._write, use_original=True)

        self.assertEqual(self.written, ["ORIGINAL\n"])

    def test_restore_without_backup_fails_cleanly(self) -> None:
        from oneclick.hosts_backup import restore_backup

        ok, message = restore_backup(root=self.root, write_hosts=self._write)

        self.assertFalse(ok)
        self.assertIn("не найдена", message.lower())
        self.assertEqual(self.written, [])

    def test_unreadable_hosts_does_not_create_backup(self) -> None:
        from oneclick.hosts_backup import create_backup, has_backup

        ok, _ = create_backup(root=self.root, read_hosts=lambda: None)

        self.assertFalse(ok)
        self.assertFalse(has_backup(self.root))

    def test_read_exception_is_reported_not_raised(self) -> None:
        from oneclick.hosts_backup import create_backup

        def boom():
            raise PermissionError("отказано в доступе")

        ok, message = create_backup(root=self.root, read_hosts=boom)

        self.assertFalse(ok)
        self.assertIn("отказано в доступе", message)

    def test_failed_write_is_reported(self) -> None:
        from oneclick.hosts_backup import create_backup, restore_backup

        create_backup(root=self.root, read_hosts=lambda: "BEFORE\n")
        ok, message = restore_backup(root=self.root, write_hosts=lambda _c: False)

        self.assertFalse(ok)
        self.assertIn("записать", message.lower())


if __name__ == "__main__":
    unittest.main()
