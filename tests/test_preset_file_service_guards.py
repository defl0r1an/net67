from __future__ import annotations

import unittest
from types import SimpleNamespace

from presets.file_service import PresetFileService
from presets.models import PresetManifest
from settings.mode import ENGINE_WINWS2, ZAPRET2_MODE


class PresetFileServiceGuardTests(unittest.TestCase):
    def test_save_same_source_text_skips_file_write_and_content_signal(self) -> None:
        manifest = PresetManifest(
            file_name="Default v5.txt",
            name="Default v5",
            updated_at="",
            kind="user",
            storage_scope="user",
        )

        class _PresetModeCoordinator:
            def get_selected_source_manifest(self, _launch_method):
                return manifest

        class _PresetFileStore:
            def get_manifest(self, _engine, _file_name):
                return manifest

            def resolve_file_name(self, _engine, file_name):
                return file_name

            def read_source_text(self, _engine, _file_name):
                return "# Preset: Default v5\n--new\n--filter-tcp=443\n"

            def update_preset(self, *_args, **_kwargs):
                raise AssertionError("unchanged preset source must not be written")

        class _PresetUiStore:
            def notify_preset_content_changed(self, _file_name):
                raise AssertionError("unchanged preset source must not notify UI")

        store = _PresetUiStore()
        service = PresetFileService(
            engine=ENGINE_WINWS2,
            launch_method=ZAPRET2_MODE,
            app_paths=SimpleNamespace(),
            preset_mode_coordinator=_PresetModeCoordinator(),
            preset_file_store=_PresetFileStore(),
            preset_selection_service=SimpleNamespace(),
            preset_store_winws2=store,
            preset_store_winws1=store,
        )

        result = service.save_source_text_by_file_name(
            "Default v5.txt",
            "# Modified: today\r\n# Preset: Default v5\r\n--new\r\n--filter-tcp=443\r\n",
        )

        self.assertEqual(result, manifest)


if __name__ == "__main__":
    unittest.main()
