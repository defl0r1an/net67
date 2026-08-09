from __future__ import annotations

import inspect
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class UserPresetsRowsWorkerArchitectureTests(unittest.TestCase):
    def test_list_metadata_snapshot_uses_file_names_without_reading_preset_headers(self) -> None:
        from app.feature_facades.presets import PresetsFeature
        from core.paths import AppPaths
        from settings.mode import ENGINE_WINWS2, ZAPRET2_MODE

        class _Feature(PresetsFeature):
            def __init__(self, app_paths: AppPaths) -> None:
                super().__init__(_services=SimpleNamespace(app_paths=app_paths))

            def list_preset_manifests(self, _launch_method: str):
                raise AssertionError("list metadata must not read preset manifests")

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_paths = AppPaths(user_root=root, local_root=root)
            engine_paths = app_paths.engine_paths(ENGINE_WINWS2).ensure_directories()
            (engine_paths.builtin_presets_dir / "Slow Header Name.txt").write_text(
                "# Preset: Pretty name from inside\n"
                "# Description: expensive description\n"
                "# IconColor: #ff00ff\n"
                "--new\n",
                encoding="utf-8",
            )
            feature = _Feature(app_paths)

            with patch(
                "presets.lightweight_metadata.read_preset_list_metadata",
                side_effect=AssertionError("list metadata must not read preset headers"),
            ), patch(
                "presets.lightweight_metadata.read_preset_stat_metadata",
                side_effect=AssertionError("list metadata must reuse directory stat data"),
            ):
                _signature, metadata = feature._build_preset_list_metadata_snapshot(ZAPRET2_MODE)

        self.assertEqual(metadata["Slow Header Name.txt"]["display_name"], "Slow Header Name")
        self.assertEqual(metadata["Slow Header Name.txt"]["description"], "")
        self.assertEqual(metadata["Slow Header Name.txt"]["icon_color"], "")
        self.assertNotEqual(metadata["Slow Header Name.txt"]["modified_display"], "")

    def test_runtime_starts_metadata_workers_through_shared_runtime(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        service_source = inspect.getsource(runtime_service.UserPresetsRuntimeService)
        start_sources = "\n".join(
            (
                inspect.getsource(runtime_service.UserPresetsRuntimeService._request_single_metadata_refresh),
                inspect.getsource(runtime_service.UserPresetsRuntimeService.load_presets),
                inspect.getsource(runtime_service.UserPresetsRuntimeService._request_rows_plan_refresh),
            )
        )

        self.assertIn("OneShotWorkerRuntime", service_source)
        self.assertIn("start_qthread_worker", start_sources)
        self.assertNotIn("worker.start()", start_sources)

    def test_runtime_service_keeps_worker_identity_only_in_shared_runtime(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        service_source = inspect.getsource(runtime_service.UserPresetsRuntimeService)

        self.assertNotIn("self._metadata_load_worker", service_source)
        self.assertNotIn("self._single_metadata_worker", service_source)
        self.assertNotIn("self._rows_plan_worker", service_source)
        self.assertNotIn("def _worker_runtime_is_running", service_source)

    def test_runtime_service_uses_shared_state_for_rows_plan_queue(self) -> None:
        import presets.user_presets_runtime_service as runtime_service
        from ui.latest_value_worker_state import LatestValueWorkerState

        service = runtime_service.UserPresetsRuntimeService()
        service_source = inspect.getsource(runtime_service.UserPresetsRuntimeService)
        request_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._request_rows_plan_refresh)
        finished_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._on_rows_plan_worker_finished)
        scheduled_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._run_scheduled_rows_plan_refresh)

        self.assertIsInstance(service._rows_plan_state_obj(), LatestValueWorkerState)
        self.assertIn("_rows_plan_state = LatestValueWorkerState", service_source)
        self.assertIn("_rows_plan_state_obj()", request_source)
        self.assertIn("_rows_plan_state_obj()", finished_source)
        self.assertIn("_rows_plan_state_obj()", scheduled_source)
        self.assertNotIn("_rows_plan_start_scheduled", service_source)

    def test_runtime_service_uses_shared_state_for_full_metadata_load_queue(self) -> None:
        import presets.user_presets_runtime_service as runtime_service
        from ui.latest_value_worker_state import LatestValueWorkerState

        service = runtime_service.UserPresetsRuntimeService()
        init_source = inspect.getsource(runtime_service.UserPresetsRuntimeService.__init__)
        load_source = inspect.getsource(runtime_service.UserPresetsRuntimeService.load_presets)
        finished_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._on_metadata_worker_finished)
        scheduled_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._run_scheduled_metadata_load)
        cleanup_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._stop_metadata_workers)

        self.assertIsInstance(service._metadata_load_state_obj(), LatestValueWorkerState)
        self.assertIn("_metadata_load_state = LatestValueWorkerState", init_source)
        self.assertIn("_metadata_load_state_obj()", load_source)
        self.assertIn("_metadata_load_state_obj()", finished_source)
        self.assertIn("_metadata_load_state_obj()", scheduled_source)
        self.assertIn("_metadata_load_state_obj().reset()", cleanup_source)
        self.assertNotIn("_metadata_load_pending_page = None", init_source)
        self.assertNotIn("_metadata_load_start_scheduled = False", init_source)

    def test_runtime_finished_handlers_leave_worker_deletion_to_shared_runtime(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        finish_sources = "\n".join(
            (
                inspect.getsource(runtime_service.UserPresetsRuntimeService._on_single_metadata_worker_finished),
                inspect.getsource(runtime_service.UserPresetsRuntimeService._on_metadata_worker_finished),
                inspect.getsource(runtime_service.UserPresetsRuntimeService._on_rows_plan_worker_finished),
            )
        )

        self.assertNotIn("worker.deleteLater()", finish_sources)

    def test_runtime_finished_handlers_use_shared_finish_guards(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        single_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._on_single_metadata_worker_finished)
        metadata_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._on_metadata_worker_finished)
        rows_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._on_rows_plan_worker_finished)
        dir_diff_source = inspect.getsource(
            runtime_service.UserPresetsRuntimeService._on_user_dir_diff_worker_finished
        )

        self.assertIn("schedule_next_after_finish", single_source)
        for source in (metadata_source, rows_source, dir_diff_source):
            self.assertIn("schedule_pending_after_finish", source)
        for source in (single_source, metadata_source, rows_source, dir_diff_source):
            self.assertNotIn("if self._", source)

    def test_runtime_refresh_requests_rows_plan_worker_instead_of_building_rows_in_gui(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeService

        refresh_source = inspect.getsource(UserPresetsRuntimeService.refresh_presets_view_from_cache)
        loaded_source = inspect.getsource(UserPresetsRuntimeService._on_metadata_loaded)
        request_source = inspect.getsource(UserPresetsRuntimeService._request_rows_plan_refresh)

        self.assertIn("_request_rows_plan_refresh", refresh_source)
        self.assertIn("_request_rows_plan_refresh", loaded_source)
        self.assertNotIn("adapter.rebuild_rows(", refresh_source)
        self.assertNotIn("adapter.rebuild_rows(", loaded_source)
        self.assertNotIn("adapter.rebuild_rows(", request_source)

    def test_rows_plan_worker_builds_plan_before_gui_applies_rows(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        self.assertTrue(hasattr(runtime_service, "UserPresetsRowsPlanWorker"))
        worker_source = inspect.getsource(runtime_service.UserPresetsRowsPlanWorker.run)
        loaded_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._on_rows_plan_loaded)
        apply_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._run_scheduled_rows_plan_apply)

        self.assertIn("_build_rows_plan", worker_source)
        self.assertIn("_schedule_rows_plan_apply", loaded_source)
        self.assertIn("adapter.apply_rows_plan", apply_source)
        self.assertNotIn("adapter.apply_rows_plan", loaded_source)
        self.assertNotIn("build_preset_rows_plan", loaded_source)
        self.assertNotIn("build_preset_rows_plan", apply_source)

    def test_rows_plan_worker_and_gui_apply_have_visible_timing_logs(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        module_source = inspect.getsource(runtime_service)
        worker_source = inspect.getsource(runtime_service.UserPresetsRowsPlanWorker.run)
        apply_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._run_scheduled_rows_plan_apply)

        self.assertIn("log_ui_timing_since", module_source)
        self.assertIn("user_presets.rows_plan.build", worker_source)
        self.assertIn("user_presets.rows_plan.apply", apply_source)
        self.assertIn("_log_user_presets_timing", worker_source)
        self.assertIn("_log_user_presets_timing", apply_source)

    def test_rows_plan_worker_resolves_active_preset_inside_worker(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        worker_init_source = inspect.getsource(runtime_service.UserPresetsRowsPlanWorker.__init__)
        worker_run_source = inspect.getsource(runtime_service.UserPresetsRowsPlanWorker.run)
        request_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._request_rows_plan_refresh)

        self.assertIn("selected_source_file_name", worker_init_source)
        self.assertIn("self._selected_source_file_name()", worker_run_source)
        self.assertIn("selected_source_file_name=adapter.selected_source_file_name", request_source)
        self.assertNotIn("active_file_name=adapter.selected_source_file_name()", request_source)

    def test_single_metadata_update_uses_model_active_marker_without_settings_read(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        source = inspect.getsource(runtime_service.UserPresetsRuntimeService.try_apply_single_preset_metadata_update)

        self.assertIn("active_preset_file_name", source)
        self.assertNotIn("adapter.selected_source_file_name()", source)

    def test_watcher_has_no_per_file_watch_sync_machinery(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        service_cls = runtime_service.UserPresetsRuntimeService
        self.assertFalse(hasattr(runtime_service, "UserPresetsWatcherSyncPlanWorker"))
        self.assertFalse(hasattr(service_cls, "sync_watched_preset_files"))
        self.assertFalse(hasattr(service_cls, "_schedule_watched_preset_files_sync"))
        self.assertFalse(hasattr(service_cls, "on_preset_file_changed"))
        start_source = inspect.getsource(service_cls._start_fallback_watcher)
        self.assertNotIn("fileChanged", start_source)

    def test_native_watcher_is_preferred_with_qfsw_fallback(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        start_source = inspect.getsource(runtime_service.UserPresetsRuntimeService.start_watching_presets)

        self.assertIn("_start_native_watcher", start_source)
        self.assertIn("_start_fallback_watcher", start_source)

    def test_dir_diff_scans_directory_in_worker_not_gui_thread(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        request_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._request_user_dir_diff)
        worker_source = inspect.getsource(runtime_service.UserPresetsDirDiffWorker.run)

        self.assertIn("UserPresetsDirDiffWorker", request_source)
        self.assertIn("start_qthread_worker", request_source)
        self.assertNotIn("os.scandir", request_source)
        self.assertIn("os.scandir", worker_source)

    def test_dir_diff_uses_shared_worker_state_helpers(self) -> None:
        import presets.user_presets_runtime_service as runtime_service
        from ui.latest_value_worker_state import LatestValueWorkerState

        service = runtime_service.UserPresetsRuntimeService()
        init_source = inspect.getsource(runtime_service.UserPresetsRuntimeService.__init__)
        request_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._request_user_dir_diff)
        finished_source = inspect.getsource(
            runtime_service.UserPresetsRuntimeService._on_user_dir_diff_worker_finished
        )
        cleanup_source = inspect.getsource(runtime_service.UserPresetsRuntimeService._stop_metadata_workers)

        self.assertIsInstance(service._dir_diff_state_obj(), LatestValueWorkerState)
        self.assertIn("_dir_diff_state = LatestValueWorkerState", init_source)
        self.assertIn("_dir_diff_state_obj()", request_source)
        self.assertIn("_dir_diff_state_obj()", finished_source)
        self.assertIn("_dir_diff_state_obj().reset()", cleanup_source)

    def test_watcher_start_does_not_create_preset_dirs_on_gui_thread(self) -> None:
        import presets.commands as commands
        import presets.user_presets_runtime_service as runtime_service
        from app.feature_facades.presets import PresetsFeature

        watcher_source = inspect.getsource(runtime_service.UserPresetsRuntimeService.start_watching_presets)
        path_source = inspect.getsource(commands.get_user_presets_dir)
        metadata_source = inspect.getsource(PresetsFeature._preset_list_metadata_entries)

        self.assertNotIn(".mkdir(", watcher_source)
        self.assertNotIn("ensure_directories()", path_source)
        self.assertIn("ensure_directories()", metadata_source)

    def test_preset_list_metadata_uses_fast_directory_enumeration(self) -> None:
        from app.feature_facades.presets import PresetsFeature

        metadata_source = inspect.getsource(PresetsFeature._preset_list_metadata_entries)

        self.assertIn("os.scandir", metadata_source)
        self.assertNotIn(".glob(", metadata_source)

    def test_single_metadata_refresh_uses_fast_feature_reader(self) -> None:
        from presets.ui.common.user_presets_page_runtime import (
            UserPresetsPageRuntime,
            UserPresetsPageRuntimeConfig,
            UserPresetsRuntimeActions,
        )

        actions = UserPresetsRuntimeActions(
            get_selected_source_preset_file_name=lambda _method: "",
            list_preset_manifests=lambda _method: (_ for _ in ()).throw(
                AssertionError("single metadata refresh must not list all manifests")
            ),
            get_user_presets_dir=lambda _method: "",
            get_cached_preset_list_metadata=lambda _method: None,
            warm_preset_list_metadata_cache=lambda _method: {},
            get_preset_source_path_by_file_name=lambda _method, _file_name: (_ for _ in ()).throw(
                AssertionError("single metadata refresh must not resolve source path through manifests")
            ),
            read_single_preset_list_metadata=lambda _method, file_name: (
                str(file_name or ""),
                {
                    "display_name": "One",
                    "kind": "user",
                    "is_builtin": False,
                    "can_reset_to_builtin": False,
                },
            ),
        )
        runtime = UserPresetsPageRuntime(
            UserPresetsPageRuntimeConfig(
                launch_method="zapret2_mode",
                folder_scope="winws2",
                empty_not_found_key="empty.not_found",
                empty_none_key="empty.none",
                list_log_prefix="TestUserPresets",
                activate_error_level="ERROR",
                activate_error_mode="log",
                preset_runtime_actions=actions,
            )
        )

        result = runtime.build_page_api().listing.read_single_preset_list_metadata_light("One.txt")

        self.assertEqual(result[0], "One.txt")
        self.assertEqual(result[1]["display_name"], "One")

    def test_runtime_service_does_not_keep_legacy_active_marker_settings_read_api(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        self.assertFalse(hasattr(runtime_service.UserPresetsRuntimeService, "apply_active_preset_marker"))

    def test_native_watch_event_handler_does_not_stat_changed_preset_on_gui_thread(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        source = inspect.getsource(runtime_service.UserPresetsRuntimeService._on_native_watch_events)

        self.assertNotIn(".exists()", source)
        self.assertNotIn(".stat()", source)
        self.assertNotIn("os.scandir", source)

    def test_user_presets_page_has_no_legacy_gui_rows_rebuild_entrypoint(self) -> None:
        from presets.ui.common.user_presets_page import UserPresetsPageBase
        import presets.ui.common.user_presets_page as page_module

        self.assertFalse(hasattr(UserPresetsPageBase, "_rebuild_presets_rows"))
        self.assertFalse(hasattr(page_module, "rebuild_presets_rows"))

    def test_user_presets_runtime_keeps_only_worker_plan_apply_path(self) -> None:
        import presets.ui.common.user_presets_page_runtime as runtime_module

        self.assertTrue(hasattr(runtime_module, "apply_presets_rows_plan"))
        self.assertFalse(hasattr(runtime_module, "rebuild_presets_rows"))

    def test_user_presets_listing_api_has_no_legacy_active_preset_name_reader(self) -> None:
        import presets.ui.common.user_presets_page_runtime as runtime_module

        self.assertFalse(hasattr(runtime_module.UserPresetsPageRuntime, "get_active_preset_name_light"))
        self.assertNotIn(
            "get_active_preset_name_light",
            inspect.getsource(runtime_module.UserPresetsListingApi),
        )

    def test_user_presets_page_has_no_legacy_selected_source_reader(self) -> None:
        from presets.ui.common.user_presets_page import UserPresetsPageBase

        self.assertFalse(hasattr(UserPresetsPageBase, "_get_selected_source_preset_file_name_light"))


if __name__ == "__main__":
    unittest.main()
