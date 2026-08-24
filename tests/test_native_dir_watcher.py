from __future__ import annotations

import unittest

from presets.native_dir_watcher import (
    FILE_ACTION_ADDED,
    FILE_ACTION_MODIFIED,
    FILE_ACTION_REMOVED,
    FILE_ACTION_RENAMED_NEW_NAME,
    FILE_ACTION_RENAMED_OLD_NAME,
    NativePresetsDirWatcher,
    parse_file_notify_information,
)


def _notify_entry(action: int, name: str, *, next_offset: int | None = None) -> bytes:
    encoded_name = name.encode("utf-16-le")
    body = (
        action.to_bytes(4, "little")
        + len(encoded_name).to_bytes(4, "little")
        + encoded_name
    )
    entry_length = 4 + len(body)
    if next_offset is None:
        next_offset = 0
    # Выравнивание записи до next_offset нулями, как делает ядро.
    padding = b"\x00" * max(0, next_offset - entry_length)
    return next_offset.to_bytes(4, "little") + body + padding


class ParseFileNotifyInformationTests(unittest.TestCase):
    def test_parses_single_entry(self) -> None:
        buffer = _notify_entry(FILE_ACTION_MODIFIED, "Default.txt")

        self.assertEqual(
            parse_file_notify_information(buffer),
            [(FILE_ACTION_MODIFIED, "Default.txt")],
        )

    def test_parses_chained_entries_with_alignment_padding(self) -> None:
        first = _notify_entry(FILE_ACTION_RENAMED_OLD_NAME, "Old.txt", next_offset=40)
        second = _notify_entry(FILE_ACTION_RENAMED_NEW_NAME, "New name.txt")

        events = parse_file_notify_information(first + second)

        self.assertEqual(
            events,
            [
                (FILE_ACTION_RENAMED_OLD_NAME, "Old.txt"),
                (FILE_ACTION_RENAMED_NEW_NAME, "New name.txt"),
            ],
        )

    def test_parses_added_and_removed_actions(self) -> None:
        added = _notify_entry(FILE_ACTION_ADDED, "Added.txt", next_offset=40)
        removed = _notify_entry(FILE_ACTION_REMOVED, "Removed.txt")

        self.assertEqual(
            parse_file_notify_information(added + removed),
            [
                (FILE_ACTION_ADDED, "Added.txt"),
                (FILE_ACTION_REMOVED, "Removed.txt"),
            ],
        )

    def test_ignores_truncated_and_empty_buffers(self) -> None:
        self.assertEqual(parse_file_notify_information(b""), [])
        self.assertEqual(parse_file_notify_information(b"\x00" * 8), [])

        truncated = _notify_entry(FILE_ACTION_MODIFIED, "Default.txt")[:-4]
        self.assertEqual(parse_file_notify_information(truncated), [])

    def test_stops_on_zero_next_offset_instead_of_looping(self) -> None:
        entry = _notify_entry(FILE_ACTION_MODIFIED, "Default.txt", next_offset=0)
        trailing_garbage = b"\xff" * 16

        self.assertEqual(
            parse_file_notify_information(entry + trailing_garbage),
            [(FILE_ACTION_MODIFIED, "Default.txt")],
        )


class NativePresetsDirWatcherTests(unittest.TestCase):
    def test_start_watching_fails_gracefully_for_missing_directory(self) -> None:
        watcher = NativePresetsDirWatcher(r"Z:\definitely\missing\presets\dir")

        self.assertFalse(watcher.start_watching())

    def test_watcher_declares_qt_signals(self) -> None:
        for signal_name in ("events", "overflowed", "failed"):
            self.assertTrue(hasattr(NativePresetsDirWatcher, signal_name))


if __name__ == "__main__":
    unittest.main()
