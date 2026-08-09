from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.feature_facades.presets import PresetsFeature
from core.paths import AppPaths
from presets.models import PresetManifest
from presets.raw_preset_editor_workflow import load_raw_preset_for_file
from settings.mode import ENGINE_WINWS2, ZAPRET2_MODE


class _Feature(PresetsFeature):
    def __init__(self, app_paths: AppPaths, manifests: list[PresetManifest]) -> None:
        super().__init__(_services=SimpleNamespace(app_paths=app_paths))
        self._manifests = list(manifests)

    def list_preset_manifests(self, _launch_method: str):
        return list(self._manifests)

    def get_preset_manifest_by_file_name(self, _launch_method: str, file_name: str):
        candidate = str(file_name or "").strip().lower()
        for manifest in self._manifests:
            if str(manifest.file_name or "").strip().lower() == candidate:
                return manifest
        return None


class PresetBuiltinResetHashTests(unittest.TestCase):
    def _feature_with_files(self, *, user_text: str, builtin_text: str) -> _Feature:
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        app_paths = AppPaths(user_root=root, local_root=root)
        engine_paths = app_paths.engine_paths(ENGINE_WINWS2).ensure_directories()
        (engine_paths.user_presets_dir / "Default.txt").write_text(user_text, encoding="utf-8")
        (engine_paths.builtin_presets_dir / "Default.txt").write_text(builtin_text, encoding="utf-8")
        return _Feature(
            app_paths,
            [
                PresetManifest(
                    file_name="Default.txt",
                    name="Default",
                    updated_at="",
                    kind="user",
                    storage_scope="user",
                )
            ],
        )

    def test_list_snapshot_never_reads_preset_contents_for_reset_flag(self) -> None:
        feature = self._feature_with_files(
            user_text="# Preset: Default\n--new\n--filter-tcp=443\n",
            builtin_text="# Preset: Default\n--new\n",
        )

        with patch.object(
            PresetsFeature,
            "_file_sha256",
            side_effect=AssertionError("list snapshot must not hash preset files"),
        ):
            _signature, metadata = feature._build_preset_list_metadata_snapshot(ZAPRET2_MODE)
            feature._build_preset_list_metadata_signature(ZAPRET2_MODE)

        # Флаг в снапшоте всегда False: он вычисляется лениво для одного файла.
        self.assertFalse(metadata["Default.txt"]["can_reset_to_builtin"])

    def test_single_file_check_detects_user_override_by_hash(self) -> None:
        same_feature = self._feature_with_files(
            user_text="# Preset: Default\n--new\n",
            builtin_text="# Preset: Default\n--new\n",
        )
        self.assertFalse(
            same_feature.preset_differs_from_builtin_by_file_name(ZAPRET2_MODE, "Default.txt")
        )

        different_feature = self._feature_with_files(
            user_text="# Preset: Default\n--new\n--filter-tcp=443\n",
            builtin_text="# Preset: Default\n--new\n",
        )
        self.assertTrue(
            different_feature.preset_differs_from_builtin_by_file_name(ZAPRET2_MODE, "Default.txt")
        )

    def test_read_single_preset_list_metadata_keeps_lazy_reset_flag(self) -> None:
        feature = self._feature_with_files(
            user_text="# Preset: Default\n--new\n--filter-tcp=443\n",
            builtin_text="# Preset: Default\n--new\n",
        )

        refreshed = feature.read_single_preset_list_metadata(ZAPRET2_MODE, "Default.txt")

        self.assertIsNotNone(refreshed)
        file_name, metadata = refreshed
        self.assertEqual(file_name, "Default.txt")
        self.assertTrue(metadata["can_reset_to_builtin"])

    def test_page_menu_reset_flag_uses_lazy_single_file_checker(self) -> None:
        from presets.ui.common.user_presets_page import UserPresetsPageBase

        checker = Mock(return_value=True)
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._presets_model = None
        page._runtime_service = SimpleNamespace(cached_presets_metadata=lambda: {})
        page._preset_runtime_actions = SimpleNamespace(
            preset_differs_from_builtin_by_file_name=checker,
        )
        page._config = SimpleNamespace(launch_method=ZAPRET2_MODE)

        self.assertTrue(UserPresetsPageBase._can_reset_preset_to_builtin(page, "Default"))
        checker.assert_called_once_with(ZAPRET2_MODE, "Default.txt")

    def test_page_menu_reset_flag_skips_checker_for_builtin_presets(self) -> None:
        from presets.ui.common.user_presets_page import UserPresetsPageBase

        checker = Mock(return_value=True)
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._presets_model = None
        page._runtime_service = SimpleNamespace(
            cached_presets_metadata=lambda: {"Default.txt": {"is_builtin": True}},
        )
        page._preset_runtime_actions = SimpleNamespace(
            preset_differs_from_builtin_by_file_name=checker,
        )
        page._config = SimpleNamespace(launch_method=ZAPRET2_MODE)

        self.assertFalse(UserPresetsPageBase._can_reset_preset_to_builtin(page, "Default.txt"))
        checker.assert_not_called()

    def test_raw_preset_load_result_uses_hash_reset_flag(self) -> None:
        feature = self._feature_with_files(
            user_text="# Preset: Default\n--new\n",
            builtin_text="# Preset: Default\n--new\n",
        )
        feature.get_preset_manifest_by_file_name = lambda _method, _name: feature._manifests[0]
        feature.get_preset_source_path_by_file_name = lambda _method, _name: (
            feature._services.app_paths.engine_paths(ENGINE_WINWS2).user_presets_dir / "Default.txt"
        )
        feature.get_selected_source_preset_file_name = lambda _method: ""
        feature.get_selected_source_preset_manifest = lambda _method: None

        result = load_raw_preset_for_file(
            presets_feature=feature,
            launch_method=ZAPRET2_MODE,
            file_name="Default.txt",
        )

        self.assertFalse(result.can_reset_to_builtin)


if __name__ == "__main__":
    unittest.main()
