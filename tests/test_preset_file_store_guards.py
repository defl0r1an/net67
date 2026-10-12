from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.paths import AppPaths
from presets.file_store import PresetFileStore
from settings.mode import ENGINE_WINWS2


class PresetFileStoreGuardTests(unittest.TestCase):
    def test_update_preset_skips_write_when_source_text_is_unchanged(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            user_dir = root / "presets" / "winws2"
            user_dir.mkdir(parents=True)
            preset_path = user_dir / "Default v5.txt"
            preset_path.write_text(
                "# Preset: Default v5\n--new\n--filter-tcp=443\n",
                encoding="utf-8",
            )
            store = PresetFileStore(AppPaths(user_root=root, local_root=root))

            with patch.object(
                store,
                "_write_source",
                side_effect=AssertionError("unchanged preset source must not be written"),
            ):
                manifest = store.update_preset(
                    ENGINE_WINWS2,
                    "Default v5.txt",
                    "# Preset: Default v5\r\n--new\r\n--filter-tcp=443\r\n",
                    None,
                )

        self.assertEqual(manifest.file_name, "Default v5.txt")

    def test_file_written_in_the_same_clock_tick_is_seen(self) -> None:
        """Время папки на Windows идёт шагами системных часов (около 16 мс), а размер
        папки всегда 0. Два файла, записанные за один шаг, оставляли ключ кэша
        прежним, и список пресетов не видел второго: «Preset not found» примерно
        в одном прогоне теста сохранения из семи. Здесь тот же шаг воспроизводится
        честно — время папки после второго файла возвращается назад."""
        import os

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = PresetFileStore(AppPaths(user_root=root, local_root=root))
            builtin_dir = store._paths.engine_paths(ENGINE_WINWS2).ensure_directories().builtin_presets_dir
            (builtin_dir / "First.txt").write_text("# Preset: First\n--new\n", encoding="utf-8")
            before = os.stat(builtin_dir)
            self.assertIsNotNone(store.get_manifest(ENGINE_WINWS2, "First.txt"))

            (builtin_dir / "Second.txt").write_text("# Preset: Second\n--new\n", encoding="utf-8")
            os.utime(builtin_dir, ns=(before.st_atime_ns, before.st_mtime_ns))

            self.assertIsNotNone(store.get_manifest(ENGINE_WINWS2, "Second.txt"))


if __name__ == "__main__":
    unittest.main()
