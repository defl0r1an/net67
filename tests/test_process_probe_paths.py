import unittest
from unittest.mock import patch

from winws_runtime.runtime import process_probe


class ProcessProbePathTests(unittest.TestCase):
    def test_normalize_path_strips_extended_windows_prefix(self) -> None:
        with (
            patch.object(process_probe.os.path, "abspath", side_effect=lambda value: value),
            patch.object(process_probe.os.path, "normcase", side_effect=lambda value: value.lower()),
        ):
            normalized = process_probe._normalize_path(r"\\?\C:\Zapret\Dev\exe\winws2.exe")

        self.assertEqual(normalized, r"c:\zapret\dev\exe\winws2.exe")

    def test_normalize_path_strips_extended_unc_prefix(self) -> None:
        with (
            patch.object(process_probe.os.path, "abspath", side_effect=lambda value: value),
            patch.object(process_probe.os.path, "normcase", side_effect=lambda value: value.lower()),
        ):
            normalized = process_probe._normalize_path(r"\\?\UNC\server\share\winws.exe")

        self.assertEqual(normalized, r"\\server\share\winws.exe")


if __name__ == "__main__":
    unittest.main()
