from __future__ import annotations

import inspect
import importlib
import importlib.util
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from profile import commands as profile_commands
import profile.additional_settings_loader as profile_additional_settings_loader
import profile.profile_setup_loader as profile_setup_loader
from profile.profile_list_loader import ProfileListLoadWorker
from profile.service import ProfilePresetService
from profile.ui.profile_list_model import ProfileListModel as ProfileSetupListModel
from profile.ui.profiles_list import ProfilesList
from profile.ui.profile_setup_page import ProfileSetupPageBase
from profile.ui.preset_setup_page import PresetSetupPageBase
from profile.ui.profile_payload_controller import ProfilePayloadController
from profile.ui.preset_write_queue import PresetWriteQueue
from profile.ui.profile_folder_controller import ProfileFolderController
from presets import display_state
from presets import commands as preset_commands
from presets.ui.common.preset_subpage_base import PresetRawEditorPage
from presets.ui.common.user_presets_page import UserPresetsPageBase
from presets.raw_preset_loader import RawPresetActionWorker, RawPresetActivateWorker, RawPresetLoadWorker, RawPresetSaveWorker
from presets.user_presets_action_workers import UserPresetActivateWorker, UserPresetItemActionWorker
from presets.user_presets_page_plans import build_preset_rows_plan
from ui.presets_menu.model import PresetListModel
import presets.user_presets_action_workers as user_presets_action_workers
import presets.ui.common.user_presets_page_runtime as user_presets_page_runtime
import app.feature_facades.presets as presets_feature_facade
import presets.ui.control.additional_settings_runtime as control_additional_settings_runtime
import presets.ui.control.control_page_shared as control_page_shared
import presets.ui.control.windows_features.runtime as windows_features_runtime
import program_settings.runtime as program_settings_runtime
import program_settings.workers as program_settings_workers
import presets.ui.common.preset_folder_menu as preset_folder_menu
import presets.ui.common.preset_rating_menu as preset_rating_menu
import profile.ui.profile_folder_menu as profile_folder_menu
import presets.ui.control.zapret2.page_runtime as zapret2_page_runtime
from presets.ui.control.zapret2.page import Zapret2ModeControlPage
from presets.user_presets_runtime_service import (
    UserPresetsMetadataLoadWorker,
    UserPresetsRuntimeService,
)
from hosts.ui.page import HostsPage
import hosts.commands as hosts_commands
import log.commands as log_commands
from log.ui.page import LogsPage
import blockcheck.page_runtime as blockcheck_page_runtime
import blockcheck.page_run_workflow as blockcheck_page_run_workflow
import blockcheck.worker as blockcheck_worker
from blockcheck.ui.page import BlockcheckPage
from blockcheck.ui.strategy_scan_page import StrategyScanPage
import blockcheck.ui.helpers as blockcheck_ui_helpers
from app.feature_facades.blockcheck import BlockcheckFeature
from updater.ui.page import ServersPage
from ui.pages.about_page import AboutPage
from ui.pages.base_page import BasePage
from ui.pages.support_page import SupportPage
import settings.appearance as appearance_settings
import settings.appearance_workers as appearance_workers
import dns.ui.page as dns_page
import dns.ui.dns_check_page as dns_check_page
import dns.commands as dns_commands
import dns.dns_check_plans as dns_check_page_plans
import dns.dns_check_worker as dns_check_worker
from dns.page_workers import DnsPageLoadWorker
import telegram_proxy.ui.diagnostics_workflow as telegram_diag_workflow
import telegram_proxy.ui.proxy_runtime_workflow as telegram_runtime_workflow
import telegram_proxy.ui.page as telegram_page
import telegram_proxy.runtime.commands as telegram_proxy_commands
import telegram_proxy.config.settings as telegram_proxy_settings
import telegram_proxy.ui.settings_build as telegram_proxy_settings_build
from app.feature_facades.telegram_proxy import TelegramProxyFeature
import telegram_proxy.ui.upstream_workflow as telegram_upstream_workflow
import telegram_proxy.runtime.workers as telegram_proxy_workers
from telegram_proxy.ui.page import TelegramProxyPage
from telegram_proxy.ui.worker_state import TelegramProxyPageQueuedWorkerState
from telegram_proxy.runtime.workers import TelegramProxyDiagnosticsWorker
import ui.navigation.text_sync as navigation_text_sync
import ui.theme as ui_theme
import ui.window_appearance_bindings as window_appearance_bindings
import ui.window_appearance_state as window_appearance_state
import ui.smooth_scroll as smooth_scroll
import ui.animation_policy as animation_policy
import main.entry as main_entry
from app.feature_facades.profile import ProfileFeature
from app.page_names import PageName
from ui.widgets.win11_controls import Win11RadioOption
from ui.page_host import WindowPageHost


class PresetProfileAsyncArchitectureTests(unittest.TestCase):
    def test_preset_setup_page_loads_profiles_through_worker(self) -> None:
        refresh_source = inspect.getsource(PresetSetupPageBase.refresh_from_preset_switch)
        activated_source = inspect.getsource(PresetSetupPageBase.on_page_activated)
        init_source = inspect.getsource(PresetSetupPageBase.__init__)
        request_source = inspect.getsource(ProfilePayloadController._request_profiles_payload)
        run_source = inspect.getsource(ProfilePayloadController._run_scheduled_profiles_payload_request)
        finished_source = inspect.getsource(ProfilePayloadController._on_profile_worker_finished)
        cleanup_source = inspect.getsource(PresetSetupPageBase.cleanup)

        self.assertNotIn(".list_profiles(", refresh_source)
        self.assertIn("_schedule_profiles_payload_request(force=True)", refresh_source)
        self.assertNotIn("_request_profiles_payload(force=True)", refresh_source)
        self.assertIn("_schedule_profiles_payload_request", activated_source)
        self.assertNotIn("QTimer.singleShot(0, self._request_profiles_payload)", init_source)
        self.assertIn("_run_scheduled_profiles_payload_request", inspect.getsource(ProfilePayloadController._schedule_profiles_payload_request))
        self.assertIn("_request_profiles_payload", run_source)
        self.assertIn("_profile_payload_dirty", request_source)
        self.assertIn("_profile_payload_loaded_once", request_source)
        self.assertIn("_profile_load_runtime_request_id", request_source)
        self.assertNotIn("_profile_load_runtime_worker", init_source)
        self.assertNotIn("_profile_load_runtime_worker", request_source)
        self.assertNotIn("_profile_load_runtime_worker", finished_source)
        self.assertNotIn("_profile_load_runtime_worker", cleanup_source)

    def test_preset_setup_clean_activation_skips_payload_request_timer(self) -> None:
        page = PresetSetupPageBase.__new__(PresetSetupPageBase)
        page._profile_payload_loaded_once = True
        page._profile_payload_dirty = False
        page._schedule_profiles_payload_request = Mock(
            side_effect=AssertionError("clean activation must not schedule profile payload request")
        )

        PresetSetupPageBase.on_page_activated(page)

        page._schedule_profiles_payload_request.assert_not_called()

    def test_preset_setup_clean_activation_keeps_ready_list_attached(self) -> None:
        class _List:
            def __init__(self) -> None:
                self.visible_calls: list[bool] = []

            def setVisible(self, value: bool) -> None:  # noqa: N802
                self.visible_calls.append(bool(value))

        page = PresetSetupPageBase.__new__(PresetSetupPageBase)
        profile_list = _List()
        page._profiles_list = profile_list
        page._profile_payload_loaded_once = True
        page._profile_payload_dirty = False
        page._profiles_list_show_scheduled = False
        page._cleanup_in_progress = False
        page._mark_profiles_list_ready_after_page_switch = Mock()
        page._schedule_profiles_payload_request = Mock(
            side_effect=AssertionError("clean activation must not reload profile payload")
        )

        PresetSetupPageBase.on_page_hidden(page)
        PresetSetupPageBase.on_page_activated(page)

        self.assertEqual(profile_list.visible_calls, [])
        page._schedule_profiles_payload_request.assert_not_called()
        page._mark_profiles_list_ready_after_page_switch.assert_called_once_with()

    def test_preset_setup_page_refreshes_after_active_preset_content_change_signal(self) -> None:
        init_source = inspect.getsource(PresetSetupPageBase.__init__)
        bind_source = inspect.getsource(PresetSetupPageBase.bind_ui_state_store)
        handler_source = inspect.getsource(PresetSetupPageBase._on_ui_state_changed)
        cleanup_source = inspect.getsource(PresetSetupPageBase.cleanup)

        self.assertIn("ui_state_store", init_source)
        self.assertIn("bind_ui_state_store", init_source)
        self.assertIn("preset_content_revision", bind_source)
        self.assertIn("active_preset_revision", bind_source)
        self.assertIn("preset_content_change_kind", handler_source)
        self.assertIn('"strategy_only"', handler_source)
        self.assertIn("_profile_payload_dirty = True", handler_source)
        self.assertIn("_schedule_profiles_payload_request(force=True)", handler_source)
        self.assertNotIn("_request_profiles_payload(force=True)", handler_source)
        self.assertIn("_ui_state_unsubscribe", cleanup_source)

    def test_preset_setup_page_ignores_stale_profile_worker_after_preset_switch(self) -> None:
        request_source = inspect.getsource(ProfilePayloadController._request_profiles_payload)
        finished_source = inspect.getsource(ProfilePayloadController._on_profile_worker_finished)
        scheduled_source = inspect.getsource(ProfilePayloadController._run_scheduled_profile_load_refresh_start)

        self.assertIn("_profile_load_refresh_state_obj()", request_source)
        self.assertIn("runtime.is_running() or refresh_state.start_scheduled", request_source)
        self.assertIn("if force:", request_source)
        self.assertIn("refresh_state.pending = True", request_source)
        self.assertIn("_profile_load_request_id += 1", request_source)
        self.assertIn("_profile_payload_dirty = True", request_source)
        self.assertIn("schedule_pending_after_finish", finished_source)
        self.assertIn("_accept_current_profile_load_worker_finished", finished_source)
        self.assertIn("_schedule_profiles_payload_request(force=True)", scheduled_source)

    def test_profile_setup_pending_load_restarts_use_shared_finish_guard(self) -> None:
        finish_sources = (
            inspect.getsource(ProfileSetupPageBase._on_profile_setup_worker_finished),
            inspect.getsource(ProfileSetupPageBase._on_list_file_worker_finished),
            inspect.getsource(ProfileSetupPageBase._on_list_file_validation_worker_finished),
        )

        for source in finish_sources:
            self.assertIn("schedule_pending_after_finish", source)
            self.assertIn("is_current_worker_finish", source)
            self.assertNotIn("if self._", source)

    def test_profile_folder_worker_returns_folder_state_after_write_action(self) -> None:
        worker_source = inspect.getsource(profile_setup_loader.ProfileFolderActionWorker.run)

        self.assertIn('context["folder_state"]', worker_source)
        self.assertIn('self._action != "load_state"', worker_source)

    def test_profile_folder_action_updates_visible_list_without_reload(self) -> None:
        page = PresetSetupPageBase.__new__(PresetSetupPageBase)
        page._profile_folder_action_request_id = 7
        page._profile_folder_action_refresh_by_request = {7: True}
        page._profiles_list = Mock()
        page._profiles_list.apply_profile_folder_state.return_value = True
        page._profile_payload_dirty = False
        page.refresh_from_preset_switch = Mock(
            side_effect=AssertionError("folder action must not reload the whole profile list")
        )

        page._folder_controller_obj()._on_profile_folder_action_finished(
            7,
            "rename",
            True,
            {"folder_state": {"folders": {}, "items": {}}},
        )

        page._profiles_list.apply_profile_folder_state.assert_called_once_with({"folders": {}, "items": {}})
        page.refresh_from_preset_switch.assert_not_called()
        self.assertTrue(page._profile_payload_dirty)

    def test_profile_folder_action_result_ignored_when_new_action_is_pending(self) -> None:
        page = PresetSetupPageBase.__new__(PresetSetupPageBase)
        page._profile_folder_action_request_id = 8
        page._profile_folder_action_refresh_by_request = {8: True}
        page._profile_folder_action_pending = [
            {
                "action": "rename",
                "folder_key": "games",
                "name": "Games",
                "direction": 0,
                "collapsed": False,
                "refresh": True,
                "context_extra": {},
            }
        ]
        page._profiles_list = Mock()
        page._profiles_list.apply_profile_folder_state.return_value = True
        page._show_folder_menu_with_state = Mock()
        page.refresh_from_preset_switch = Mock()
        page._profile_payload_dirty = False

        page._folder_controller_obj()._on_profile_folder_action_finished(
            8,
            "rename",
            True,
            {"folder_state": {"folders": {}, "items": {}}},
        )

        page._profiles_list.apply_profile_folder_state.assert_not_called()
        page._show_folder_menu_with_state.assert_not_called()
        page.refresh_from_preset_switch.assert_not_called()
        self.assertFalse(page._profile_payload_dirty)
        self.assertNotIn(8, page._profile_folder_action_refresh_by_request)

    def test_profile_folder_action_error_ignored_when_new_action_is_pending(self) -> None:
        page = PresetSetupPageBase.__new__(PresetSetupPageBase)
        page._profile_folder_action_request_id = 9
        page._profile_folder_action_refresh_by_request = {9: True}
        page._profile_folder_action_pending = [
            {
                "action": "set_collapsed",
                "folder_key": "video",
                "name": "",
                "direction": 0,
                "collapsed": True,
                "refresh": False,
                "context_extra": {},
            }
        ]

        with patch("profile.ui.preset_setup_page.log") as log_mock:
            PresetSetupPageBase._on_profile_folder_action_failed(page, 9, "rename", "old error", {})

        log_mock.assert_not_called()
        self.assertNotIn(9, page._profile_folder_action_refresh_by_request)

    def test_profile_model_applies_folder_state_without_loading_profiles_again(self) -> None:
        model = ProfileSetupListModel()
        model.set_profiles((
            SimpleNamespace(
                key="profile-1",
                persistent_key="persistent-1",
                profile_index=0,
                profile_name="Discord",
                enabled=True,
                in_preset=True,
                strategy_id="none",
                strategy_name="Стратегия не выбрана",
                match_lines=("--filter-tcp=443",),
                list_type="hostlist",
                rating="",
                favorite=False,
                group="common",
                group_name="Общие",
                order=0,
                order_is_manual=False,
                group_collapsed=False,
                user_profile_id="",
            ),
        ))
        model.beginResetModel = Mock(side_effect=AssertionError("folder rename must not reload profiles"))

        self.assertTrue(model.apply_folder_state({
            "folders": {
                "common": {"name": "Новая папка", "order": 0, "collapsed": False},
            },
            "items": {
                "persistent-1": {"folder_key": "common", "order": 0},
            },
        }))

        self.assertEqual(model.index(0, 0).data(ProfileSetupListModel.GroupNameRole), "Новая папка")

    def test_raw_preset_editor_saves_without_runtime_publish_until_editor_is_left(self) -> None:
        from presets.ui.common.raw_preset_text_editor import RawPresetTextEditor

        save_source = inspect.getsource(PresetRawEditorPage._save_file)
        text_changed_source = inspect.getsource(RawPresetTextEditor.on_text_changed)
        commit_source = inspect.getsource(RawPresetTextEditor.commit_pending_content_change)
        event_source = inspect.getsource(RawPresetTextEditor.handle_event)
        controller_source = inspect.getsource(PresetRawEditorPage.__init__) + inspect.getsource(
            RawPresetTextEditor.__init__
        )

        self.assertIn("publish_content_changed: bool = False", save_source)
        self.assertIn("publish_content_changed", save_source)
        self.assertIn("content_publish_pending", text_changed_source)
        self.assertIn("publish_content_changed=True", commit_source)
        self.assertIn("QEvent.Type.FocusOut", event_source)
        self.assertIn("QEvent.Type.Leave", event_source)
        self.assertIn("QEvent.Type.MouseButtonPress", event_source)
        self.assertIn("installEventFilter", controller_source)

    def test_raw_preset_editor_has_inline_text_search(self) -> None:
        from presets.ui.common.raw_preset_text_editor import RawPresetTextEditor

        build_source = inspect.getsource(PresetRawEditorPage._build_ui)
        editor_init_source = inspect.getsource(RawPresetTextEditor.__init__)
        search_source = inspect.getsource(RawPresetTextEditor.search_text)
        find_source = inspect.getsource(RawPresetTextEditor.find_next)

        self.assertTrue(hasattr(RawPresetTextEditor, "search_text"))
        self.assertTrue(hasattr(RawPresetTextEditor, "find_next"))
        # Поиск живёт в общем ui.code_editor: панель Find/Replace плюс
        # контроллер, владеющий состоянием совпадений.
        self.assertIn("FindReplaceBar(parent)", editor_init_source)
        self.assertIn("FindController(self.editor, self.find_bar", editor_init_source)
        self.assertIn("self.search_input = self.find_bar.search_input", editor_init_source)
        self.assertIn("actions_layout.addStretch(1)", build_source)
        self.assertIn("self.add_widget(self.findBar)", build_source)
        self.assertIn("self.find_controller.search_text(query)", search_source)
        self.assertIn("self.find_controller.find_next(reverse=", find_source)

    def test_refresh_after_switch_uses_profile_snapshot_not_full_list(self) -> None:
        source = inspect.getsource(display_state.resolve_profile_strategy_display_state)

        self.assertNotIn(".list_profiles(", source)
        self.assertIn("get_profile_strategy_display_state", source)

    def test_preset_switch_summary_refresh_runs_through_worker_runtime(self) -> None:
        import ui.window_bootstrap_runtime as bootstrap_runtime

        source = inspect.getsource(bootstrap_runtime.create_preset_runtime_coordinator)

        self.assertIn("PresetProfileStrategySummaryRefreshRuntime", source)
        self.assertIn("summary_refresh_runtime.request_refresh", source)
        self.assertNotIn(
            "refresh_after_switch=lambda: runtime_deps.presets_feature.refresh_profile_strategy_summary_in_store",
            source,
        )

    def test_preset_switch_summary_worker_does_not_touch_ui_state_store(self) -> None:
        import presets.display_state_refresh as display_state_refresh

        worker_source = inspect.getsource(display_state_refresh.PresetProfileStrategySummaryWorker.run)
        runtime_source = inspect.getsource(
            display_state_refresh.PresetProfileStrategySummaryRefreshRuntime._on_summary_loaded,
        )
        publish_source = inspect.getsource(display_state.publish_profile_strategy_summary_in_store)

        self.assertIn("resolve_profile_strategy_display_state", worker_source)
        self.assertNotIn("ui_state_store", worker_source)
        self.assertIn("publish_profile_strategy_summary_in_store", runtime_source)
        self.assertIn("set_current_strategy_summary", publish_source)

    def test_user_presets_full_metadata_loading_is_worker_only(self) -> None:
        load_source = inspect.getsource(UserPresetsRuntimeService.load_presets)
        watcher_source = inspect.getsource(UserPresetsRuntimeService.reload_presets_from_watcher)

        self.assertNotIn("adapter.load_all_metadata()", load_source)
        self.assertNotIn("adapter.load_all_metadata()", watcher_source)
        self.assertIn("UserPresetsMetadataLoadWorker", load_source)

    def test_user_presets_single_metadata_refresh_is_worker_only(self) -> None:
        import presets.user_presets_runtime_service as runtime_service

        self.assertTrue(hasattr(runtime_service, "UserPresetsSingleMetadataWorker"))
        changed_source = inspect.getsource(UserPresetsRuntimeService.on_store_content_changed)
        request_source = inspect.getsource(UserPresetsRuntimeService._request_single_metadata_refresh)
        start_source = inspect.getsource(UserPresetsRuntimeService._start_single_metadata_refresh_worker)
        loaded_source = inspect.getsource(UserPresetsRuntimeService._on_single_metadata_loaded)
        worker_source = inspect.getsource(runtime_service.UserPresetsSingleMetadataWorker.run)

        self.assertNotIn("adapter.read_single_metadata(file_name)", changed_source)
        self.assertIn("_request_single_metadata_refresh", changed_source)
        self.assertIn("_single_metadata_state_obj", request_source)
        self.assertIn("_start_single_metadata_refresh_worker", request_source)
        self.assertIn("UserPresetsSingleMetadataWorker", start_source)
        self.assertIn("_read_single_metadata", worker_source)
        self.assertIn("try_apply_single_preset_metadata_update", loaded_source)

    def test_user_presets_folder_state_for_rows_is_worker_loaded(self) -> None:
        worker_source = inspect.getsource(UserPresetsMetadataLoadWorker.run)
        load_source = inspect.getsource(UserPresetsRuntimeService.load_presets)
        loaded_source = inspect.getsource(UserPresetsRuntimeService._on_metadata_loaded)
        cache_refresh_source = inspect.getsource(UserPresetsRuntimeService.refresh_presets_view_from_cache)
        request_rows_source = inspect.getsource(UserPresetsRuntimeService._request_rows_plan_refresh)
        plan_source = inspect.getsource(build_preset_rows_plan)

        self.assertIn("_load_folder_state", worker_source)
        self.assertIn("folder_state", load_source)
        self.assertIn("_cached_folder_state", loaded_source)
        self.assertIn("_cached_folder_state", cache_refresh_source)
        self.assertIn("folder_state=folder_state", request_rows_source)
        fallback_branch = plan_source.split("effective_folder_state", 1)[1]
        self.assertNotIn("load_preset_folder_state", fallback_branch)

    def test_user_presets_rows_plan_apply_is_deferred_after_worker_signal(self) -> None:
        service = UserPresetsRuntimeService.__new__(UserPresetsRuntimeService)
        service._rows_plan_request_id = 3
        page = SimpleNamespace()
        adapter = SimpleNamespace(apply_rows_plan=Mock())
        service._resolve_page = Mock(return_value=page)
        service._resolve_adapter = Mock(return_value=adapter)

        with patch("presets.user_presets_runtime_service.QTimer.singleShot") as single_shot:
            UserPresetsRuntimeService._on_rows_plan_loaded(service, 3, "plan", 12.5, page)

        adapter.apply_rows_plan.assert_not_called()
        single_shot.assert_called_once()

        UserPresetsRuntimeService._run_scheduled_rows_plan_apply(service)

        adapter.apply_rows_plan.assert_called_once_with("plan", 12.5)

    def test_user_presets_active_marker_uses_model_signals_without_full_viewport_update(self) -> None:
        source = inspect.getsource(UserPresetsRuntimeService.apply_active_preset_marker_for_file)

        self.assertIn("set_active_preset", source)
        self.assertIn("schedule_current_preset_index", source)
        self.assertNotIn("viewport().update()", source)
        self.assertNotIn("viewport().repaint()", source)

    def test_user_presets_single_metadata_update_uses_model_signals_without_full_viewport_update(self) -> None:
        source = inspect.getsource(UserPresetsRuntimeService.try_apply_single_preset_metadata_update)

        self.assertIn("update_preset_row", source)
        self.assertNotIn("viewport().update()", source)
        self.assertNotIn("viewport().repaint()", source)

    def test_user_presets_switched_signal_uses_delivered_file_name(self) -> None:
        source = inspect.getsource(UserPresetsRuntimeService.on_store_switched)

        self.assertIn("apply_active_preset_marker_for_file", source)
        self.assertNotIn("apply_active_preset_marker(page)", source)

    def test_user_presets_page_uses_warmed_smooth_scroll_preference(self) -> None:
        source = inspect.getsource(UserPresetsPageBase._build_ui)

        self.assertIn("get_page_smooth_scroll_enabled", source)
        self.assertNotIn("load_smooth_scroll_enabled", source)

    def test_user_presets_page_uses_narrow_preset_dependencies(self) -> None:
        after_ui_source = inspect.getsource(UserPresetsPageBase._after_ui_built)
        open_folder_source = inspect.getsource(UserPresetsPageBase._open_presets_folder)
        page_source = inspect.getsource(UserPresetsPageBase)

        self.assertIn("self._connect_preset_signals", after_ui_source)
        self.assertIn("_request_preset_open_folder_action", open_folder_source)
        self.assertNotIn("open_presets_folder_action", open_folder_source)
        self.assertNotIn("open_user_presets_folder", open_folder_source)
        self.assertIn("create_preset_open_folder_worker", page_source)
        self.assertIn("_preset_open_folder_worker", page_source)
        self.assertNotIn("self._presets_feature", page_source)
        self.assertNotIn("self._presets.", after_ui_source)
        self.assertNotIn("self._presets.", open_folder_source)

        self.assertTrue(hasattr(user_presets_action_workers, "UserPresetOpenFolderWorker"))
        create_worker_source = inspect.getsource(UserPresetsPageBase.create_preset_open_folder_worker)
        worker_source = inspect.getsource(user_presets_action_workers.UserPresetOpenFolderWorker.run)
        worker_init_source = inspect.getsource(user_presets_action_workers.UserPresetOpenFolderWorker.__init__)
        feature_source = inspect.getsource(presets_feature_facade.PresetsFeature.create_user_presets_open_folder_worker)
        self.assertIn("_create_user_presets_open_folder_worker", create_worker_source)
        self.assertNotIn("UserPresetOpenFolderWorker(", create_worker_source)
        self.assertNotIn("_presets_feature", worker_init_source)
        self.assertIn("open_folder", worker_init_source)
        self.assertIn("self._open_folder", worker_init_source)
        self.assertIn("self._open_folder()", worker_source)
        self.assertNotIn("preset_commands.open_user_presets_folder", worker_source)
        self.assertNotIn("_preset_services", worker_init_source)
        self.assertIn("open_user_presets_folder", feature_source)

    def test_preset_list_active_marker_updates_indexed_rows_only(self) -> None:
        class CountingRow(dict):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                self.get_count = 0

            def get(self, key, default=None):
                self.get_count += 1
                return super().get(key, default)

        rows = [
            CountingRow(
                {
                    "kind": "preset",
                    "file_name": f"preset-{index}.txt",
                    "is_active": index == 3,
                }
            )
            for index in range(100)
        ]
        model = PresetListModel()
        model.set_rows(rows)
        for row in rows:
            row.get_count = 0

        self.assertTrue(model.set_active_preset("preset-70.txt"))

        touched_rows = [row for row in rows if row.get_count]
        self.assertLessEqual(len(touched_rows), 2)
        self.assertFalse(rows[3]["is_active"])
        self.assertTrue(rows[70]["is_active"])

    def test_user_presets_current_index_uses_model_row_index(self) -> None:
        source = inspect.getsource(UserPresetsRuntimeService.set_current_preset_index)

        self.assertIn("find_preset_row", source)
        self.assertNotIn("for row in range", source)

    def test_user_presets_ensure_current_index_uses_model_first_preset_row(self) -> None:
        source = inspect.getsource(UserPresetsRuntimeService.ensure_preset_list_current_index)

        self.assertIn("first_preset_row", source)
        self.assertNotIn("for row in range", source)

    def test_user_presets_current_index_skips_already_selected_row(self) -> None:
        class _Index:
            def __init__(self, row: int) -> None:
                self.row = row

            def isValid(self) -> bool:
                return True

            def __eq__(self, other) -> bool:
                return isinstance(other, _Index) and self.row == other.row

        target_index = _Index(4)
        model = Mock()
        model.find_preset_row.return_value = 4
        model.index.return_value = target_index
        presets_list = Mock()
        presets_list.currentIndex.return_value = target_index
        page = SimpleNamespace(_presets_model=model, presets_list=presets_list)
        service = UserPresetsRuntimeService.__new__(UserPresetsRuntimeService)
        service._resolve_page = Mock(return_value=page)

        UserPresetsRuntimeService.set_current_preset_index(service, "Default.txt")

        presets_list.setCurrentIndex.assert_not_called()

    def test_user_presets_restore_view_state_skips_same_scroll_value(self) -> None:
        scrollbar = Mock()
        scrollbar.value.return_value = 42
        presets_list = Mock()
        presets_list.verticalScrollBar.return_value = scrollbar
        page = SimpleNamespace(presets_list=presets_list)
        service = UserPresetsRuntimeService.__new__(UserPresetsRuntimeService)
        service._resolve_page = Mock(return_value=page)

        UserPresetsRuntimeService.restore_presets_view_state(
            service,
            {"current_file_name": "", "scroll_value": 42},
        )

        scrollbar.setValue.assert_not_called()

    def test_user_presets_activation_runs_through_worker(self) -> None:
        handler_source = inspect.getsource(UserPresetsPageBase._on_activate_preset)
        request_source = inspect.getsource(UserPresetsPageBase._request_preset_activation)
        start_source = inspect.getsource(UserPresetsPageBase._start_preset_activation_worker)
        worker_source = inspect.getsource(UserPresetActivateWorker.run)

        self.assertNotIn("activate_preset_action", handler_source)
        self.assertNotIn(".activate_preset(", handler_source)
        self.assertIn("_request_preset_activation", handler_source)
        self.assertIn("apply_active_preset_marker_for_file", request_source + start_source)
        self.assertIn("create_preset_activate_worker", request_source + start_source)
        self.assertIn("self._activate_preset", worker_source)
        self.assertNotIn("actions_api.activate_preset", worker_source)

    def test_user_presets_activation_error_restores_marker_without_list_reload(self) -> None:
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._preset_activate_request_id = 4
        page._pending_preset_activation = None
        page._restore_preset_activation_marker_file_name = "Before.txt"
        page._runtime_service = Mock()
        page._refresh_presets_view_from_cache = Mock(
            side_effect=AssertionError("activation error must not reload the whole preset list")
        )
        page._tr = Mock(side_effect=lambda _key, default, **_kwargs: default)
        page.window = Mock(return_value=None)
        result = SimpleNamespace(
            ok=False,
            log_message="Ошибка активации",
            log_level="ERROR",
            infobar_level="error",
            infobar_title="Ошибка",
            infobar_content="Не удалось",
            activated_file_name=None,
        )

        with patch("presets.ui.common.user_presets_page.InfoBar.error"):
            UserPresetsPageBase._on_preset_activation_finished(page, 4, result)

        page._runtime_service.apply_active_preset_marker.assert_not_called()
        page._runtime_service.apply_active_preset_marker_for_file.assert_called_once_with("Before.txt")

    def test_user_presets_activation_failure_restores_marker_without_list_reload(self) -> None:
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._preset_activate_request_id = 5
        page._pending_preset_activation = None
        page._restore_preset_activation_marker_file_name = "Before.txt"
        page._runtime_service = Mock()
        page._refresh_presets_view_from_cache = Mock(
            side_effect=AssertionError("activation failure must not reload the whole preset list")
        )
        page._tr = Mock(side_effect=lambda _key, default, **_kwargs: default)
        page.window = Mock(return_value=None)

        with patch("presets.ui.common.user_presets_page.InfoBar.error"):
            UserPresetsPageBase._on_preset_activation_failed(page, 5, "bad")

        page._runtime_service.apply_active_preset_marker.assert_not_called()
        page._runtime_service.apply_active_preset_marker_for_file.assert_called_once_with("Before.txt")

    def test_user_presets_pending_activation_uses_shared_write_queue_after_worker_signal(self) -> None:
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._preset_activate_request_id = 5
        page._preset_activate_runtime = SimpleNamespace(is_running=Mock(return_value=False))
        page._preset_item_action_runtime = SimpleNamespace(is_running=Mock(return_value=False))
        page._preset_bulk_action_runtime = SimpleNamespace(is_running=Mock(return_value=False))
        page._preset_edit_action_runtime = SimpleNamespace(is_running=Mock(return_value=False))
        page._preset_storage_action_runtime = SimpleNamespace(is_running=Mock(return_value=False))
        page._preset_folder_action_runtime = SimpleNamespace(is_running=Mock(return_value=False))
        page._preset_folder_action_pending = []
        page._pending_preset_write_actions = []
        page._pending_preset_activation = ("Next.txt", "Next")
        page._cleanup_in_progress = False
        page._start_preset_activation_worker = Mock()
        callbacks = []

        with patch(
            "presets.ui.common.user_presets_page.QTimer.singleShot",
            side_effect=lambda _delay, callback: callbacks.append(callback),
        ):
            UserPresetsPageBase._on_preset_activate_worker_finished(page, SimpleNamespace(_request_id=5))

        page._start_preset_activation_worker.assert_not_called()
        self.assertEqual(len(callbacks), 1)

        callbacks[0]()

        page._start_preset_activation_worker.assert_called_once_with("Next.txt", "Next")

    def test_preset_model_removes_visible_preset_without_full_reset(self) -> None:
        model = PresetListModel()
        model.set_rows([
            {
                "kind": "folder",
                "folder_key": "common",
                "text": "Общие",
                "count": 2,
                "is_collapsed": False,
            },
            {
                "kind": "preset",
                "file_name": "first.txt",
                "name": "First",
                "folder_key": "common",
            },
            {
                "kind": "preset",
                "file_name": "second.txt",
                "name": "Second",
                "folder_key": "common",
            },
        ])
        model.beginResetModel = Mock(side_effect=AssertionError("delete must not reset the whole preset list"))

        self.assertTrue(model.remove_preset("first.txt"))

        self.assertEqual(model.rowCount(), 2)
        self.assertEqual(model.find_preset_row("first.txt"), -1)
        self.assertEqual(model.find_preset_row("second.txt"), 1)
        self.assertEqual(model.index(0, 0).data(PresetListModel.CountRole), 1)

    def test_preset_model_skips_identical_rows_without_full_reset(self) -> None:
        rows = [
            {
                "kind": "folder",
                "folder_key": "common",
                "text": "Общие",
                "count": 1,
                "is_collapsed": False,
            },
            {
                "kind": "preset",
                "file_name": "first.txt",
                "name": "First",
                "folder_key": "common",
            },
        ]
        model = PresetListModel()
        model.set_rows(rows)
        model.beginResetModel = Mock(side_effect=AssertionError("same rows must not reset the preset list"))

        model.set_rows([dict(row) for row in rows])

        self.assertEqual(model.rowCount(), 2)
        self.assertEqual(model.find_preset_row("first.txt"), 1)

    def test_preset_model_reports_whether_set_rows_changed_model(self) -> None:
        rows = [
            {
                "kind": "preset",
                "file_name": "first.txt",
                "name": "First",
                "folder_key": "common",
            },
        ]
        model = PresetListModel()

        self.assertTrue(model.set_rows(rows))
        self.assertFalse(model.set_rows([dict(row) for row in rows]))
        self.assertTrue(model.set_rows([{**rows[0], "name": "First updated"}]))

    def test_preset_model_tracks_first_visible_preset_row(self) -> None:
        model = PresetListModel()
        model.set_rows([
            {
                "kind": "folder",
                "folder_key": "common",
                "text": "Общие",
                "count": 2,
                "is_collapsed": False,
            },
            {
                "kind": "preset",
                "file_name": "first.txt",
                "name": "First",
                "folder_key": "common",
            },
            {
                "kind": "preset",
                "file_name": "second.txt",
                "name": "Second",
                "folder_key": "common",
            },
        ])

        self.assertEqual(model.first_preset_row(), 1)

        model.set_rows([
            {
                "kind": "folder",
                "folder_key": "empty",
                "text": "Нет",
                "count": 0,
                "is_collapsed": False,
            }
        ])

        self.assertEqual(model.first_preset_row(), -1)

    def test_preset_model_updates_stable_rows_without_full_reset(self) -> None:
        model = PresetListModel()
        model.set_rows([
            {
                "kind": "folder",
                "folder_key": "common",
                "text": "Общие",
                "count": 1,
                "is_collapsed": False,
            },
            {
                "kind": "preset",
                "file_name": "first.txt",
                "name": "First",
                "folder_key": "common",
                "description": "old",
                "rating": 1,
            },
        ])
        model.beginResetModel = Mock(side_effect=AssertionError("stable rows must not reset the preset list"))

        model.set_rows([
            {
                "kind": "folder",
                "folder_key": "common",
                "text": "Общие",
                "count": 1,
                "is_collapsed": False,
            },
            {
                "kind": "preset",
                "file_name": "first.txt",
                "name": "First updated",
                "folder_key": "common",
                "description": "new",
                "rating": 5,
            },
        ])

        self.assertEqual(model.rowCount(), 2)
        self.assertEqual(model.find_preset_row("first.txt"), 1)
        self.assertEqual(model.index(1, 0).data(PresetListModel.NameRole), "First updated")
        self.assertEqual(model.index(1, 0).data(PresetListModel.DescriptionRole), "new")
        self.assertEqual(model.index(1, 0).data(PresetListModel.RatingRole), 5)

    def test_preset_model_moves_single_reordered_row_without_full_reset(self) -> None:
        model = PresetListModel()
        model.set_rows([
            {
                "kind": "folder",
                "folder_key": "common",
                "text": "Общие",
                "count": 3,
                "is_collapsed": False,
            },
            {
                "kind": "preset",
                "file_name": "first.txt",
                "name": "First",
                "folder_key": "common",
                "rating": 0,
            },
            {
                "kind": "preset",
                "file_name": "second.txt",
                "name": "Second",
                "folder_key": "common",
                "rating": 0,
            },
            {
                "kind": "preset",
                "file_name": "third.txt",
                "name": "Third",
                "folder_key": "common",
                "rating": 0,
            },
        ])
        model.beginResetModel = Mock(side_effect=AssertionError("single-row reorder must not reset the whole preset list"))

        changed = model.set_rows([
            {
                "kind": "folder",
                "folder_key": "common",
                "text": "Общие",
                "count": 3,
                "is_collapsed": False,
            },
            {
                "kind": "preset",
                "file_name": "second.txt",
                "name": "Second",
                "folder_key": "common",
                "rating": 0,
            },
            {
                "kind": "preset",
                "file_name": "first.txt",
                "name": "First",
                "folder_key": "common",
                "rating": 5,
            },
            {
                "kind": "preset",
                "file_name": "third.txt",
                "name": "Third",
                "folder_key": "common",
                "rating": 0,
            },
        ])

        self.assertTrue(changed)
        self.assertEqual(model.find_preset_row("first.txt"), 2)
        self.assertEqual(model.index(2, 0).data(PresetListModel.FileNameRole), "first.txt")
        self.assertEqual(model.index(2, 0).data(PresetListModel.RatingRole), 5)

    def test_preset_model_single_move_detection_is_not_bruteforce(self) -> None:
        helper_source = inspect.getsource(__import__("ui.presets_menu.model", fromlist=["_single_row_move"])._single_row_move)

        self.assertNotIn("for insert_index in range", helper_source)
        self.assertNotIn("candidate =", helper_source)
        self.assertIn("current_positions", helper_source)

    def test_preset_rows_plan_apply_skips_layout_when_rows_do_not_change(self) -> None:
        from presets.ui.common.user_presets_page_runtime import apply_presets_rows_plan

        runtime_service = Mock()
        runtime_service.capture_presets_view_state.return_value = {}
        presets_model = Mock()
        presets_model.set_rows.return_value = False
        plan = SimpleNamespace(
            rows=[
                {
                    "kind": "preset",
                    "file_name": "first.txt",
                    "name": "First",
                    "folder_key": "common",
                }
            ],
            total_presets=1,
        )
        update_height = Mock(side_effect=AssertionError("unchanged rows must not recalculate list height"))
        schedule_resync = Mock(side_effect=AssertionError("unchanged rows must not resync layout"))
        presets_delegate = Mock()

        apply_presets_rows_plan(
            runtime_service=runtime_service,
            presets_delegate=presets_delegate,
            presets_model=presets_model,
            presets_list=object(),
            schedule_layout_resync_fn=schedule_resync,
            update_presets_view_height_fn=update_height,
            log_fn=Mock(),
            plan=plan,
        )

        presets_delegate.reset_interaction_state.assert_not_called()
        runtime_service.ensure_preset_list_current_index.assert_not_called()
        runtime_service.restore_presets_view_state.assert_not_called()

    def test_preset_rows_plan_apply_skips_layout_when_row_count_is_unchanged(self) -> None:
        from presets.ui.common.user_presets_page_runtime import apply_presets_rows_plan

        runtime_service = Mock()
        runtime_service.capture_presets_view_state.return_value = {}
        presets_model = PresetListModel()
        presets_model.set_rows([
            {
                "kind": "folder",
                "folder_key": "common",
                "text": "Общие",
                "count": 2,
                "is_collapsed": False,
            },
            {
                "kind": "preset",
                "file_name": "first.txt",
                "name": "First",
                "folder_key": "common",
            },
            {
                "kind": "preset",
                "file_name": "second.txt",
                "name": "Second",
                "folder_key": "common",
            },
        ])
        plan = SimpleNamespace(
            rows=[
                {
                    "kind": "folder",
                    "folder_key": "common",
                    "text": "Общие",
                    "count": 2,
                    "is_collapsed": False,
                },
                {
                    "kind": "preset",
                    "file_name": "second.txt",
                    "name": "Second",
                    "folder_key": "common",
                },
                {
                    "kind": "preset",
                    "file_name": "first.txt",
                    "name": "First",
                    "folder_key": "common",
                    "rating": 5,
                },
            ],
            total_presets=2,
        )
        update_height = Mock()
        schedule_resync = Mock()

        apply_presets_rows_plan(
            runtime_service=runtime_service,
            presets_delegate=Mock(),
            presets_model=presets_model,
            presets_list=object(),
            schedule_layout_resync_fn=schedule_resync,
            update_presets_view_height_fn=update_height,
            log_fn=Mock(),
            plan=plan,
        )

        update_height.assert_not_called()
        schedule_resync.assert_not_called()
        runtime_service.ensure_preset_list_current_index.assert_called_once_with()

    def test_user_presets_clean_activation_skips_full_layout_resync(self) -> None:
        from presets.ui.common.user_presets_page_lifecycle import activate_user_presets_page

        runtime_service = Mock()
        runtime_service.is_ui_dirty.return_value = False
        start_watching = Mock()
        apply_mode_labels = Mock()
        resync_layout = Mock(side_effect=AssertionError("clean activation must not fully resync layout"))
        refresh_view = Mock(side_effect=AssertionError("clean activation must not reload preset rows"))
        update_height = Mock()
        schedule_resync = Mock(side_effect=AssertionError("clean activation must not schedule delayed layout resync"))

        activate_user_presets_page(
            cleanup_in_progress=False,
            apply_mode_labels_fn=apply_mode_labels,
            resync_layout_metrics_fn=resync_layout,
            start_watching_presets_fn=start_watching,
            runtime_service=runtime_service,
            refresh_presets_view_if_possible_fn=refresh_view,
            update_presets_view_height_fn=update_height,
            schedule_layout_resync_fn=schedule_resync,
        )

        start_watching.assert_called_once_with()
        apply_mode_labels.assert_called_once_with()
        update_height.assert_called_once_with()

    def test_user_presets_delete_updates_visible_row_without_reload(self) -> None:
        result = SimpleNamespace(
            ok=True,
            structure_changed=True,
            log_message="Удалён пресет",
            log_level="INFO",
            infobar_level="",
            infobar_title="",
            infobar_content="",
            error_code="",
        )
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._preset_item_action_request_id = 4
        page._runtime_service = Mock()
        page._runtime_service.remove_deleted_preset_locally.return_value = True
        page._tr = Mock(side_effect=lambda _key, default, **_kwargs: default)
        page.window = Mock(return_value=None)

        with patch("presets.ui.common.user_presets_page.InfoBar.success"):
            UserPresetsPageBase._on_preset_item_action_finished(
                page,
                4,
                "delete",
                result,
                {"file_name": "first.txt"},
            )

        page._runtime_service.remove_deleted_preset_locally.assert_called_once_with("first.txt")
        page._runtime_service.mark_presets_structure_changed.assert_not_called()

    def test_preset_model_renames_visible_preset_without_full_reset(self) -> None:
        model = PresetListModel()
        model.set_rows([
            {
                "kind": "preset",
                "file_name": "old.txt",
                "name": "Old",
                "folder_key": "common",
                "is_active": True,
            },
        ])
        model.beginResetModel = Mock(side_effect=AssertionError("rename must not reset the whole preset list"))

        self.assertTrue(model.rename_preset("old.txt", "new.txt", name="New"))

        self.assertEqual(model.find_preset_row("old.txt"), -1)
        self.assertEqual(model.find_preset_row("new.txt"), 0)
        self.assertEqual(model.index(0, 0).data(PresetListModel.FileNameRole), "new.txt")
        self.assertEqual(model.index(0, 0).data(PresetListModel.NameRole), "New")
        self.assertEqual(model.active_preset_file_name(), "new.txt")

    def test_user_presets_rename_updates_visible_row_without_reload(self) -> None:
        result = SimpleNamespace(
            ok=True,
            structure_changed=True,
            log_message="Переименован",
            log_level="INFO",
            infobar_level="",
            infobar_title="",
            infobar_content="",
            error_code="",
            preset_file_name="new.txt",
            preset_display_name="New",
        )
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._preset_edit_action_request_id = 5
        page._runtime_service = Mock()
        page._runtime_service.rename_preset_locally.return_value = True

        UserPresetsPageBase._on_preset_edit_action_finished(
            page,
            5,
            "rename",
            result,
            {"current_name": "old.txt", "new_name": "New"},
        )

        page._runtime_service.rename_preset_locally.assert_called_once_with(
            "old.txt",
            "new.txt",
            "New",
        )
        page._runtime_service.mark_presets_structure_changed.assert_not_called()

    def test_preset_model_inserts_created_preset_without_full_reset(self) -> None:
        model = PresetListModel()
        model.set_rows([
            {
                "kind": "folder",
                "folder_key": "common",
                "name": "Общие",
                "text": "Общие",
                "count": 1,
                "is_collapsed": False,
            },
            {
                "kind": "preset",
                "file_name": "old.txt",
                "name": "Old",
                "folder_key": "common",
                "is_active": False,
            },
        ])
        model.beginResetModel = Mock(side_effect=AssertionError("create must not reset the whole preset list"))

        self.assertTrue(model.insert_preset({
            "kind": "preset",
            "file_name": "new.txt",
            "name": "New",
            "folder_key": "common",
            "is_active": False,
        }))

        self.assertEqual(model.find_preset_row("new.txt"), 2)
        self.assertEqual(model.index(0, 0).data(PresetListModel.CountRole), 2)

    def test_user_presets_create_updates_visible_row_without_reload(self) -> None:
        result = SimpleNamespace(
            ok=True,
            structure_changed=True,
            log_message="Создан",
            log_level="INFO",
            infobar_level="",
            infobar_title="",
            infobar_content="",
            error_code="",
            preset_file_name="new.txt",
            preset_display_name="New",
        )
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._preset_edit_action_request_id = 6
        page._runtime_service = Mock()
        page._runtime_service.add_created_preset_locally.return_value = True

        UserPresetsPageBase._on_preset_edit_action_finished(
            page,
            6,
            "create",
            result,
            {"name": "New"},
        )

        page._runtime_service.add_created_preset_locally.assert_called_once_with(
            "new.txt",
            "New",
        )
        page._runtime_service.mark_presets_structure_changed.assert_not_called()

    def test_user_presets_duplicate_updates_visible_row_without_reload(self) -> None:
        result = SimpleNamespace(
            ok=True,
            structure_changed=True,
            log_message="Дублирован",
            log_level="INFO",
            infobar_level="",
            infobar_title="",
            infobar_content="",
            error_code="",
            preset_file_name="copy.txt",
            preset_display_name="Copy",
        )
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._preset_item_action_request_id = 7
        page._runtime_service = Mock()
        page._runtime_service.add_created_preset_locally.return_value = True
        page._tr = Mock(side_effect=lambda _key, default, **_kwargs: default)
        page.window = Mock(return_value=None)

        UserPresetsPageBase._on_preset_item_action_finished(
            page,
            7,
            "duplicate",
            result,
            {"file_name": "source.txt", "display_name": "Source"},
        )

        page._runtime_service.add_created_preset_locally.assert_called_once_with(
            "copy.txt",
            "Copy",
        )
        page._runtime_service.mark_presets_structure_changed.assert_not_called()

    def test_user_presets_import_updates_visible_row_without_reload(self) -> None:
        result = SimpleNamespace(
            ok=True,
            structure_changed=True,
            log_message="Импортирован",
            log_level="INFO",
            infobar_level="success",
            infobar_title="Пресет импортирован",
            infobar_content="Готово",
            actual_file_name="imported.txt",
            actual_name="Imported",
        )
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._preset_bulk_action_request_id = 8
        page._runtime_service = Mock()
        page._runtime_service.add_created_preset_locally.return_value = True
        page.window = Mock(return_value=None)

        with patch("presets.ui.common.user_presets_page.InfoBar.success"):
            UserPresetsPageBase._on_preset_bulk_action_finished(
                page,
                8,
                "import",
                result,
                {},
            )

        page._runtime_service.add_created_preset_locally.assert_called_once_with(
            "imported.txt",
            "Imported",
        )
        page._runtime_service.mark_presets_structure_changed.assert_not_called()

    def test_user_presets_display_name_uses_visible_cache_not_backend_manifest(self) -> None:
        class _ListingApi:
            def resolve_display_name(self, _reference: str) -> str:
                raise AssertionError("display name must not be resolved from backend in GUI path")

        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._page_api = type("_PageApi", (), {"listing": _ListingApi()})()
        page._runtime_service = UserPresetsRuntimeService()
        page._runtime_service._cached_presets_metadata = {
            "cached.txt": {"display_name": "Cached Preset"},
        }
        page._presets_model = PresetListModel()
        page._presets_model.set_rows(
            [
                {
                    "kind": "preset",
                    "file_name": "visible.txt",
                    "name": "Visible Preset",
                }
            ]
        )
        page._presets_model.find_preset_row = Mock(
            side_effect=AssertionError("display name should use model display cache")
        )

        self.assertEqual(page._resolve_display_name("visible.txt"), "Visible Preset")
        self.assertEqual(page._resolve_display_name("cached.txt"), "Cached Preset")
        self.assertEqual(page._resolve_display_name("fallback.txt"), "fallback")

    def test_user_presets_builtin_check_uses_visible_cache_not_backend_storage(self) -> None:
        class _StorageApi:
            def is_builtin_preset_file_with_cache(self, _name: str, _cached_metadata) -> bool:
                raise AssertionError("builtin check must not be resolved from backend in GUI path")

        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._page_api = type("_PageApi", (), {"storage": _StorageApi()})()
        page._runtime_service = UserPresetsRuntimeService()
        page._runtime_service._cached_presets_metadata = {
            "cached.txt": {"is_builtin": True},
        }
        page._presets_model = PresetListModel()
        page._presets_model.set_rows(
            [
                {
                    "kind": "preset",
                    "file_name": "visible.txt",
                    "name": "Visible Preset",
                    "is_builtin": True,
                }
            ]
        )
        page._presets_model.find_preset_row = Mock(
            side_effect=AssertionError("builtin check should use model builtin cache")
        )

        self.assertTrue(page._is_builtin_preset_file("visible.txt"))
        self.assertTrue(page._is_builtin_preset_file("cached.txt"))
        self.assertFalse(page._is_builtin_preset_file("fallback.txt"))

    def test_user_presets_rating_menu_uses_visible_cache_not_backend_metadata(self) -> None:
        class _RuntimeService:
            def cached_presets_metadata(self):
                raise AssertionError("rating menu should use model rating cache")

        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._runtime_service = _RuntimeService()
        page._config = SimpleNamespace(tr_prefix="presets")
        page._tr = Mock(side_effect=lambda _key, fallback="": fallback)
        page._request_preset_storage_action = Mock()
        page._presets_model = PresetListModel()
        page._presets_model.set_rows(
            [
                {
                    "kind": "preset",
                    "file_name": "visible.txt",
                    "name": "Visible Preset",
                    "rating": 6,
                }
            ]
        )

        with patch(
            "presets.ui.common.user_presets_page.show_preset_rating_menu",
            return_value=8,
        ) as menu_mock:
            page._show_rating_menu("visible.txt")

        menu_mock.assert_called_once()
        self.assertEqual(menu_mock.call_args.kwargs["current_rating"], 6)
        page._request_preset_storage_action.assert_called_once_with(
            "rating",
            name="visible.txt",
            display_name="Visible Preset",
            rating=8,
        )

    def test_user_presets_cleanup_stops_action_workers_and_pending_requests(self) -> None:
        class _Runtime:
            def __init__(self) -> None:
                self.stop = Mock()
                self.cancel = Mock()

        class _Timer:
            def __init__(self) -> None:
                self.stop = Mock()

        runtime_attrs = (
            "_preset_activate_runtime",
            "_preset_item_action_runtime",
            "_preset_bulk_action_runtime",
            "_preset_edit_action_runtime",
            "_preset_storage_action_runtime",
            "_preset_folder_action_runtime",
            "_preset_open_folder_runtime",
            "_preset_link_action_runtime",
        )
        request_attrs = (
            "_preset_activate_request_id",
            "_preset_item_action_request_id",
            "_preset_bulk_action_request_id",
            "_preset_edit_action_request_id",
            "_preset_storage_action_request_id",
            "_preset_folder_action_request_id",
            "_preset_open_folder_request_id",
            "_preset_link_action_request_id",
        )
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        runtimes = {attr: _Runtime() for attr in runtime_attrs}
        for attr, runtime in runtimes.items():
            setattr(page, attr, runtime)
        for attr in request_attrs:
            setattr(page, attr, 7)
        page._pending_preset_activation = ("next.txt", "Next")
        page._preset_folder_action_pending = [{"action": "load_state"}]
        page._preset_open_folder_pending = True
        page._preset_link_action_pending = ["info"]
        page._preset_bulk_action_kind = "reset_all"
        page._bulk_reset_running = True
        page._layout_resync_timer = _Timer()
        page._layout_resync_delayed_timer = _Timer()
        page._preset_search_timer = _Timer()
        page._ui_state_unsubscribe = Mock()
        page._ui_state_store = object()
        page._runtime_service = Mock()

        UserPresetsPageBase.cleanup(page)

        for runtime in runtimes.values():
            runtime.stop.assert_called_once()
            runtime.cancel.assert_called_once()
        for attr in request_attrs:
            self.assertEqual(getattr(page, attr), 8)
        self.assertIsNone(page._pending_preset_activation)
        self.assertEqual(page._preset_folder_action_pending, [])
        self.assertFalse(page._preset_open_folder_pending)
        self.assertEqual(page._preset_link_action_pending, [])
        self.assertEqual(page._preset_bulk_action_kind, "")
        self.assertFalse(page._bulk_reset_running)
        page._runtime_service.stop_watching_presets.assert_called_once()

    def test_user_presets_menu_selected_check_uses_runtime_marker(self) -> None:
        source = inspect.getsource(UserPresetsPageBase._is_selected_source_preset_file)

        self.assertIn("active_preset_file_name", source)
        self.assertNotIn("_get_selected_source_preset_file_name_light", source)

    def test_user_preset_activation_worker_is_created_through_feature(self) -> None:
        request_source = inspect.getsource(UserPresetsPageBase._request_preset_activation)
        start_source = inspect.getsource(UserPresetsPageBase._start_preset_activation_worker)
        create_worker_source = inspect.getsource(UserPresetsPageBase.create_preset_activate_worker)

        self.assertIn("_start_preset_activation_worker", request_source)
        self.assertIn("create_preset_activate_worker", start_source)
        self.assertNotIn("UserPresetActivateWorker", create_worker_source)
        self.assertIn("_create_preset_activate_worker_fn", create_worker_source)

    def test_user_presets_runtime_does_not_keep_file_action_fallbacks(self) -> None:
        page_source = inspect.getsource(UserPresetsPageBase)
        runtime_source = inspect.getsource(user_presets_page_runtime)

        self.assertNotIn("def _actions_api", page_source)
        self.assertNotIn("class UserPresetsActionsApi", runtime_source)
        self.assertNotIn("class _UserPresetsActionsApiImpl", runtime_source)
        self.assertNotIn("def create_preset(self, *, name", runtime_source)
        self.assertNotIn("def import_preset_from_file(self, *, file_path", runtime_source)
        self.assertNotIn("def activate_preset(self, *, file_name", runtime_source)
        self.assertNotIn("def duplicate_preset(self, *, file_name", runtime_source)
        self.assertNotIn("def open_presets_info(self)", runtime_source)
        self.assertNotIn(
            "presets.ui.common.user_presets_page_runtime",
            inspect.getsource(presets_feature_facade),
        )

    def test_user_presets_item_file_actions_run_through_worker(self) -> None:
        worker_source = inspect.getsource(UserPresetItemActionWorker.run)
        request_source = inspect.getsource(UserPresetsPageBase._request_preset_item_action)
        start_source = inspect.getsource(UserPresetsPageBase._start_preset_item_action_worker)
        create_worker_source = inspect.getsource(UserPresetsPageBase.create_preset_item_action_worker)

        for method in (
            UserPresetsPageBase._on_duplicate_preset,
            UserPresetsPageBase._on_reset_preset,
            UserPresetsPageBase._on_delete_preset,
            UserPresetsPageBase._on_export_preset,
        ):
            source = inspect.getsource(method)
            self.assertIn("_request_preset_item_action", source)
            self.assertNotIn("duplicate_preset_action", source)
            self.assertNotIn("reset_preset_action", source)
            self.assertNotIn("delete_preset_action", source)
            self.assertNotIn("export_preset_action", source)
            self.assertNotIn(".duplicate_preset(", source)
            self.assertNotIn(".reset_preset_to_builtin(", source)
            self.assertNotIn(".delete_preset(", source)
            self.assertNotIn(".export_preset(", source)

        delete_source = inspect.getsource(UserPresetsPageBase._on_delete_preset)
        self.assertIn("_is_builtin_preset_file", delete_source)
        self.assertNotIn("_storage_api().is_builtin_preset_file", delete_source)
        self.assertIn("_start_preset_item_action_worker", request_source)
        self.assertIn("create_preset_item_action_worker", start_source)
        self.assertNotIn("UserPresetItemActionWorker", create_worker_source)
        self.assertIn("_create_preset_item_action_worker_fn", create_worker_source)
        self.assertIn("self._duplicate_preset", worker_source)
        self.assertIn("self._reset_preset_to_builtin", worker_source)
        self.assertIn("self._delete_preset", worker_source)
        self.assertIn("self._export_preset", worker_source)
        self.assertNotIn("actions_api.", worker_source)

    def test_user_presets_import_and_reset_all_run_through_worker(self) -> None:
        import_source = inspect.getsource(UserPresetsPageBase._on_import_clicked)
        reset_source = inspect.getsource(UserPresetsPageBase._on_reset_all_presets_clicked)

        self.assertTrue(hasattr(user_presets_action_workers, "UserPresetBulkActionWorker"))
        worker_source = inspect.getsource(user_presets_action_workers.UserPresetBulkActionWorker.run)
        request_source = inspect.getsource(UserPresetsPageBase._request_preset_bulk_action)
        start_source = inspect.getsource(UserPresetsPageBase._start_preset_bulk_action_worker)
        create_worker_source = inspect.getsource(UserPresetsPageBase.create_preset_bulk_action_worker)

        for source in (import_source, reset_source):
            self.assertIn("_request_preset_bulk_action", source)
            self.assertNotIn("import_preset_action", source)
            self.assertNotIn("run_reset_all_presets_action", source)
            self.assertNotIn(".import_preset_from_file(", source)
            self.assertNotIn(".reset_all_presets(", source)

        self.assertIn("_start_preset_bulk_action_worker", request_source)
        self.assertIn("create_preset_bulk_action_worker", start_source)
        self.assertNotIn("UserPresetBulkActionWorker", create_worker_source)
        self.assertIn("_create_preset_bulk_action_worker_fn", create_worker_source)
        self.assertIn("self._import_preset_from_file", worker_source)
        self.assertIn("self._reset_all_presets", worker_source)
        self.assertNotIn("actions_api.", worker_source)

    def test_user_presets_create_and_rename_run_through_worker(self) -> None:
        create_source = inspect.getsource(UserPresetsPageBase._show_inline_action_create)
        rename_source = inspect.getsource(UserPresetsPageBase._show_inline_action_rename)

        self.assertTrue(hasattr(user_presets_action_workers, "UserPresetEditActionWorker"))
        worker_source = inspect.getsource(user_presets_action_workers.UserPresetEditActionWorker.run)
        request_source = inspect.getsource(UserPresetsPageBase._request_preset_edit_action)
        start_source = inspect.getsource(UserPresetsPageBase._start_preset_edit_action_worker)
        create_worker_source = inspect.getsource(UserPresetsPageBase.create_preset_edit_action_worker)

        for source in (create_source, rename_source):
            body_source = "\n".join(source.splitlines()[1:])
            self.assertIn("_request_preset_edit_action", source)
            self.assertNotIn("show_inline_action_create(", body_source)
            self.assertNotIn("show_inline_action_rename(", body_source)
            self.assertNotIn(".create_preset(", source)
            self.assertNotIn(".rename_preset(", source)

        self.assertIn("_start_preset_edit_action_worker", request_source)
        self.assertIn("create_preset_edit_action_worker", start_source)
        self.assertNotIn("UserPresetEditActionWorker", create_worker_source)
        self.assertIn("_create_preset_edit_action_worker_fn", create_worker_source)
        self.assertIn("self._create_preset", worker_source)
        self.assertIn("self._rename_preset", worker_source)
        self.assertNotIn("actions_api.", worker_source)

    def test_user_presets_info_links_open_through_worker(self) -> None:
        from presets.ui.common import user_presets_item_actions_workflow

        info_source = inspect.getsource(UserPresetsPageBase._open_presets_info)
        request_source = inspect.getsource(UserPresetsPageBase._request_preset_link_action)
        cleanup_source = inspect.getsource(UserPresetsPageBase._stop_action_workers_for_cleanup)
        item_actions_source = inspect.getsource(user_presets_item_actions_workflow)

        self.assertTrue(hasattr(user_presets_action_workers, "UserPresetLinkActionWorker"))
        worker_source = inspect.getsource(user_presets_action_workers.UserPresetLinkActionWorker.run)
        create_worker_source = inspect.getsource(UserPresetsPageBase.create_preset_link_action_worker)

        # Карточка «Получить конфиги» вела на пост автора и удалена
        # вместе с методом _open_new_configs_post.
        self.assertFalse(hasattr(UserPresetsPageBase, "_open_new_configs_post"))
        self.assertIn("_request_preset_link_action", info_source)
        self.assertNotIn("open_presets_info_action", info_source)

        self.assertIn("create_preset_link_action_worker", request_source)
        self.assertNotIn("UserPresetLinkActionWorker", create_worker_source)
        self.assertIn("_create_preset_link_action_worker_fn", create_worker_source)
        self.assertIn("self._open_presets_info", worker_source)
        self.assertNotIn("actions_api.", worker_source)
        self.assertNotIn("open_presets_info_action", item_actions_source)
        self.assertNotIn("open_new_configs_post_action", item_actions_source)
        self.assertNotIn("actions_api.open_presets_info", item_actions_source)
        self.assertNotIn("actions_api.open_new_configs_post", item_actions_source)
        self.assertIn("_preset_link_action_runtime", cleanup_source)
        self.assertIn(".stop(", cleanup_source)
        self.assertIn(".cancel()", cleanup_source)

    def test_user_presets_storage_actions_run_through_worker(self) -> None:
        pin_source = inspect.getsource(UserPresetsPageBase._on_toggle_pin_preset)
        rating_source = inspect.getsource(UserPresetsPageBase._show_rating_menu)
        rating_menu_source = inspect.getsource(preset_rating_menu.show_preset_rating_menu)
        move_source = inspect.getsource(UserPresetsPageBase._move_preset_by_step)
        drop_source = inspect.getsource(UserPresetsPageBase._on_item_dropped)
        finished_source = inspect.getsource(UserPresetsPageBase._on_preset_storage_action_finished)

        self.assertTrue(hasattr(user_presets_action_workers, "UserPresetStorageActionWorker"))
        worker_source = inspect.getsource(user_presets_action_workers.UserPresetStorageActionWorker.run)
        request_source = inspect.getsource(UserPresetsPageBase._request_preset_storage_action)
        start_source = inspect.getsource(UserPresetsPageBase._start_preset_storage_action_worker)
        create_source = inspect.getsource(UserPresetsPageBase.create_preset_storage_action_worker)
        runtime_source = inspect.getsource(user_presets_page_runtime.UserPresetsPageRuntime)

        for source in (pin_source, rating_source, move_source, drop_source):
            self.assertIn("_request_preset_storage_action", source)
            self.assertNotIn("toggle_pin_preset_action", source)
            self.assertNotIn("move_preset_by_step_action", source)
            self.assertNotIn("handle_item_dropped_action", source)
            self.assertNotIn("set_preset_rating(", source)
            self.assertNotIn(".toggle_preset_pin(", source)
            self.assertNotIn(".move_preset_by_step(", source)
            self.assertNotIn(".move_preset_on_drop(", source)

        self.assertNotIn("set_preset_rating(", rating_menu_source)
        self.assertNotIn("get_preset_item_meta", rating_menu_source)
        self.assertNotIn("folder_scope", rating_menu_source)
        self.assertIn("current_rating=", rating_source)
        self.assertIn("cached_presets_metadata", rating_source)
        self.assertIn("_update_cached_preset_rating", finished_source)
        self.assertIn("_start_preset_storage_action_worker", request_source)
        self.assertIn("create_preset_storage_action_worker", start_source)
        self.assertNotIn("UserPresetStorageActionWorker", create_source)
        self.assertIn("_create_preset_storage_action_worker_fn", create_source)
        self.assertNotIn("from presets.folders import toggle_preset_pin", runtime_source)
        self.assertNotIn("from presets.folders import set_preset_rating", runtime_source)
        self.assertNotIn("from presets.folders import move_preset_by_step", runtime_source)
        self.assertNotIn("from presets.folders import move_preset_after", runtime_source)
        self.assertIn("self._toggle_preset_pin", worker_source)
        self.assertIn("self._set_preset_rating", worker_source)
        self.assertIn("self._move_preset_by_step", worker_source)
        self.assertIn("self._move_preset_on_drop", worker_source)
        self.assertIn("self._load_folder_state", worker_source)
        self.assertNotIn("storage_api.", worker_source)
        self.assertIn('self._action == "pin"', worker_source)
        self.assertIn("destination_kind", worker_source)
        self.assertIn("destination_folder_key", worker_source)
        self.assertIn('context["folder_state"]', worker_source)
        self.assertIn("update_cached_folder_state", finished_source)

    def test_user_presets_queued_write_action_restarts_after_worker_signal(self) -> None:
        page = UserPresetsPageBase.__new__(UserPresetsPageBase)
        page._preset_write_action_running = Mock(return_value=False)
        page._pending_preset_write_actions = [
            {
                "kind": "storage",
                "action": "rating",
                "name": "Default.txt",
                "display_name": "Default",
                "rating": 5,
                "direction": 0,
                "cached_metadata": None,
                "source_kind": "",
                "source_id": "",
                "destination_kind": "",
                "destination_id": "",
                "destination_folder_key": "",
                "file_name": "",
                "file_path": "",
            }
        ]
        page._pending_preset_storage_actions = [{"action": "rating"}]
        page._start_preset_storage_action_worker = Mock()
        callbacks = []

        with patch(
            "presets.ui.common.user_presets_page.QTimer.singleShot",
            side_effect=lambda _delay, callback: callbacks.append(callback),
        ):
            self.assertTrue(UserPresetsPageBase._start_next_preset_write_action(page))

        page._start_preset_storage_action_worker.assert_not_called()
        self.assertEqual(len(callbacks), 1)

        callbacks[0]()

        page._start_preset_storage_action_worker.assert_called_once_with(
            "rating",
            name="Default.txt",
            display_name="Default",
            rating=5,
            direction=0,
            cached_metadata=None,
            source_kind="",
            source_id="",
            destination_kind="",
            destination_id="",
            destination_folder_key="",
        )

    def test_user_presets_folder_actions_run_through_worker(self) -> None:
        toggle_source = inspect.getsource(UserPresetsPageBase._on_toggle_folder)
        menu_source = inspect.getsource(UserPresetsPageBase._show_folder_menu)
        folder_menu_source = inspect.getsource(preset_folder_menu.show_preset_folder_menu)

        self.assertTrue(hasattr(user_presets_action_workers, "UserPresetFolderActionWorker"))
        worker_source = inspect.getsource(user_presets_action_workers.UserPresetFolderActionWorker.run)
        request_source = inspect.getsource(UserPresetsPageBase._request_preset_folder_action)
        action_finished_source = inspect.getsource(UserPresetsPageBase._on_preset_folder_action_finished)
        finished_source = inspect.getsource(UserPresetsPageBase._on_preset_folder_action_worker_finished)
        next_write_source = inspect.getsource(UserPresetsPageBase._start_next_preset_write_action)
        show_source = inspect.getsource(UserPresetsPageBase._show_folder_menu)

        for source in (toggle_source, menu_source):
            self.assertIn("_request_preset_folder_action", source)
            self.assertNotIn("set_preset_folder_collapsed(", source)
            self.assertNotIn("create_preset_folder(", source)
            self.assertNotIn("rename_preset_folder(", source)
            self.assertNotIn("delete_preset_folder(", source)
            self.assertNotIn("reset_preset_folders(", source)

        for forbidden in (
            "create_preset_folder(",
            "rename_preset_folder(",
            "delete_preset_folder(",
            "move_preset_folder_by_step(",
            "set_preset_folder_collapsed(",
            "reset_preset_folders(",
        ):
            self.assertNotIn(forbidden, folder_menu_source)

        self.assertNotIn("load_preset_folder_state", folder_menu_source)
        self.assertIn("folder_state", folder_menu_source)
        self.assertIn('"load_state"', show_source)
        self.assertIn("self._create_preset_folder", worker_source)
        self.assertIn("self._rename_preset_folder", worker_source)
        self.assertIn("self._delete_preset_folder", worker_source)
        self.assertIn("self._move_preset_folder_by_step", worker_source)
        self.assertIn("self._set_preset_folder_collapsed", worker_source)
        self.assertIn("self._reset_preset_folders", worker_source)
        self.assertIn("self._load_preset_folder_state", worker_source)
        self.assertNotIn("from presets.folders", worker_source)
        self.assertNotIn("from presets.folders import", inspect.getsource(UserPresetsPageBase))
        self.assertIn('context["folder_state"]', worker_source)
        self.assertIn("_queue_preset_folder_action", request_source)
        self.assertIn(
            "_preset_folder_action_state_obj()",
            inspect.getsource(UserPresetsPageBase._queue_preset_folder_action),
        )
        self.assertIn("_schedule_next_preset_write_action_after_finish", finished_source)
        self.assertIn("schedule_next_after_finish", inspect.getsource(UserPresetsPageBase._schedule_next_preset_write_action_after_finish))
        self.assertIn("_preset_folder_action_state_obj().pop_next()", next_write_source)
        self.assertIn("update_cached_folder_state", action_finished_source)
        self.assertIn("show_menu", action_finished_source)
        self.assertIn("create_preset_folder_action_worker", request_source)
        create_source = inspect.getsource(UserPresetsPageBase.create_preset_folder_action_worker)
        self.assertNotIn("UserPresetFolderActionWorker", create_source)
        self.assertIn("_create_preset_folder_action_worker_fn", create_source)

    def test_profile_folder_actions_run_through_worker(self) -> None:
        toggle_source = inspect.getsource(PresetSetupPageBase._on_folder_toggled)
        menu_source = inspect.getsource(PresetSetupPageBase._on_folder_context_requested)
        folder_menu_source = inspect.getsource(profile_folder_menu.show_profile_folder_menu)

        self.assertTrue(hasattr(profile_setup_loader, "ProfileFolderActionWorker"))
        worker_source = inspect.getsource(profile_setup_loader.ProfileFolderActionWorker.run)
        request_source = inspect.getsource(ProfileFolderController._request_profile_folder_action)
        action_finished_source = inspect.getsource(ProfileFolderController._on_profile_folder_action_finished)
        finished_source = inspect.getsource(ProfileFolderController._on_profile_folder_action_worker_finished)
        show_source = inspect.getsource(PresetSetupPageBase._on_folder_context_requested)

        for source in (toggle_source, menu_source):
            self.assertIn("_request_profile_folder_action", source)
            self.assertNotIn("set_profile_folder_collapsed(", source)
            self.assertNotIn("create_profile_folder(", source)
            self.assertNotIn("rename_profile_folder(", source)
            self.assertNotIn("delete_profile_folder(", source)
            self.assertNotIn("reset_profile_folders(", source)

        for forbidden in (
            "create_profile_folder(",
            "rename_profile_folder(",
            "delete_profile_folder(",
            "move_profile_folder_by_step(",
            "set_profile_folder_collapsed(",
            "reset_profile_folders(",
        ):
            self.assertNotIn(forbidden, folder_menu_source)

        self.assertNotIn("load_profile_folder_state", folder_menu_source)
        self.assertIn("folder_state", folder_menu_source)
        self.assertIn('"load_state"', show_source)
        self.assertIn("self._create_profile_folder", worker_source)
        self.assertIn("self._rename_profile_folder", worker_source)
        self.assertIn("self._delete_profile_folder", worker_source)
        self.assertIn("self._move_profile_folder_by_step", worker_source)
        self.assertIn("self._set_profile_folder_collapsed", worker_source)
        self.assertIn("self._reset_profile_folders", worker_source)
        self.assertIn("self._load_profile_folder_state", worker_source)
        self.assertNotIn("from profile.folders", worker_source)
        self.assertNotIn("from profile.folders import", inspect.getsource(PresetSetupPageBase))
        self.assertIn("_queue_profile_folder_action", request_source)
        self.assertIn(
            "_profile_folder_action_state_obj()",
            inspect.getsource(ProfileFolderController._queue_profile_folder_action),
        )
        self.assertIn("_profile_folder_action_state_obj().pop_next()", finished_source)
        self.assertIn("show_menu", action_finished_source)
        self.assertIn("_create_profile_folder_action_worker", request_source)
        create_source = inspect.getsource(PresetSetupPageBase._create_profile_folder_action_worker)
        self.assertNotIn("ProfileFolderActionWorker", create_source)
        self.assertIn("_create_profile_folder_action_worker_fn", create_source)

    def test_profile_preset_write_queue_restarts_after_worker_signal_returns(self) -> None:
        context_finished = inspect.getsource(PresetWriteQueue._on_profile_context_action_worker_finished)
        move_finished = inspect.getsource(PresetWriteQueue._on_profile_move_worker_finished)
        create_finished = inspect.getsource(PresetWriteQueue._on_user_profile_create_worker_finished)
        update_finished = inspect.getsource(PresetWriteQueue._on_user_profile_update_worker_finished)
        delete_finished = inspect.getsource(PresetWriteQueue._on_user_profile_delete_worker_finished)
        helper_source = inspect.getsource(PresetWriteQueue._schedule_next_profile_preset_write_operation_after_finish)
        schedule_source = inspect.getsource(PresetWriteQueue._schedule_next_profile_preset_write_operation_start)
        run_source = inspect.getsource(PresetWriteQueue._run_scheduled_profile_preset_write_operation_start)

        for source in (context_finished, move_finished, create_finished, update_finished, delete_finished):
            self.assertIn("_schedule_next_profile_preset_write_operation_after_finish", source)
            self.assertNotIn("_start_next_profile_preset_write_operation()", source)

        self.assertIn("schedule_next_after_finish", helper_source)
        self.assertIn("_accept_current_preset_setup_worker_finished", helper_source)
        self.assertIn("QTimer.singleShot", schedule_source)
        self.assertIn("_run_scheduled_profile_preset_write_operation_start", schedule_source)
        self.assertIn("_start_next_profile_preset_write_operation", run_source)

    def test_profile_folder_action_queue_restarts_after_worker_signal_returns(self) -> None:
        finished_source = inspect.getsource(ProfileFolderController._on_profile_folder_action_worker_finished)
        schedule_source = inspect.getsource(ProfileFolderController._schedule_profile_folder_action_start)
        run_source = inspect.getsource(ProfileFolderController._run_scheduled_profile_folder_action_start)

        self.assertIn("_profile_folder_action_state_obj().pop_next()", finished_source)
        self.assertIn("_schedule_profile_folder_action_start", finished_source)
        self.assertNotIn("_request_profile_folder_action(", finished_source)
        self.assertIn("QTimer.singleShot", schedule_source)
        self.assertIn("_run_scheduled_profile_folder_action_start", schedule_source)
        self.assertIn("_request_profile_folder_action", run_source)

    def test_profile_folder_action_queue_uses_shared_queued_worker_state(self) -> None:
        from types import SimpleNamespace

        from ui.queued_worker_state import QueuedWorkerState

        page = PresetSetupPageBase.__new__(PresetSetupPageBase)
        page._profile_folder_action_runtime = SimpleNamespace(is_running=lambda: False)

        init_source = inspect.getsource(PresetSetupPageBase.__init__)
        queue_source = inspect.getsource(ProfileFolderController._queue_profile_folder_action)
        cleanup_source = inspect.getsource(PresetSetupPageBase.cleanup)

        self.assertTrue(hasattr(PresetSetupPageBase, "_profile_folder_action_state_obj"))
        self.assertIsInstance(page._profile_folder_action_state_obj(), QueuedWorkerState)
        self.assertIn("_profile_folder_action_state = QueuedWorkerState", init_source)
        self.assertIn("_profile_folder_action_state_obj()", queue_source)
        self.assertIn("_profile_folder_action_state_obj().reset()", cleanup_source)
        self.assertNotIn("self._profile_folder_action_pending: list", init_source)
        self.assertNotIn("self._profile_folder_action_start_scheduled = False", init_source)

    def test_profile_move_updates_visible_list_locally_after_worker(self) -> None:
        finished_source = inspect.getsource(PresetWriteQueue._on_profile_move_finished)
        local_source = inspect.getsource(PresetSetupPageBase._apply_profile_move_locally)
        list_source = inspect.getsource(ProfilesList)

        self.assertIn("_apply_profile_move_locally", finished_source)
        self.assertIn("refresh_from_preset_switch", finished_source)
        self.assertLess(finished_source.index("_apply_profile_move_locally"), finished_source.index("refresh_from_preset_switch"))
        self.assertIn("move_profile_item", list_source)
        self.assertIn("move_profile_item", local_source)

    def test_profile_commands_reuse_service_cache(self) -> None:
        source = inspect.getsource(profile_commands._profile_preset_service)

        self.assertIn("_preset_service_cache", source)
        self.assertIn("cache[key]", source)

    def test_profile_service_exposes_cached_profile_payload_without_rebuilding(self) -> None:
        service_source = inspect.getsource(ProfilePresetService.get_cached_profile_list_entry)
        payload_source = inspect.getsource(ProfilePresetService.get_cached_profile_list)
        revision_source = inspect.getsource(ProfilePresetService._current_profile_list_revision)
        command_source = inspect.getsource(profile_commands.get_cached_profile_list)

        self.assertIn("_profile_list_lock", service_source)
        self.assertIn("acquire(blocking=False)", service_source)
        self.assertIn("_profile_list_snapshot_revision", service_source)
        self.assertIn("return list_revision, snapshot", service_source)
        self.assertNotIn("_list_profiles_locked(", service_source)
        self.assertIn("get_cached_profile_list_entry", payload_source)
        self.assertIn("return payload", payload_source)
        self.assertIn("_selected_preset_revision", revision_source)
        self.assertIn("load_profile_folder_state", revision_source)
        self.assertIn("get_cached_profile_list", command_source)

    def test_preset_setup_page_always_uses_worker_for_profile_payload(self) -> None:
        source = inspect.getsource(ProfilePayloadController._request_profiles_payload)

        self.assertNotIn("get_cached_profile_list", source)
        self.assertNotIn("_apply_cached_profile_payload", source)
        self.assertIn("create_profile_list_load_worker", source)
        self.assertNotIn("_show_loading_skeleton", source)

    def test_preset_setup_force_refresh_still_uses_worker_path(self) -> None:
        source = inspect.getsource(ProfilePayloadController._request_profiles_payload)

        before_worker = source.split("worker =", 1)[0]

        self.assertNotIn("get_cached_profile_list", before_worker)
        self.assertNotIn("if not force:", before_worker)
        self.assertNotIn("_apply_cached_profile_payload", before_worker)

    def test_profile_service_has_selected_preset_snapshot(self) -> None:
        source = inspect.getsource(ProfilePresetService.load_selected_preset)
        helper_source = inspect.getsource(ProfilePresetService._load_selected_preset_for_revision)

        self.assertIn("_selected_preset_revision", source)
        self.assertIn("_selected_preset_snapshot", helper_source)

    def test_profile_list_worker_logs_full_profile_payload_duration(self) -> None:
        source = inspect.getsource(ProfileListLoadWorker.run)
        module_source = inspect.getsource(importlib.import_module("profile.profile_list_loader"))

        self.assertIn("time.perf_counter", source)
        self.assertIn("profile_feature.worker.list_profiles.total", source)
        self.assertIn("log_ui_timing_since", module_source)
        self.assertNotIn("PROFILE_TIMING_LOG_LEVEL", module_source)

    def test_profile_list_worker_accepts_warmed_load_result(self) -> None:
        source = inspect.getsource(ProfileListLoadWorker.run)

        self.assertIn("ProfileListLoadResult", source)
        self.assertIn("isinstance(payload, ProfileListLoadResult)", source)

    def test_profile_list_worker_receives_loader_function(self) -> None:
        init_source = inspect.getsource(ProfileListLoadWorker.__init__)
        run_source = inspect.getsource(ProfileListLoadWorker.run)

        self.assertIn("load_profiles", init_source)
        self.assertIn("self._load_profiles", init_source)
        self.assertNotIn("self._service", init_source)
        self.assertNotIn("self._profile", init_source)
        self.assertNotIn("launch_method", init_source)
        self.assertIn("self._load_profiles()", run_source)
        self.assertNotIn("self._service.list_profiles", run_source)
        self.assertNotIn("self._profile.list_profiles", run_source)

    def test_profile_list_filter_rebuild_runs_through_worker_runtime(self) -> None:
        import profile.ui.profiles_list as profiles_list_module
        from ui.latest_value_worker_state import LatestValueWorkerState

        page = ProfilesList.__new__(ProfilesList)
        page._view_state_runtime = Mock()
        list_source = inspect.getsource(ProfilesList)
        init_source = inspect.getsource(ProfilesList.__init__)
        build_source = inspect.getsource(ProfilesList.build_profiles)
        update_source = inspect.getsource(ProfilesList.update_profiles)
        search_source = inspect.getsource(ProfilesList.set_search_query)
        request_source = inspect.getsource(ProfilesList._request_view_state_rebuild)
        finished_source = inspect.getsource(ProfilesList._on_view_state_worker_finished)
        type_source = inspect.getsource(ProfilesList._apply_profile_type_filter)
        toggle_source = inspect.getsource(ProfilesList._on_delegate_action)
        expand_source = inspect.getsource(ProfilesList.expand_all)
        collapse_source = inspect.getsource(ProfilesList.collapse_all)
        all_groups_source = inspect.getsource(ProfilesList._request_all_groups_expanded)
        folder_state_source = inspect.getsource(ProfilesList.apply_profile_folder_state)
        replace_item_source = inspect.getsource(ProfilesList.replace_profile_item)
        add_item_source = inspect.getsource(ProfilesList.add_profile_item)
        remove_item_source = inspect.getsource(ProfilesList.remove_profile_item)
        move_item_source = inspect.getsource(ProfilesList.move_profile_item)
        worker_source = inspect.getsource(profiles_list_module.ProfileListViewStateWorker.run)

        self.assertIn("OneShotWorkerRuntime", list_source)
        self.assertIn("LatestValueWorkerState", list_source)
        self.assertTrue(hasattr(ProfilesList, "_view_state_state_obj"))
        self.assertIsInstance(page._view_state_state_obj(), LatestValueWorkerState)
        self.assertIn("_view_state_state = LatestValueWorkerState", init_source)
        self.assertNotIn("_view_state_runtime_worker = None", init_source)
        self.assertNotIn("_view_state_rebuild_pending = False", init_source)
        self.assertIn("_view_state_state_obj()", request_source)
        self.assertIn("_view_state_state_obj()", finished_source)
        self.assertIn("_request_view_state_rebuild", build_source)
        self.assertIn("_request_view_state_rebuild", update_source)
        self.assertIn("_request_view_state_rebuild", search_source)
        self.assertIn("_request_view_state_rebuild", type_source)
        self.assertIn("_request_view_state_rebuild", toggle_source)
        self.assertIn("_request_all_groups_expanded", expand_source)
        self.assertIn("_request_all_groups_expanded", collapse_source)
        self.assertIn("_request_view_state_rebuild", all_groups_source)
        self.assertIn("_request_view_state_rebuild", folder_state_source)
        self.assertIn("_request_view_state_rebuild", replace_item_source)
        self.assertIn("_request_view_state_rebuild", add_item_source)
        self.assertIn("_request_view_state_rebuild", remove_item_source)
        self.assertIn("_request_view_state_rebuild", move_item_source)
        self.assertNotIn("self._model.set_profiles", build_source)
        self.assertNotIn("self._model.update_profiles", update_source)
        self.assertNotIn("self._model.set_search_query", search_source)
        self.assertNotIn("self._model.set_active_profile_types", type_source)
        self.assertNotIn("self._model.set_group_expanded", toggle_source)
        self.assertNotIn("self._model.set_all_groups_expanded", expand_source)
        self.assertNotIn("self._model.set_all_groups_expanded", collapse_source)
        self.assertNotIn("self._model.apply_folder_state", folder_state_source)
        self.assertNotIn("self._model.replace_profile", replace_item_source)
        self.assertNotIn("self._model.add_profile", add_item_source)
        self.assertNotIn("self._model.remove_profile", remove_item_source)
        self.assertNotIn("self._model.move_profile", move_item_source)
        self.assertIn("build_profile_list_view_state", worker_source)
        self.assertIn("folder_state", worker_source)

    def test_profile_feature_warms_profile_list_without_mass_setup_warm(self) -> None:
        source = inspect.getsource(ProfileFeature.warm_profile_list)
        class_source = inspect.getsource(ProfileFeature)

        self.assertIn("service.list_profiles", source)
        self.assertIn("build_profile_list_view_state", source)
        self.assertIn("ProfileListLoadResult", source)
        self.assertIn("profile_warmup.list_profiles", source)
        self.assertIn("profile_warmup.view_state", source)
        self.assertNotIn("warm_profile_setups", source)
        self.assertNotIn("profile_warmup.setup_payloads", source)
        self.assertNotIn("_profile_list_load_result_cache", class_source)

    def test_profile_feature_profile_list_worker_reads_service_cache(self) -> None:
        source = inspect.getsource(ProfileFeature.create_profile_list_load_worker)

        self.assertIn("view_state_options", source)
        self.assertIn("active_profile_types", source)
        self.assertIn("search_query", source)
        self.assertIn("group_expanded", source)
        self.assertIn("build_profile_list_view_state", source)
        self.assertIn("service.list_profiles()", source)
        self.assertNotIn("_profile_list_load_result", source)

    def test_profile_service_logs_profile_payload_stages(self) -> None:
        source = inspect.getsource(ProfilePresetService._list_profiles_locked)
        timing_source = inspect.getsource(ProfilePresetService._log_timing)

        self.assertIn("profile_feature.strategy_catalogs.load", source)
        self.assertIn("profile_feature.templates.load", source)
        self.assertIn("profile_feature.folder_state.load", source)
        self.assertIn("profile_feature.sources.build", source)
        self.assertIn("profile_feature.profile_list_item.build", source)
        self.assertIn("log_ui_timing_since", timing_source)
        self.assertIn("important=True", timing_source)

    def test_profile_worker_yields_during_large_payload_builds(self) -> None:
        source = inspect.getsource(ProfilePresetService._list_profiles_locked)
        helper_source = inspect.getsource(ProfilePresetService._yield_profile_payload_worker)

        self.assertIn("_yield_profile_payload_worker", source)
        self.assertIn("time.sleep(0)", helper_source)

    def test_profile_service_serializes_profile_list_snapshot_builds(self) -> None:
        source = inspect.getsource(ProfilePresetService.list_profiles)

        self.assertIn("_profile_list_lock", source)
        self.assertIn("_list_profiles_locked", source)

    def test_preset_setup_page_logs_profile_list_ui_apply_stages(self) -> None:
        source = inspect.getsource(PresetSetupPageBase._apply_payload)
        timing_source = inspect.getsource(PresetSetupPageBase._log_ui_timing)

        self.assertIn("profile_ui.apply_payload.total", source)
        self.assertIn("profile_ui.profile_list.create", source)
        self.assertIn("profile_ui.profile_list.build", source)
        self.assertIn("profile_ui.profile_list.attach", source)
        self.assertIn("log_ui_timing_since", timing_source)
        self.assertIn("important=label in", timing_source)


    def test_base_page_language_uses_warmed_cache_not_settings_read(self) -> None:
        base_source = inspect.getsource(BasePage._resolve_ui_language)
        navigation_source = inspect.getsource(navigation_text_sync.resolve_ui_language)

        self.assertIn("peek_warmed_ui_language", base_source)
        self.assertIn("peek_warmed_ui_language", navigation_source)
        self.assertNotIn("load_ui_language", base_source)
        self.assertNotIn("load_ui_language", navigation_source)


    def test_telegram_proxy_restart_request_survives_queued_settings_saves(self) -> None:
        from telegram_proxy.runtime.settings_save_flow import merge_restart_request

        self.assertEqual(merge_restart_request("", "schedule"), "schedule")
        self.assertEqual(merge_restart_request("schedule", ""), "schedule")
        self.assertEqual(merge_restart_request("schedule", "now"), "now")
        self.assertEqual(merge_restart_request("now", "schedule"), "now")

        completed_source = inspect.getsource(TelegramProxyFeature._on_settings_save_completed)
        flushed_source = inspect.getsource(TelegramProxyPage._on_settings_flushed)

        self.assertIn("merge_restart_request", completed_source)
        self.assertIn("restart_pending", completed_source)
        self.assertIn("_dispatch_pending_restart(restart)", flushed_source)


    def test_theme_uses_warmed_accent_and_tinted_settings(self) -> None:
        tint_source = inspect.getsource(ui_theme._compute_tint_color)
        accent_source = inspect.getsource(ui_theme._sync_theme_accent_to_qfluent)

        self.assertIn("peek_warmed_tinted_settings", tint_source)
        self.assertIn("peek_warmed_accent_color", accent_source)
        self.assertNotIn("load_tinted_settings", tint_source)
        self.assertNotIn("load_accent_color", accent_source)

    def test_window_appearance_uses_warmed_state_without_settings_reads(self) -> None:
        background_source = inspect.getsource(ui_theme.apply_window_background)
        opacity_source = inspect.getsource(window_appearance_state.apply_window_opacity_value)
        startup_source = inspect.getsource(main_entry._configure_window_appearance)

        combined = "\n".join((background_source, opacity_source, startup_source))
        self.assertIn("peek_warmed_background_preset", combined)
        self.assertIn("peek_warmed_window_opacity", combined)
        self.assertNotIn("load_background_preset", combined)
        # Mica тоже берётся из прогретого состояния; запрещено чтение
        # настройки, а не само слово — локальная переменная mica_enabled
        # законна.
        self.assertIn("peek_warmed_mica_enabled", combined)
        self.assertNotIn("load_mica_enabled", combined)
        self.assertNotIn("get_mica_enabled", combined)
        self.assertNotIn("load_window_opacity", combined)


    def test_support_page_external_links_run_through_worker(self) -> None:
        from app.feature_facades.external import ExternalActionsFeature
        import app.external_workers as external_workers

        page_source = inspect.getsource(SupportPage)
        feature_source = inspect.getsource(ExternalActionsFeature)
        worker_source = inspect.getsource(external_workers.ExternalActionWorker.run)

        self.assertTrue(hasattr(external_workers, "ExternalActionWorker"))
        self.assertIn("_support_open_runtime", page_source)
        self.assertIn("create_support_open_action_worker", page_source)
        self.assertIn("_create_support_open_action_worker", page_source)
        self.assertIn("create_external_action_worker", feature_source)
        self.assertNotIn("ui.pages.support_open_worker", page_source)
        for method_name in (
            "_open_support_discussions",
        ):
            source = inspect.getsource(getattr(SupportPage, method_name))
            self.assertIn("_request_support_open_action", source)
            self.assertNotIn("_open_discussions_action()", source)
            self.assertNotIn("_open_telegram_action()", source)
            self.assertNotIn("_open_discord_action()", source)

        self.assertIn("action_fn", worker_source)

    def test_about_page_external_actions_run_through_worker(self) -> None:
        from app.feature_facades.external import ExternalActionsFeature
        import app.external_workers as external_workers

        page_source = inspect.getsource(AboutPage)
        feature_source = inspect.getsource(ExternalActionsFeature)
        worker_source = inspect.getsource(external_workers.ExternalActionWorker.run)

        self.assertTrue(hasattr(external_workers, "ExternalActionWorker"))
        self.assertIn("_about_open_runtime", page_source)
        self.assertIn("create_about_open_action_worker", page_source)
        self.assertIn("_create_about_open_action_worker", page_source)
        self.assertIn("create_external_action_worker", feature_source)
        self.assertNotIn("ui.pages.about_open_worker", page_source)
        for method_name in (
            "_open_support_discussions",
            "_open_forum_for_beginners",
        ):
            source = inspect.getsource(getattr(AboutPage, method_name))
            self.assertIn("_request_about_open_action", source)
            self.assertNotIn("_action()", source)

        self.assertIn("action_fn", worker_source)

    def test_page_language_is_not_reapplied_on_every_repeat_navigation(self) -> None:
        class _Page:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def set_ui_language(self, language: str) -> None:
                self.calls.append(language)

        window = type("_Window", (), {})()
        window.ui_session = type("_Session", (), {"ui_language": "ru"})()
        page = _Page()

        navigation_text_sync.apply_ui_language_to_page(window, page)
        navigation_text_sync.apply_ui_language_to_page(window, page)
        window.ui_session.ui_language = "en"
        navigation_text_sync.apply_ui_language_to_page(window, page)

        self.assertEqual(page.calls, ["ru", "en"])

    def test_page_language_skips_initial_reapply_when_page_already_matches_window(self) -> None:
        class _Page:
            def __init__(self) -> None:
                self._ui_language = "ru"
                self.calls: list[str] = []

            def set_ui_language(self, language: str) -> None:
                self.calls.append(language)

        window = type("_Window", (), {})()
        window.ui_session = type("_Session", (), {"ui_language": "ru"})()
        page = _Page()

        navigation_text_sync.apply_ui_language_to_page(window, page)

        self.assertEqual(page.calls, [])
        self.assertEqual(page._last_applied_ui_language, "ru")

    def test_page_language_still_applies_when_page_language_is_unknown(self) -> None:
        class _Page:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def set_ui_language(self, language: str) -> None:
                self.calls.append(language)

        window = type("_Window", (), {})()
        window.ui_session = type("_Session", (), {"ui_language": "ru"})()
        page = _Page()

        navigation_text_sync.apply_ui_language_to_page(window, page)

        self.assertEqual(page.calls, ["ru"])


    def test_telegram_proxy_initial_state_is_backend_plan_not_ui_loading(self) -> None:
        telegram_proxy_workers = importlib.import_module("telegram_proxy.runtime.workers")

        init_source = inspect.getsource(TelegramProxyPage.__init__)
        after_source = inspect.getsource(TelegramProxyPage._after_ui_built)
        request_source = inspect.getsource(TelegramProxyPage._request_initial_state_load)
        loaded_source = inspect.getsource(TelegramProxyPage._on_initial_state_loaded)
        cleanup_source = inspect.getsource(TelegramProxyPage.cleanup)
        page_source = inspect.getsource(TelegramProxyPage)
        settings_build_source = inspect.getsource(telegram_proxy_settings_build.build_telegram_proxy_settings_panel)
        settings_source = inspect.getsource(telegram_proxy_settings.load_page_initial_state)
        feature_source = inspect.getsource(TelegramProxyFeature)
        worker_source = inspect.getsource(telegram_proxy_workers.TelegramProxyInitialStateWorker.run)

        self.assertIn("_request_initial_state_load", init_source)
        self.assertIn("_initial_state_runtime", page_source)
        self.assertIn("start_qthread_worker", request_source)
        self.assertIn("bind_worker", request_source)
        self.assertIn("worker.completed.connect(self._on_initial_state_loaded)", request_source)
        self.assertIn("worker.failed.connect(self._on_initial_state_failed)", request_source)
        self.assertIn("_initial_state_runtime.is_current", loaded_source)
        self.assertIn("_initial_state_runtime.stop", cleanup_source)
        self.assertNotIn("_initial_state_worker =", page_source)
        self.assertNotIn("worker.start()", request_source)
        self.assertNotIn("self._telegram_proxy.load_page_initial_state()", init_source)
        self.assertIn("_apply_initial_settings_state", page_source)
        self.assertNotIn("self._load_settings()", after_source)
        self.assertNotIn("load_settings_into_ui", after_source)
        self.assertNotIn("UpstreamCatalog.load_from_runtime", settings_build_source)
        self.assertIn("create_initial_state_worker", page_source)
        self.assertIn("create_page_initial_state_worker", feature_source)
        self.assertNotIn("def load_page_initial_state", feature_source)

        self.assertIn("read_settings", settings_source)
        self.assertNotIn("get_tg_proxy_host", settings_source)
        self.assertNotIn("get_tg_proxy_port", settings_source)
        self.assertNotIn("get_tg_proxy_upstream_enabled", settings_source)
        self.assertIn("load_page_initial_state=self.load_page_initial_state", feature_source)
        self.assertIn("_load_page_initial_state", worker_source)
        self.assertNotIn("telegram_proxy.runtime.commands", worker_source)
        self.assertNotIn("telegram_proxy.settings", worker_source)
        self.assertIn("load_page_initial_state", worker_source)

    def test_telegram_proxy_initial_state_plan_reads_settings_once(self) -> None:
        from telegram_proxy.config.upstream_catalog import UpstreamCatalog

        catalog = UpstreamCatalog(build_presets=[
            {
                "id": "build:test",
                "name": "Test",
                "type": "socks5",
                "source": "build",
                "host": "10.0.0.2",
                "port": 1081,
                "username": "u",
                "password": "p",
            }
        ])
        data = {
            "telegram_proxy": {
                "host": "0.0.0.0",
                "port": 1453,
                "upstream_enabled": True,
                "upstream_host": "10.0.0.2",
                "upstream_port": 1081,
                "upstream_user": "u",
                "upstream_pass": "p",
                "upstream_mode": "always",
            },
        }

        with (
            patch("telegram_proxy.config.upstream_catalog.UpstreamCatalog.load_from_runtime", return_value=catalog),
            patch("settings.store.read_settings", return_value=data) as read_settings,
        ):
            plan = telegram_proxy_settings.load_page_initial_state()

        self.assertEqual(read_settings.call_count, 1)
        self.assertIs(plan.upstream_catalog, catalog)
        self.assertEqual(plan.settings.host, "0.0.0.0")
        self.assertEqual(plan.settings.port, 1453)
        self.assertTrue(plan.settings.upstream_enabled)
        self.assertEqual(plan.settings.upstream_host, "10.0.0.2")
        self.assertEqual(plan.settings.upstream_port, 1081)
        self.assertEqual(plan.settings.upstream_user, "u")
        self.assertEqual(plan.settings.upstream_password, "p")
        self.assertEqual(plan.settings.upstream_mode, "always")
        self.assertEqual(plan.settings.upstream_preset_index, 1)

    def test_telegram_proxy_log_lines_write_through_worker(self) -> None:
        append_source = inspect.getsource(TelegramProxyPage._append_log_line)
        request_source = inspect.getsource(TelegramProxyPage._request_log_line_append)
        start_source = inspect.getsource(TelegramProxyPage._start_log_line_worker)
        failed_source = inspect.getsource(TelegramProxyPage._on_log_line_worker_failed)
        cleanup_source = inspect.getsource(TelegramProxyPage.cleanup)
        page_source = inspect.getsource(TelegramProxyPage)
        feature_source = inspect.getsource(TelegramProxyFeature)

        self.assertTrue(hasattr(telegram_proxy_commands, "append_log_line"))
        command_source = inspect.getsource(telegram_proxy_commands.append_log_line)
        self.assertTrue(hasattr(telegram_proxy_workers, "TelegramProxyLogLineWorker"))
        worker_source = inspect.getsource(telegram_proxy_workers.TelegramProxyLogLineWorker.run)

        self.assertIn("_request_log_line_append", append_source)
        self.assertNotIn("proxy_logger.log", append_source)
        self.assertIn("_log_line_runtime", page_source)
        self.assertIn("start_qthread_worker", start_source)
        self.assertIn("bind_worker", start_source)
        self.assertIn("worker.completed.connect(self._on_log_line_worker_completed)", start_source)
        self.assertIn("worker.failed.connect(self._on_log_line_worker_failed)", start_source)
        self.assertIn('_queued_worker_state("_log_line_state", "_log_line_runtime")', request_source)
        self.assertIn("state.start_or_queue", request_source)
        self.assertIn("_log_line_runtime.is_current", failed_source)
        self.assertIn("_log_line_runtime.stop", cleanup_source)
        self.assertNotIn("_log_line_worker =", page_source)
        self.assertNotIn("worker.start()", start_source)
        self.assertIn("create_log_line_worker", feature_source)
        self.assertIn("append_log_line", command_source)
        self.assertIn("append_log_line", worker_source)

    def test_telegram_proxy_auto_deeplink_check_runs_through_worker(self) -> None:
        due_source = inspect.getsource(TelegramProxyPage._run_due_auto_deeplink)
        request_source = inspect.getsource(TelegramProxyPage._request_auto_deeplink_check)
        start_source = inspect.getsource(TelegramProxyPage._start_auto_deeplink_worker)
        checked_source = inspect.getsource(TelegramProxyPage._on_auto_deeplink_checked)
        cleanup_source = inspect.getsource(TelegramProxyPage.cleanup)
        page_source = inspect.getsource(TelegramProxyPage)
        feature_source = inspect.getsource(TelegramProxyFeature)

        self.assertTrue(hasattr(telegram_proxy_commands, "consume_auto_deeplink_request"))
        command_source = inspect.getsource(telegram_proxy_commands.consume_auto_deeplink_request)
        self.assertTrue(hasattr(telegram_proxy_workers, "TelegramProxyAutoDeeplinkWorker"))
        worker_source = inspect.getsource(telegram_proxy_workers.TelegramProxyAutoDeeplinkWorker.run)

        self.assertIn("_request_auto_deeplink_check", due_source)
        self.assertNotIn("consume_auto_deeplink_request", due_source)
        self.assertIn("_auto_deeplink_runtime", page_source)
        self.assertIn("_start_auto_deeplink_worker", request_source)
        self.assertIn("start_qthread_worker", start_source)
        self.assertIn("bind_worker", start_source)
        self.assertIn("worker.completed.connect(self._on_auto_deeplink_checked)", start_source)
        self.assertIn("worker.failed.connect(self._on_auto_deeplink_failed)", start_source)
        self.assertIn("_auto_deeplink_runtime.is_current", checked_source)
        self.assertIn("_auto_deeplink_runtime.stop", cleanup_source)
        self.assertNotIn("_auto_deeplink_worker =", page_source)
        self.assertNotIn("worker.start()", start_source)
        self.assertIn("create_auto_deeplink_worker", feature_source)
        self.assertIn("telegram_proxy.config.settings", command_source)
        self.assertIn("consume_auto_deeplink_request", worker_source)

    def test_dns_check_save_runs_through_worker(self) -> None:
        page_source = inspect.getsource(dns_check_page.DNSCheckPage)
        save_source = inspect.getsource(dns_check_page.DNSCheckPage.save_results)

        self.assertTrue(hasattr(dns_check_worker, "DNSCheckSaveWorker"))
        self.assertTrue(hasattr(dns_commands, "save_dns_check_results"))
        worker_source = inspect.getsource(dns_check_worker.DNSCheckSaveWorker.run)
        commands_source = inspect.getsource(dns_commands.save_dns_check_results)
        feature_source = inspect.getsource(__import__("app.feature_facades.dns", fromlist=["build_dns_feature"]).build_dns_feature)

        self.assertIn("create_dns_check_save_worker", page_source)
        self.assertIn("_start_save_results_worker", save_source)
        self.assertNotIn("save_results_text(", save_source)
        self.assertIn("save_dns_check_results=save_dns_check_results", feature_source)
        self.assertIn("_save_dns_check_results", worker_source)
        self.assertNotIn("dns_commands", worker_source)
        self.assertNotIn("dns.dns_check_plans", worker_source)
        self.assertIn("open(", commands_source)
        self.assertIn("os.startfile", commands_source)

    def test_dns_check_worker_runs_poisoning_check_through_commands(self) -> None:
        page_source = inspect.getsource(dns_check_page.DNSCheckPage)

        self.assertTrue(hasattr(dns_commands, "run_dns_poisoning_check"))
        worker_source = inspect.getsource(dns_check_worker.DNSCheckWorker.run)
        commands_source = inspect.getsource(dns_commands.run_dns_poisoning_check)
        feature_source = inspect.getsource(__import__("app.feature_facades.dns", fromlist=["build_dns_feature"]).build_dns_feature)

        self.assertIn("create_dns_check_worker", page_source)
        self.assertIn("run_dns_poisoning_check=run_dns_poisoning_check", feature_source)
        self.assertIn("_run_dns_poisoning_check", worker_source)
        self.assertNotIn("dns_commands", worker_source)
        self.assertNotIn("dns_checker", worker_source)
        self.assertNotIn("diagnostics.engine", worker_source)
        self.assertIn("run_dns_check", commands_source)

    def test_telegram_proxy_settings_save_runs_through_worker(self) -> None:
        from telegram_proxy.ui.advanced_page import TelegramProxyAdvancedPage

        page_source = inspect.getsource(TelegramProxyPage)
        upstream_source = inspect.getsource(telegram_upstream_workflow)
        runtime_source = inspect.getsource(telegram_runtime_workflow)
        request_source = inspect.getsource(TelegramProxyFeature.request_settings_save)
        start_source = inspect.getsource(TelegramProxyFeature._start_settings_save_worker)
        completed_source = inspect.getsource(TelegramProxyFeature._on_settings_save_completed)
        failed_source = inspect.getsource(TelegramProxyFeature._on_settings_save_failed)
        finished_source = inspect.getsource(TelegramProxyFeature._on_settings_save_worker_finished)
        cleanup_source = inspect.getsource(TelegramProxyFeature.cleanup)
        command_source = inspect.getsource(telegram_proxy_commands)
        queued_state_source = inspect.getsource(TelegramProxyPageQueuedWorkerState)

        self.assertTrue(hasattr(telegram_proxy_workers, "TelegramProxySettingsSaveWorker"))
        worker_source = inspect.getsource(telegram_proxy_workers.TelegramProxySettingsSaveWorker.run)

        for page_cls, handler_name in (
            (TelegramProxyPage, "_on_port_changed"),
            (TelegramProxyPage, "_on_host_changed"),
            (TelegramProxyPage, "_on_auto_deeplink_toggled"),
            (TelegramProxyAdvancedPage, "_on_upstream_changed"),
            (TelegramProxyAdvancedPage, "_on_upstream_preset_changed"),
            (TelegramProxyAdvancedPage, "_on_manual_upstream_edited"),
            (TelegramProxyAdvancedPage, "_on_upstream_port_changed"),
            (TelegramProxyAdvancedPage, "_on_upstream_mode_changed"),
        ):
            source = inspect.getsource(getattr(page_cls, handler_name))
            self.assertRegex(source, r"_request_(?:manual_upstream|settings)_save")
            self.assertNotIn("telegram_proxy_settings.set_", source)

        for page_cls in (TelegramProxyPage, TelegramProxyAdvancedPage):
            self.assertIn(
                "self._telegram_proxy.request_settings_save(",
                inspect.getsource(page_cls._request_settings_save),
            )
        self.assertIn("_queue_settings_save_payload", request_source)
        self.assertIn("has_pending_settings_saves", request_source)
        self.assertIn("replace_by_key", inspect.getsource(TelegramProxyFeature._queue_settings_save_payload))
        self.assertIn("start_qthread_worker", start_source)
        self.assertIn("bind_worker", start_source)
        self.assertIn("worker.completed.connect(self._on_settings_save_completed)", start_source)
        self.assertIn("worker.failed.connect(self._on_settings_save_failed)", start_source)
        self.assertIn("runtime.is_current", completed_source)
        self.assertIn("runtime.is_current", failed_source)
        self.assertIn("schedule_next_after_finish", finished_source)
        self.assertIn("pop_next_after_finish", queued_state_source)
        self.assertIn("runtime.stop", cleanup_source)
        self.assertNotIn("_settings_save_runtime", page_source)
        self.assertNotIn("worker.start()", start_source)
        self.assertNotIn("import telegram_proxy.settings", upstream_source)
        self.assertNotIn("telegram_proxy_settings.set_", upstream_source)
        self.assertNotIn("telegram_proxy_settings.set_proxy_enabled", runtime_source)
        self.assertIn("request_proxy_enabled_save", runtime_source)
        self.assertIn('"proxy_enabled"', page_source)
        feature_source = inspect.getsource(TelegramProxyFeature)
        self.assertIn("save_settings_action=self.save_settings_action", feature_source)
        self.assertIn("_save_settings_action", worker_source)
        self.assertNotIn("telegram_proxy.runtime.commands", worker_source)
        self.assertNotIn("telegram_proxy.settings", worker_source)
        self.assertIn("save_settings_action", worker_source)
        for setter in (
            "set_host",
            "set_port",
            "set_proxy_enabled",
            "set_upstream_enabled",
            "set_upstream_preset",
            "set_manual_upstream",
            "set_upstream_mode",
            "set_auto_deeplink",
        ):
            self.assertIn(setter, command_source)

    def test_telegram_proxy_relay_http_probe_is_command_not_ui_runtime(self) -> None:
        page_runtime_source = inspect.getsource(telegram_page.telegram_proxy_page_runtime)
        feature_source = inspect.getsource(TelegramProxyFeature)
        worker_source = inspect.getsource(telegram_proxy_workers.TelegramProxyRelayCheckWorker.run)

        self.assertTrue(hasattr(telegram_proxy_commands, "check_relay_http"))
        command_source = inspect.getsource(telegram_proxy_commands.check_relay_http)

        self.assertNotIn("socket.", page_runtime_source)
        self.assertIn("check_relay_reachable=self.check_relay_reachable", feature_source)
        self.assertIn("check_relay_http=self.check_relay_http", feature_source)
        self.assertIn("_check_relay_reachable", worker_source)
        self.assertIn("_check_relay_http", worker_source)
        self.assertNotIn("telegram_proxy.runtime.commands", worker_source)
        self.assertIn("check_relay_http", worker_source)
        self.assertIn("socket.create_connection", command_source)

    def test_telegram_proxy_open_log_file_runs_through_worker(self) -> None:
        page_source = inspect.getsource(TelegramProxyPage)
        handler_source = inspect.getsource(TelegramProxyPage._on_open_log_file)
        start_source = inspect.getsource(TelegramProxyPage._start_open_log_file_worker)
        cleanup_source = inspect.getsource(TelegramProxyPage.cleanup)
        feature_source = inspect.getsource(TelegramProxyFeature)

        self.assertTrue(hasattr(telegram_proxy_workers, "TelegramProxyOpenLogFileWorker"))
        worker_source = inspect.getsource(telegram_proxy_workers.TelegramProxyOpenLogFileWorker.run)

        self.assertIn("_start_open_log_file_worker", handler_source)
        self.assertNotIn(".open_log_file(", handler_source)
        self.assertIn("create_open_log_file_worker", page_source)
        self.assertIn("_open_log_file_runtime", page_source)
        self.assertIn("start_qthread_worker", start_source)
        self.assertIn("bind_worker", start_source)
        self.assertIn("worker.completed.connect(self._on_open_log_file_finished)", start_source)
        self.assertIn("worker.failed.connect(self._on_open_log_file_failed)", start_source)
        self.assertIn('_queued_worker_state("_open_log_file_state", "_open_log_file_runtime")', start_source)
        self.assertIn("state.is_busy()", start_source)
        self.assertIn("_open_log_file_runtime.stop", cleanup_source)
        self.assertNotIn("_open_log_file_worker =", page_source)
        self.assertNotIn("worker.start()", start_source)
        self.assertIn("create_open_log_file_worker", feature_source)
        self.assertIn("open_log_file", worker_source)

    def test_telegram_proxy_external_links_run_through_worker(self) -> None:
        from telegram_proxy.ui.advanced_page import TelegramProxyAdvancedPage

        page_source = inspect.getsource(TelegramProxyPage)
        telegram_source = inspect.getsource(TelegramProxyPage._on_open_in_telegram)
        mtproxy_source = inspect.getsource(TelegramProxyAdvancedPage._on_open_mtproxy)
        start_source = inspect.getsource(TelegramProxyPage._start_external_link_worker)
        cleanup_source = inspect.getsource(TelegramProxyPage.cleanup)
        advanced_cleanup_source = inspect.getsource(TelegramProxyAdvancedPage.cleanup)
        feature_source = inspect.getsource(TelegramProxyFeature)

        self.assertTrue(hasattr(telegram_proxy_workers, "TelegramProxyExternalLinkWorker"))
        worker_source = inspect.getsource(telegram_proxy_workers.TelegramProxyExternalLinkWorker.run)

        self.assertIn("_start_external_link_worker", telegram_source)
        for source in (mtproxy_source, telegram_source):
            self.assertNotIn(".open_external_link(", source)
        self.assertIn("_external_link_runtime.start_qthread_worker", mtproxy_source)
        self.assertIn("create_external_link_worker", mtproxy_source)
        self.assertIn("_external_link_runtime", advanced_cleanup_source)

        self.assertIn("create_external_link_worker", page_source)
        self.assertIn("_external_link_runtime", page_source)
        self.assertIn("start_qthread_worker", start_source)
        self.assertIn("bind_worker", start_source)
        self.assertIn("worker.completed.connect(self._on_external_link_finished)", start_source)
        self.assertIn("worker.failed.connect(self._on_external_link_failed)", start_source)
        self.assertIn('_queued_worker_state("_external_link_state", "_external_link_runtime")', start_source)
        self.assertIn("state.is_busy()", start_source)
        self.assertIn("_external_link_runtime.stop", cleanup_source)
        self.assertNotIn("_external_link_worker =", page_source)
        self.assertNotIn("worker.start()", start_source)
        self.assertIn("create_external_link_worker", feature_source)
        self.assertIn("open_external_link", worker_source)

    def test_telegram_proxy_stop_runs_through_worker(self) -> None:
        page_source = inspect.getsource(TelegramProxyPage)
        stop_source = inspect.getsource(TelegramProxyPage._stop_proxy)
        request_source = inspect.getsource(TelegramProxyPage._request_proxy_stop)
        start_source = inspect.getsource(TelegramProxyPage._start_proxy_stop_worker)
        runtime_source = inspect.getsource(telegram_runtime_workflow.stop_proxy_runtime)

        self.assertTrue(hasattr(telegram_proxy_workers, "TelegramProxyStopRuntimeWorker"))
        worker_source = inspect.getsource(telegram_proxy_workers.TelegramProxyStopRuntimeWorker.run)

        self.assertIn("_request_proxy_stop", stop_source)
        self.assertIn("_start_proxy_stop_worker", request_source)
        self.assertIn("stop_proxy_runtime", start_source)
        self.assertNotIn("manager.stop_proxy()", stop_source)
        self.assertNotIn("manager.stop_proxy()", request_source)
        self.assertNotIn("manager.stop_proxy()", start_source)
        self.assertNotIn("manager.stop_proxy()", runtime_source)
        self.assertIn("create_stop_runtime_worker", runtime_source)
        self.assertIn("_proxy_stop_runtime", page_source)
        self.assertIn("_finish_stop_proxy", runtime_source)
        self.assertIn("QMetaObject.invokeMethod", runtime_source)
        self.assertIn('_request_settings_save("proxy_enabled", enabled=False)', page_source)
        self.assertIn("stop_proxy", worker_source)

    def test_blockcheck_initial_state_is_backend_plan_not_ui_loading(self) -> None:
        spec = importlib.util.find_spec("blockcheck.workers")
        self.assertIsNotNone(spec)
        blockcheck_workers = importlib.import_module("blockcheck.workers")

        init_source = inspect.getsource(BlockcheckPage.__init__)
        build_source = inspect.getsource(BlockcheckPage._build_ui)
        request_source = inspect.getsource(BlockcheckPage._request_page_initial_state_load)
        loaded_source = inspect.getsource(BlockcheckPage._on_initial_state_loaded)
        cleanup_source = inspect.getsource(BlockcheckPage.cleanup)
        page_source = inspect.getsource(BlockcheckPage)
        helper_source = inspect.getsource(blockcheck_ui_helpers)
        runtime_source = inspect.getsource(blockcheck_page_runtime.load_page_initial_state)
        feature_source = inspect.getsource(BlockcheckFeature)
        worker_source = inspect.getsource(blockcheck_workers.BlockcheckInitialStateWorker.run)

        self.assertIn("_request_page_initial_state_load", init_source)
        self.assertIn("_initial_state_runtime", page_source)
        self.assertIn("start_qthread_worker", request_source)
        self.assertIn("bind_worker", request_source)
        self.assertIn("worker.completed.connect(self._on_initial_state_loaded)", request_source)
        self.assertIn("worker.failed.connect(self._on_initial_state_failed)", request_source)
        self.assertIn("_initial_state_runtime.is_current", loaded_source)
        self.assertIn("_initial_state_runtime.stop", cleanup_source)
        self.assertNotIn("_initial_state_worker =", page_source)
        self.assertNotIn("worker.start()", request_source)
        self.assertNotIn("self._blockcheck.load_page_initial_state()", init_source)
        self.assertIn("_apply_initial_domain_chips", build_source)
        self.assertNotIn("self._load_domain_chips()", build_source)
        self.assertNotIn("load_domain_chips", helper_source)
        self.assertIn("read_settings", runtime_source)
        self.assertNotIn("get_blockcheck_settings", runtime_source)
        self.assertIn("create_initial_state_worker", page_source)
        self.assertIn("create_page_initial_state_worker", feature_source)
        self.assertIn("load_page_initial_state=self.load_page_initial_state", feature_source)
        self.assertIn("_load_page_initial_state", worker_source)
        self.assertNotIn("blockcheck.commands", worker_source)
        self.assertNotIn("blockcheck.page_runtime", worker_source)
        self.assertIn("load_page_initial_state", worker_source)

    def test_blockcheck_initial_state_plan_reads_settings_once(self) -> None:
        data = {
            "blockcheck": {
                "user_domains": [" Example.COM ", "", "discord.com"],
            },
        }

        with patch("settings.store.read_settings", return_value=data) as read_settings:
            plan = blockcheck_page_runtime.load_page_initial_state()

        self.assertEqual(read_settings.call_count, 1)
        self.assertEqual(plan.user_domains, ("example.com", "discord.com"))

    def test_blockcheck_run_log_writes_are_owned_by_worker(self) -> None:
        start_source = inspect.getsource(blockcheck_page_run_workflow.start_blockcheck_page_run)
        page_source = inspect.getsource(BlockcheckPage)
        worker_source = inspect.getsource(blockcheck_worker.BlockcheckWorker)

        self.assertNotIn("blockcheck_page_runtime.start_run_log", start_source)
        self.assertNotIn("blockcheck_page_runtime.append_run_log", page_source)
        self.assertNotIn("_append_run_log", page_source)
        self.assertNotIn("blockcheck.commands", worker_source)
        self.assertNotIn("blockcheck.page_runtime", worker_source)
        self.assertIn("run_log_started", worker_source)
        self.assertIn("_start_run_log", worker_source)
        self.assertIn("_append_run_log_action", worker_source)

    def test_strategy_scan_run_log_writes_are_owned_by_worker(self) -> None:
        strategy_scan_run_workflow = importlib.import_module("blockcheck.strategy_scan_run_workflow")
        strategy_scan_results_workflow = importlib.import_module("blockcheck.ui.strategy_scan_page_results_workflow")
        strategy_scan_worker = importlib.import_module("blockcheck.strategy_scan_worker")

        start_source = inspect.getsource(strategy_scan_run_workflow.start_strategy_scan_run)
        run_workflow_source = inspect.getsource(strategy_scan_run_workflow)
        results_workflow_source = inspect.getsource(strategy_scan_results_workflow)
        worker_source = inspect.getsource(strategy_scan_worker.StrategyScanWorker)

        self.assertNotIn(".start_run_log", start_source)
        self.assertNotIn(".append_run_log", run_workflow_source)
        self.assertNotIn("append_strategy_scan_log", results_workflow_source)
        self.assertNotIn("blockcheck.commands", worker_source)
        self.assertNotIn("blockcheck.strategy_scan_logs", worker_source)
        self.assertIn("run_log_started", worker_source)
        self.assertIn("_start_run_log_action", worker_source)
        self.assertIn("_append_run_log_action", worker_source)

    def test_strategy_scan_page_receives_worker_factory_not_runtime_feature(self) -> None:
        from app.page_names import PageName
        from ui.page_deps.system import build_blockcheck_page_kwargs

        blockcheck_page_init = inspect.getsource(BlockcheckPage.__init__)
        blockcheck_page_source = inspect.getsource(BlockcheckPage)
        strategy_page_init = inspect.getsource(StrategyScanPage.__init__)
        strategy_start_source = inspect.getsource(StrategyScanPage._on_start)
        workflow_start_source = inspect.getsource(blockcheck_page_run_workflow.start_blockcheck_page_run)
        strategy_workflow = importlib.import_module("blockcheck.strategy_scan_run_workflow")
        strategy_workflow_source = inspect.getsource(strategy_workflow.start_strategy_scan_run)

        self.assertNotIn("runtime_feature", blockcheck_page_init)
        self.assertNotIn("self._runtime_feature", blockcheck_page_source)
        self.assertNotIn("runtime_feature", strategy_page_init)
        self.assertNotIn("self._runtime_feature", strategy_start_source)
        self.assertIn("create_strategy_scan_worker", strategy_page_init)
        self.assertIn("create_strategy_scan_worker", strategy_workflow_source)
        self.assertNotIn("runtime_feature=runtime_feature", strategy_workflow_source)
        self.assertNotIn("runtime_feature", workflow_start_source)

        blockcheck_feature = Mock()
        runtime_feature = Mock()
        kwargs = build_blockcheck_page_kwargs(
            page_name=PageName.BLOCKCHECK,
            blockcheck_feature=blockcheck_feature,
            dns_feature=Mock(),
            runtime_feature=runtime_feature,
        )

        self.assertNotIn("runtime_feature", kwargs)
        self.assertIn("create_strategy_scan_worker", kwargs)
        kwargs["create_strategy_scan_worker"](target="example.org", mode="quick", parent=object())
        blockcheck_feature.create_strategy_scan_worker.assert_called_once()
        _, call_kwargs = blockcheck_feature.create_strategy_scan_worker.call_args
        # Сканер работает в своём QThread: остановка идёт через worker-вариант,
        # который применяет runtime-state (и UI-подписчиков) в GUI-потоке.
        self.assertIs(call_kwargs["shutdown_sync"], runtime_feature.shutdown_sync_from_worker)

    def test_blockcheck_support_bundle_prepares_through_worker(self) -> None:
        blockcheck_workers = importlib.import_module("blockcheck.workers")
        page_source = inspect.getsource(BlockcheckPage)
        handler_source = inspect.getsource(BlockcheckPage._prepare_support_from_blockcheck)
        worker_source = inspect.getsource(blockcheck_workers.BlockcheckSupportPrepareWorker.run)
        feature_source = inspect.getsource(BlockcheckFeature)

        self.assertIn("_request_support_prepare", handler_source)
        self.assertNotIn("blockcheck_page_runtime.prepare_support", handler_source)
        self.assertIn("create_support_prepare_worker", page_source)
        self.assertIn("_support_prepare_runtime", page_source)
        self.assertIn("start_qthread_worker", page_source)
        self.assertIn("bind_worker", page_source)
        self.assertIn("_on_support_prepare_finished", page_source)
        self.assertIn("_on_support_prepare_failed", page_source)
        self.assertIn("_support_prepare_runtime.is_current", page_source)
        self.assertIn("_support_prepare_runtime.stop", page_source)
        self.assertNotIn("_support_prepare_worker =", page_source)
        self.assertNotIn("worker.start()", inspect.getsource(BlockcheckPage._request_support_prepare))
        self.assertIn("create_blockcheck_support_prepare_worker", feature_source)
        self.assertIn("prepare_support=self.prepare_support", feature_source)
        self.assertIn("_prepare_support", worker_source)
        self.assertNotIn("blockcheck.commands", worker_source)
        self.assertNotIn("blockcheck.page_runtime", worker_source)
        self.assertIn("prepare_support", worker_source)

    def test_blockcheck_user_domain_actions_run_through_commands(self) -> None:
        blockcheck_workers = importlib.import_module("blockcheck.workers")
        page_source = inspect.getsource(BlockcheckPage)
        feature_source = inspect.getsource(BlockcheckFeature)
        worker_source = inspect.getsource(blockcheck_workers.BlockcheckUserDomainActionWorker.run)

        self.assertIn("create_user_domain_action_worker", page_source)
        self.assertIn("create_user_domain_action_worker", feature_source)
        self.assertIn("run_user_domain_action=self.run_user_domain_action", feature_source)
        self.assertIn("_run_user_domain_action", worker_source)
        self.assertNotIn("blockcheck.commands", worker_source)
        self.assertNotIn("blockcheck.page_runtime", worker_source)
        self.assertIn("run_user_domain_action", worker_source)

    def test_strategy_scan_support_bundle_prepares_through_worker(self) -> None:
        blockcheck_workers = importlib.import_module("blockcheck.workers")
        page_source = inspect.getsource(StrategyScanPage)
        handler_source = inspect.getsource(StrategyScanPage._prepare_support_from_strategy_scan)
        worker_source = inspect.getsource(blockcheck_workers.StrategyScanSupportPrepareWorker.run)
        feature_source = inspect.getsource(BlockcheckFeature)

        self.assertIn("_request_support_prepare", handler_source)
        self.assertNotIn("prepare_strategy_scan_support", handler_source)
        self.assertIn("create_support_prepare_worker", page_source)
        self.assertIn("_support_prepare_runtime", page_source)
        self.assertIn("start_qthread_worker", page_source)
        self.assertNotIn("_support_prepare_worker =", page_source)
        self.assertNotIn("worker.start()", inspect.getsource(StrategyScanPage._request_support_prepare))
        self.assertIn("create_strategy_scan_support_prepare_worker", feature_source)
        self.assertIn("prepare_strategy_scan_support=self.prepare_strategy_scan_support", feature_source)
        self.assertIn("_prepare_strategy_scan_support", worker_source)
        self.assertNotIn("blockcheck.commands", worker_source)
        self.assertNotIn("blockcheck.strategy_scan_logs", worker_source)
        self.assertIn("prepare_strategy_scan_support", worker_source)

    def test_strategy_scan_apply_runs_through_worker(self) -> None:
        spec = importlib.util.find_spec("blockcheck.strategy_apply_worker")
        self.assertIsNotNone(spec)
        strategy_apply_worker = importlib.import_module("blockcheck.strategy_apply_worker")

        apply_source = inspect.getsource(StrategyScanPage._on_apply_strategy)
        page_source = inspect.getsource(StrategyScanPage)
        finished_source = inspect.getsource(StrategyScanPage._on_strategy_apply_finished)
        feature_source = inspect.getsource(BlockcheckFeature)
        worker_source = inspect.getsource(strategy_apply_worker.StrategyApplyWorker.run)

        self.assertIn("_request_strategy_apply", apply_source)
        self.assertNotIn("self._blockcheck.apply_strategy(", apply_source)
        self.assertIn("create_strategy_apply_worker", page_source)
        self.assertIn("_strategy_apply_runtime", page_source)
        self.assertIn("start_qthread_worker", page_source)
        self.assertNotIn("_strategy_apply_worker =", page_source)
        self.assertNotIn("worker.start()", inspect.getsource(StrategyScanPage._request_strategy_apply))
        self.assertIn("create_strategy_apply_worker", feature_source)
        self.assertIn("build_apply_success_plan", finished_source)
        self.assertIn("apply_strategy", worker_source)

    def test_strategy_scan_quick_targets_load_through_worker(self) -> None:
        import blockcheck.workers as blockcheck_workers

        page_source = inspect.getsource(StrategyScanPage)
        handler_source = inspect.getsource(StrategyScanPage._show_quick_domains_menu)
        feature_source = inspect.getsource(BlockcheckFeature)

        self.assertTrue(hasattr(blockcheck_workers, "StrategyScanQuickTargetsWorker"))
        worker_source = inspect.getsource(blockcheck_workers.StrategyScanQuickTargetsWorker.run)

        self.assertIn("create_quick_targets_worker", page_source)
        self.assertIn("create_strategy_scan_quick_targets_worker", feature_source)
        self.assertIn("build_quick_target_menu_plan=self.build_quick_target_menu_plan", feature_source)
        self.assertIn("_build_quick_target_menu_plan", worker_source)
        self.assertNotIn("blockcheck.commands", worker_source)
        self.assertNotIn("blockcheck.strategy_scan_page_plans", worker_source)
        self.assertIn("build_quick_target_menu_plan", worker_source)
        self.assertNotIn("build_quick_target_menu_plan", handler_source)

    def test_strategy_scan_has_no_resume_cursor(self) -> None:
        import blockcheck.workers as blockcheck_workers

        page_source = inspect.getsource(StrategyScanPage)
        feature_source = inspect.getsource(BlockcheckFeature)

        # Порядок стратегий задаёт история подбора, а не курсор продолжения.
        # «Продолжить с места остановки» вернулось 30 сентября, но считается
        # по той же истории (сколько стратегий на цели уже не сработало) —
        # отдельного сохранённого курсора по-прежнему нет.
        self.assertFalse(hasattr(blockcheck_workers, "StrategyScanResumeSaveWorker"))
        for source in (page_source, feature_source):
            for cursor_marker in ("resume_cursor", "ResumeSave", "save_resume", "resume_index"):
                self.assertNotIn(cursor_marker, source)
        self.assertIn("count_resumable_strategies", feature_source)

    def test_strategy_scan_finish_plan_finalizes_through_worker(self) -> None:
        import blockcheck.workers as blockcheck_workers

        strategy_scan_results_workflow = importlib.import_module("blockcheck.ui.strategy_scan_page_results_workflow")
        page_source = inspect.getsource(StrategyScanPage)
        finished_source = inspect.getsource(StrategyScanPage._on_finished)
        apply_finished_source = inspect.getsource(strategy_scan_results_workflow.apply_finished_scan)
        feature_source = inspect.getsource(BlockcheckFeature)

        self.assertTrue(hasattr(blockcheck_workers, "StrategyScanFinalizeWorker"))
        worker_source = inspect.getsource(blockcheck_workers.StrategyScanFinalizeWorker.run)

        self.assertIn("_request_strategy_scan_finalize", finished_source)
        self.assertIn("create_strategy_scan_finalize_worker", page_source)
        self.assertIn("_strategy_scan_finalize_worker", page_source)
        self.assertIn("create_strategy_scan_finalize_worker", feature_source)
        self.assertNotIn("finalize_scan_report", apply_finished_source)
        self.assertIn("finalize_scan_report=self.finalize_scan_report", feature_source)
        self.assertIn("_finalize_scan_report", worker_source)
        self.assertNotIn("blockcheck_public", worker_source)
        self.assertIn("finalize_scan_report", worker_source)

    def test_logs_file_operations_log_internal_timing_stages(self) -> None:
        list_source = inspect.getsource(log_commands.list_logs)
        stats_source = inspect.getsource(log_commands.build_stats)

        self.assertIn("logs_feature.list_logs.total", list_source)
        self.assertIn("logs_feature.list_logs.glob", list_source)
        self.assertIn("logs_feature.list_logs.sort", list_source)
        self.assertIn("logs_feature.build_stats.total", stats_source)

    def test_logs_page_file_listing_and_stats_are_loaded_through_worker(self) -> None:
        from app.page_names import PageName
        from ui.page_composition import PAGE_DEPS_BUILDERS
        from ui.page_deps.system import build_logs_page_kwargs

        init_source = inspect.getsource(LogsPage.__init__)
        deps_source = inspect.getsource(build_logs_page_kwargs)
        page_source = inspect.getsource(LogsPage)
        refresh_source = inspect.getsource(LogsPage._refresh_logs_list)
        stats_source = inspect.getsource(LogsPage._update_stats)
        runtime_source = inspect.getsource(LogsPage._run_runtime_init_once)

        self.assertNotIn("runtime_feature", init_source)
        self.assertNotIn("runtime_feature", deps_source)
        self.assertNotIn("self._runtime =", page_source)
        self.assertNotIn("runtime", PAGE_DEPS_BUILDERS[PageName.LOGS].features)
        self.assertIn("_start_logs_overview_worker", refresh_source)
        self.assertIn("_start_logs_overview_worker", stats_source)
        self.assertNotIn(".list_logs(", refresh_source)
        self.assertNotIn(".build_stats(", stats_source)
        self.assertIn("update_stats_fn=self._update_stats", runtime_source)
        self.assertNotIn("refresh_logs_fn=", runtime_source)

        # orchestra_feature ушёл вместе с оркестратором (30 сентября).
        kwargs = build_logs_page_kwargs(
            page_name=PageName.LOGS,
            logs_feature=Mock(),
        )
        self.assertNotIn("runtime_feature", kwargs)

    def test_logs_page_secondary_panels_are_built_after_initial_shell(self) -> None:
        build_source = inspect.getsource(LogsPage._build_logs_tab)
        activation_source = inspect.getsource(LogsPage.on_page_activated)
        runtime_schedule_source = inspect.getsource(LogsPage._schedule_runtime_init)
        runtime_flush_source = inspect.getsource(LogsPage._run_scheduled_runtime_init)
        scheduled_source = inspect.getsource(LogsPage._schedule_logs_secondary_panels)
        ensure_source = inspect.getsource(LogsPage._ensure_logs_secondary_panels)

        self.assertIn("build_logs_primary_tab_ui", build_source)
        self.assertNotIn("build_logs_secondary_panels_ui", build_source)
        self.assertIn("_schedule_logs_secondary_panels", activation_source)
        self.assertIn("_schedule_runtime_init", activation_source)
        self.assertNotIn("self._run_runtime_init_once()", activation_source)
        self.assertIn("QTimer.singleShot", runtime_schedule_source)
        self.assertIn("_run_runtime_init_once", runtime_flush_source)
        self.assertIn("QTimer.singleShot", scheduled_source)
        self.assertIn("build_logs_secondary_panels_ui", ensure_source)

    def test_logs_page_management_tab_is_built_only_when_opened(self) -> None:
        build_source = inspect.getsource(LogsPage._build_ui)
        switch_source = inspect.getsource(LogsPage._switch_tab)

        self.assertNotIn("self._build_manage_tab", build_source)
        self.assertIn("index == 2", switch_source)
        self.assertIn("self._build_manage_tab", switch_source)


    def test_updater_changelog_links_open_through_worker(self) -> None:
        from app.page_names import PageName
        from ui.page_deps.system import build_servers_page_kwargs

        external_workers = importlib.import_module("app.external_workers")
        page_source = inspect.getsource(ServersPage)
        init_source = inspect.getsource(ServersPage.__init__)
        build_source = inspect.getsource(ServersPage._build_ui)
        create_source = inspect.getsource(ServersPage.create_changelog_link_open_worker)

        self.assertTrue(hasattr(external_workers, "ExternalOpenUrlWorker"))
        worker_source = inspect.getsource(external_workers.ExternalOpenUrlWorker.run)

        self.assertIn("open_url=self._request_changelog_link_open", build_source)
        self.assertNotIn("open_url=self._external_actions.open_url", build_source)
        self.assertIn("create_changelog_link_open_worker", page_source)
        self.assertNotIn("external_actions_feature", init_source)
        self.assertNotIn("self._external_actions", page_source)
        self.assertIn("self._create_changelog_link_open_worker", create_source)
        self.assertIn("_request_changelog_link_open", page_source)
        self.assertIn("_changelog_link_open_runtime", page_source)
        self.assertIn("_stop_changelog_link_open_worker", page_source)
        self.assertIn("open_url", worker_source)

        external_actions = Mock()
        kwargs = build_servers_page_kwargs(
            page_name=PageName.SERVERS,
            runtime_feature=Mock(),
            updater_feature=Mock(),
            external_actions_feature=external_actions,
            show_page=Mock(),
            request_exit=Mock(),
        )
        self.assertNotIn("external_actions_feature", kwargs)
        self.assertIn("create_changelog_link_open_worker", kwargs)

        parent = object()
        kwargs["create_changelog_link_open_worker"](8, url="https://example.org", parent=parent)
        external_actions.create_open_url_worker.assert_called_once_with(
            8,
            url="https://example.org",
            parent=parent,
        )

    def test_logs_cleanup_stops_overview_worker(self) -> None:
        cleanup_source = inspect.getsource(LogsPage.cleanup)

        self.assertIn("_stop_logs_overview_worker(blocking=False)", cleanup_source)
        self.assertIn("_stop_log_source(blocking=False)", cleanup_source)

    def test_logs_support_bundle_prepares_through_worker(self) -> None:
        support_worker = importlib.import_module("log.support_worker")
        page_source = inspect.getsource(LogsPage)
        handler_source = inspect.getsource(LogsPage._prepare_support_from_logs)
        feature_source = inspect.getsource(__import__("app.feature_facades.logs", fromlist=["LogsFeature"]).LogsFeature)

        self.assertTrue(hasattr(support_worker, "LogsSupportPrepareWorker"))
        worker_source = inspect.getsource(support_worker.LogsSupportPrepareWorker.run)

        self.assertIn("_request_support_prepare", handler_source)
        self.assertNotIn("prepare_support_bundle", handler_source)
        self.assertIn("create_support_prepare_worker", page_source)
        self.assertIn("_support_prepare_runtime", page_source)
        self.assertIn("create_support_prepare_worker", feature_source)
        self.assertIn("prepare_support_bundle=self.prepare_support_bundle", feature_source)
        self.assertIn("_prepare_support_bundle", worker_source)
        self.assertNotIn("log_commands", worker_source)
        self.assertIn("prepare_support_bundle", worker_source)

    def test_logs_open_folder_runs_through_worker(self) -> None:
        spec = importlib.util.find_spec("log.open_folder_worker")
        self.assertIsNotNone(spec)
        open_worker = importlib.import_module("log.open_folder_worker")
        page_source = inspect.getsource(LogsPage)
        handler_source = inspect.getsource(LogsPage._open_folder)
        feature_source = inspect.getsource(__import__("app.feature_facades.logs", fromlist=["LogsFeature"]).LogsFeature)

        self.assertTrue(hasattr(open_worker, "LogsOpenFolderWorker"))
        worker_source = inspect.getsource(open_worker.LogsOpenFolderWorker.run)

        self.assertIn("_request_open_logs_folder", handler_source)
        self.assertNotIn(".open_logs_folder(", handler_source)
        self.assertIn("create_open_folder_worker", page_source)
        self.assertIn("_open_folder_runtime", page_source)
        self.assertIn("create_open_folder_worker", feature_source)
        self.assertIn("open_logs_folder", worker_source)

    def test_profile_setup_page_loads_profile_payload_through_worker(self) -> None:
        source = inspect.getsource(ProfileSetupPageBase.reload_current_profile)

        self.assertNotIn("self._controller.load(", source)
        self.assertIn("_request_profile_setup_payload", source)

    def test_preset_selection_state_uses_profile_snapshot(self) -> None:
        source = inspect.getsource(preset_commands._profile_selection_details)

        self.assertNotIn(".list_profiles(", source)
        self.assertNotIn("get_profile_setup(", source)
        self.assertIn("get_profile_selection_details", source)


    def test_additional_settings_worker_uses_requested_launch_method(self) -> None:
        worker_init_source = inspect.getsource(profile_additional_settings_loader.AdditionalSettingsLoadWorker.__init__)
        worker_run_source = inspect.getsource(profile_additional_settings_loader.AdditionalSettingsLoadWorker.run)

        self.assertIn("state_loader", worker_init_source)
        self.assertIn("self._state_loader", worker_init_source)
        self.assertNotIn("self._profile", worker_init_source)
        self.assertNotIn("launch_method", worker_init_source)
        self.assertNotIn("self._launch_method", worker_init_source)
        self.assertIn("self._state_loader()", worker_run_source)
        self.assertNotIn("get_additional_settings_state", worker_run_source)
        self.assertNotIn("ZAPRET2_MODE", worker_run_source)
        factory_source = inspect.getsource(control_additional_settings_runtime.create_additional_settings_worker)
        self.assertIn("create_load_worker", factory_source)
        self.assertNotIn("profile_feature", factory_source)


    def test_defender_admin_check_runs_through_worker(self) -> None:
        defender_source = "\n".join(
            (
                inspect.getsource(windows_features_runtime.ControlPageWindowsFeatureMixin._on_defender_toggled),
                inspect.getsource(windows_features_runtime.ControlPageWindowsFeatureMixin._continue_defender_toggle),
            )
        )
        mixin_source = inspect.getsource(windows_features_runtime.ControlPageWindowsFeatureMixin)
        feature_source = inspect.getsource(__import__("app.feature_facades.program_settings", fromlist=["ProgramSettingsFeature"]).ProgramSettingsFeature)

        self.assertTrue(hasattr(program_settings_workers, "ProgramSettingsAdminCheckWorker"))
        worker_source = inspect.getsource(program_settings_workers.ProgramSettingsAdminCheckWorker.run)

        self.assertIn("_request_defender_admin_check", defender_source)
        self.assertNotIn("self._program_settings.is_user_admin", defender_source)
        self.assertIn("create_program_settings_admin_check_worker", mixin_source)
        self.assertIn("create_program_settings_admin_check_worker", feature_source)
        self.assertIn("is_user_admin", worker_source)


    def test_zapret2_control_initial_store_snapshot_is_applied_immediately(self) -> None:
        helper_source = inspect.getsource(control_page_shared.bind_control_ui_state_store)
        bind_source = inspect.getsource(Zapret2ModeControlPage.bind_ui_state_store)

        self.assertIn("emit_initial: bool = True", helper_source)
        self.assertIn("emit_initial=bool(emit_initial)", helper_source)
        self.assertNotIn("defer_initial_state", bind_source)
        self.assertNotIn("emit_initial=not defer_initial_state", bind_source)
        self.assertNotIn("_wait_for_startup_interactive_before_initial_ui_state", bind_source)

    def test_raw_preset_editor_loads_file_through_worker(self) -> None:
        source = inspect.getsource(PresetRawEditorPage._load_file)
        set_source = inspect.getsource(PresetRawEditorPage.set_preset_file_name)
        header_source = inspect.getsource(PresetRawEditorPage._refresh_header)
        worker_init_source = inspect.getsource(RawPresetLoadWorker.__init__)
        worker_source = inspect.getsource(RawPresetLoadWorker.run)

        self.assertNotIn("self._controller.load_text(", source)
        self.assertIn("_request_raw_preset_text", source)
        self.assertNotIn("self._controller.manifest", set_source)
        self.assertNotIn("self._controller.source_path", set_source)
        self.assertNotIn("self._controller.manifest", header_source)
        self.assertIn("load_preset", worker_init_source)
        self.assertIn("self._load_preset", worker_init_source)
        self.assertNotIn("self._controller", worker_init_source)
        self.assertIn("self._load_preset(self._file_name)", worker_source)
        self.assertNotIn("self._controller.load_preset", worker_source)

    def test_raw_preset_editor_saves_file_through_worker(self) -> None:
        from app.feature_facades.presets import PresetsFeature

        save_source = inspect.getsource(PresetRawEditorPage._save_file)
        feature_source = inspect.getsource(PresetsFeature.create_raw_preset_save_worker)
        worker_init_source = inspect.getsource(RawPresetSaveWorker.__init__)
        worker_source = inspect.getsource(RawPresetSaveWorker.run)

        self.assertNotIn("self._controller.save_text(", save_source)
        self.assertIn("_request_raw_preset_save", save_source)
        self.assertIn("RawPresetSaveWorker", feature_source)
        self.assertIn("save_text", worker_init_source)
        self.assertIn("self._save_text", worker_init_source)
        self.assertNotIn("controller", worker_init_source)
        self.assertIn("self._save_text(", worker_source)
        self.assertNotIn("controller.save_text", worker_source)

    def test_raw_preset_editor_waits_for_pending_save_before_file_actions(self) -> None:
        set_file_source = inspect.getsource(PresetRawEditorPage.set_preset_file_name)
        activate_source = inspect.getsource(PresetRawEditorPage._activate_preset)
        open_source = inspect.getsource(PresetRawEditorPage._open_external)
        rename_source = inspect.getsource(PresetRawEditorPage._rename_preset)
        duplicate_source = inspect.getsource(PresetRawEditorPage._duplicate_preset)
        export_source = inspect.getsource(PresetRawEditorPage._export_preset)
        reset_source = inspect.getsource(PresetRawEditorPage._reset_preset)
        delete_source = inspect.getsource(PresetRawEditorPage._delete_preset)
        save_finished_source = inspect.getsource(PresetRawEditorPage._on_raw_preset_save_worker_finished)

        for source in (
            set_file_source,
            activate_source,
            open_source,
            rename_source,
            duplicate_source,
            export_source,
            reset_source,
            delete_source,
        ):
            self.assertIn("_run_after_raw_preset_save", source)
        self.assertIn("_after_raw_preset_save", save_finished_source)
        self.assertIn("_raw_save_succeeded", save_finished_source)

    def test_raw_preset_write_finished_uses_queued_state_finish_guard(self) -> None:
        save_finished_source = inspect.getsource(PresetRawEditorPage._on_raw_preset_save_worker_finished)
        activate_finished_source = inspect.getsource(PresetRawEditorPage._on_preset_activation_worker_finished)
        action_finished_source = inspect.getsource(PresetRawEditorPage._on_raw_preset_action_worker_finished)
        helper_source = inspect.getsource(PresetRawEditorPage._schedule_next_raw_preset_write_operation_after_finish)

        self.assertIn("schedule_next_after_finish", helper_source)
        self.assertIn("_accept_current_raw_write_worker_finished", helper_source)
        for source in (save_finished_source, activate_finished_source, action_finished_source):
            self.assertIn("_schedule_next_raw_preset_write_operation_after_finish", source)
            self.assertNotIn("_schedule_next_raw_preset_write_operation_start()", source)

    def test_raw_preset_editor_activation_runs_through_worker(self) -> None:
        source = inspect.getsource(PresetRawEditorPage._activate_preset)
        request_source = inspect.getsource(PresetRawEditorPage._request_preset_activation)
        start_source = inspect.getsource(PresetRawEditorPage._start_preset_activation_worker)
        worker_init_source = inspect.getsource(RawPresetActivateWorker.__init__)
        worker_source = inspect.getsource(RawPresetActivateWorker.run)

        self.assertNotIn("_activate_selected_preset()", source)
        self.assertNotIn("self._controller.activate(", source)
        self.assertIn("_request_preset_activation", source)
        self.assertIn("create_raw_preset_activate_worker", request_source + start_source)
        self.assertIn("activate", worker_init_source)
        self.assertIn("self._activate", worker_init_source)
        self.assertNotIn("controller", worker_init_source)
        self.assertIn("self._activate(file_name=self._file_name)", worker_source)
        self.assertNotIn("controller.activate", worker_source)

    def test_raw_preset_editor_file_actions_run_through_worker(self) -> None:
        from app.feature_facades.presets import PresetsFeature

        action_sources = "\n".join(
            inspect.getsource(method)
            for method in (
                PresetRawEditorPage._open_external,
                PresetRawEditorPage._rename_preset,
                PresetRawEditorPage._duplicate_preset,
                PresetRawEditorPage._export_preset,
                PresetRawEditorPage._reset_preset,
                PresetRawEditorPage._delete_preset,
            )
        )
        feature_source = inspect.getsource(PresetsFeature.create_raw_preset_action_worker)
        worker_init_source = inspect.getsource(RawPresetActionWorker.__init__)
        worker_source = inspect.getsource(RawPresetActionWorker.run)

        for call in (
            "self._controller.open_source_file(",
            "self._controller.rename(",
            "self._controller.duplicate(",
            "self._controller.export(",
            "self._controller.reset_to_builtin(",
            "self._controller.delete(",
        ):
            self.assertNotIn(call, action_sources)
        self.assertIn("_request_raw_preset_action", action_sources)
        self.assertIn("RawPresetActionWorker", feature_source)
        self.assertIn("open_source_file", worker_init_source)
        self.assertIn("rename_preset", worker_init_source)
        self.assertIn("duplicate_preset", worker_init_source)
        self.assertIn("export_preset", worker_init_source)
        self.assertIn("reset_to_builtin", worker_init_source)
        self.assertIn("delete_preset", worker_init_source)
        self.assertIn("source_path", worker_init_source)
        self.assertNotIn("run_action", worker_init_source)
        self.assertNotIn("controller", worker_init_source)
        self.assertIn("self._rename_preset(", worker_source)
        self.assertIn("self._duplicate_preset(", worker_source)
        self.assertIn("self._export_preset(", worker_source)
        self.assertIn("self._reset_to_builtin(", worker_source)
        self.assertIn("self._delete_preset(", worker_source)
        self.assertIn("self._source_path(", worker_source)
        self.assertNotIn("self._run_action", worker_source)
        self.assertNotIn("controller.rename", worker_source)
        self.assertNotIn("controller.duplicate", worker_source)
        self.assertNotIn("controller.export", worker_source)
        self.assertNotIn("controller.reset_to_builtin", worker_source)
        self.assertNotIn("controller.delete", worker_source)

    def test_profile_setup_builds_hidden_tabs_lazily(self) -> None:
        build_source = inspect.getsource(ProfileSetupPageBase._build_content)
        switch_source = inspect.getsource(ProfileSetupPageBase._switch_strategy_tab)
        apply_source = inspect.getsource(ProfileSetupPageBase._apply_payload)

        self.assertNotIn("self._list_file_text = PlainTextEdit()", build_source)
        self.assertNotIn("self._raw_profile_text = PlainTextEdit()", build_source)
        self.assertIn("_ensure_editor_tab_built()", switch_source)
        self.assertIn("_request_list_file_editor_state()", switch_source)
        self.assertNotIn("_apply_list_file_editor_state", apply_source)


    def test_page_host_logs_first_and_repeat_show_for_all_pages(self) -> None:
        init_source = inspect.getsource(WindowPageHost.__init__)
        show_source = inspect.getsource(WindowPageHost.show_page)
        ensure_source = inspect.getsource(WindowPageHost.ensure_page)

        self.assertIn("_shown_pages", init_source)
        self.assertIn("open.navigation.first", show_source)
        self.assertIn("open.navigation.repeat", show_source)
        self.assertIn("log_page_timing", show_source)
        self.assertIn("open.ensure_page", show_source)
        self.assertIn("open.stack", show_source)
        self.assertIn("open.switch", show_source)
        self.assertIn("open.navigation_sync", show_source)
        self.assertNotIn("animate=", show_source)
        self.assertIn("ensure.cached.language", ensure_source)
        self.assertIn("ensure.created.language", ensure_source)

    def test_page_host_repeat_show_budget_allows_animated_navigation(self) -> None:
        self.assertEqual(
            WindowPageHost._show_budget_ms(
                PageName.ZAPRET2_USER_PRESETS,
                first_show=False,
                use_nav_route=True,
            ),
            120,
        )
        self.assertEqual(
            WindowPageHost._show_budget_ms(
                PageName.ZAPRET2_USER_PRESETS,
                first_show=False,
                use_nav_route=False,
            ),
            40,
        )

    def test_page_host_never_disables_qfluent_animation(self) -> None:
        page = object()

        class _FakeStack:
            def __init__(self) -> None:
                self.isAnimationEnabled = True
                self.animation_seen_during_switch = None

        class _FakeWindow:
            def __init__(self) -> None:
                self.stackedWidget = _FakeStack()

            def switchTo(self, target):  # noqa: N802
                self.target = target
                self.stackedWidget.animation_seen_during_switch = self.stackedWidget.isAnimationEnabled

        window = _FakeWindow()
        host = WindowPageHost(window=window, page_factory=None)

        self.assertTrue(host.set_stacked_widget_current_page(page))
        self.assertIs(window.target, page)
        self.assertTrue(window.stackedWidget.animation_seen_during_switch)
        self.assertTrue(window.stackedWidget.isAnimationEnabled)
        switch_source = inspect.getsource(WindowPageHost.set_stacked_widget_current_page)
        self.assertNotIn("isAnimationEnabled", switch_source)
        self.assertNotIn("setCurrentWidget", switch_source)

    def test_page_host_uses_qfluent_animation_for_navigation_switch(self) -> None:
        page = object()

        class _FakeStack:
            def setCurrentWidget(self, _page, _need_pop_out=False):  # noqa: N802
                raise AssertionError("animated navigation must use window.switchTo")

        class _FakeWindow:
            def __init__(self) -> None:
                self.stackedWidget = _FakeStack()
                self.switched_to = None

            def switchTo(self, target):  # noqa: N802
                self.switched_to = target

        window = _FakeWindow()
        host = WindowPageHost(window=window, page_factory=None)

        self.assertTrue(host.set_stacked_widget_current_page(page))
        self.assertIs(window.switched_to, page)

    def test_page_host_does_not_switch_stack_when_page_is_already_current(self) -> None:
        page = object()

        class _FakeStack:
            def __init__(self) -> None:
                self.switch_count = 0

            def currentWidget(self):  # noqa: N802
                return page

            def setCurrentWidget(self, _page, _need_pop_out=False):  # noqa: N802
                self.switch_count += 1

        class _FakeWindow:
            def __init__(self) -> None:
                self.stackedWidget = _FakeStack()

            def get_launch_method(self) -> str:
                return "zapret2_mode"

        window = _FakeWindow()
        host = WindowPageHost(window=window, page_factory=None)
        host.pages[PageName.ZAPRET2_USER_PRESETS] = page
        host._shown_pages.add(PageName.ZAPRET2_USER_PRESETS)

        with patch("ui.page_host.apply_ui_language_to_page"):
            self.assertTrue(host.show_page(PageName.ZAPRET2_USER_PRESETS, allow_internal=True))

        self.assertEqual(window.stackedWidget.switch_count, 0)

    def test_page_host_keeps_stack_repaint_enabled_during_direct_switch(self) -> None:
        class _FakeStack:
            def __init__(self) -> None:
                self.updates_enabled = True
                self.updates_seen_during_switch = None
                self.calls: list[tuple[str, bool | None]] = []

            def setUpdatesEnabled(self, enabled):  # noqa: N802
                self.updates_enabled = bool(enabled)
                self.calls.append(("updates", self.updates_enabled))

            def setCurrentWidget(self, page, need_pop_out=False):
                _ = page
                _ = need_pop_out
                self.updates_seen_during_switch = self.updates_enabled
                self.calls.append(("switch", self.updates_seen_during_switch))

            def update(self):
                self.calls.append(("update", None))

        class _FakeWindow:
            def __init__(self) -> None:
                self.stackedWidget = _FakeStack()

            def switchTo(self, page):  # noqa: N802
                self.stackedWidget.setCurrentWidget(page, False)

        window = _FakeWindow()
        host = WindowPageHost(window=window, page_factory=None)
        self.assertTrue(host.set_stacked_widget_current_page(object()))

        self.assertTrue(window.stackedWidget.updates_seen_during_switch)
        self.assertTrue(window.stackedWidget.updates_enabled)
        self.assertEqual(
            window.stackedWidget.calls,
            [
                ("switch", True),
            ],
        )

    def test_page_host_logs_slow_direct_switch_substeps(self) -> None:
        class _FakeStack:
            def __init__(self) -> None:
                self.updates_enabled = True

            def setUpdatesEnabled(self, enabled):  # noqa: N802
                self.updates_enabled = bool(enabled)

            def updatesEnabled(self):  # noqa: N802
                return self.updates_enabled

            def setCurrentWidget(self, page, need_pop_out=False):
                _ = page
                _ = need_pop_out
                time.sleep(0.02)

            def update(self):
                pass

        class _FakeWindow:
            def __init__(self) -> None:
                self.stackedWidget = _FakeStack()

            def switchTo(self, page):  # noqa: N802
                self.stackedWidget.setCurrentWidget(page, False)

        host = WindowPageHost(window=_FakeWindow(), page_factory=None)
        events: list[str] = []

        with patch("ui.page_host.log_page_timing", side_effect=lambda _page, stage, *_args, **_kwargs: events.append(stage)):
            self.assertTrue(
                host.set_stacked_widget_current_page(
                    object(),
                    page_name=PageName.ZAPRET2_USER_PRESETS,
                )
            )

        self.assertIn("open.switch.qfluent", events)

    def test_telegram_proxy_builds_secondary_tabs_lazily(self) -> None:
        setup_source = inspect.getsource(TelegramProxyPage._setup_ui)
        after_source = inspect.getsource(TelegramProxyPage._after_ui_built)
        switch_source = inspect.getsource(TelegramProxyPage._switch_tab)
        timer_source = inspect.getsource(TelegramProxyPage._sync_log_timer)

        self.assertIn("_built_panel_indexes", setup_source)
        self.assertNotIn("build_telegram_proxy_logs_panel(", setup_source)
        self.assertNotIn("build_telegram_proxy_diag_panel(", setup_source)
        self.assertNotIn("_log_timer.start", after_source)
        self.assertIn("_ensure_panel_built(index)", switch_source)
        self.assertIn("self._stacked.currentIndex() == 1", timer_source)

    def test_telegram_proxy_advanced_settings_live_on_nested_page(self) -> None:
        from telegram_proxy.ui import advanced_build
        from telegram_proxy.ui.advanced_page import TelegramProxyAdvancedPage

        page_source = inspect.getsource(TelegramProxyPage)
        settings_build_source = inspect.getsource(telegram_proxy_settings_build)
        advanced_init_source = inspect.getsource(TelegramProxyAdvancedPage.__init__)
        activated_source = inspect.getsource(TelegramProxyAdvancedPage.on_page_activated)

        self.assertNotIn("advanced_build", page_source)
        self.assertNotIn("cloudflare", settings_build_source.lower())
        self.assertIn("build_telegram_proxy_advanced_panel", inspect.getsource(TelegramProxyAdvancedPage))
        self.assertIn("SettingCardGroup(text.upstream_group_title", inspect.getsource(advanced_build))
        # Настройки читаются не в конструкторе, а при открытии страницы и в фоне.
        self.assertNotIn("_request_state_reload", advanced_init_source)
        self.assertIn("_request_state_reload", activated_source)

    def test_user_presets_hide_keeps_clean_cache_clean(self) -> None:
        source = inspect.getsource(UserPresetsPageBase.on_page_hidden)

        self.assertNotIn("stop_watching_presets", source)


    def test_hosts_page_file_work_runs_through_feature_workers(self) -> None:
        from hosts.ui.file_page import HostsFilePage

        page_source = inspect.getsource(HostsPage)
        file_page_source = inspect.getsource(HostsFilePage)

        for factory in (
            "self._hosts.create_snapshot_worker",
            "self._hosts.create_apply_worker",
            "self._hosts.create_permission_restore_worker",
        ):
            self.assertIn(factory, page_source)
        for factory in (
            "self._hosts.create_file_text_worker",
            "self._hosts.create_file_save_worker",
            "self._hosts.create_open_hosts_file_worker",
        ):
            self.assertIn(factory, file_page_source)
        for source in (page_source, file_page_source):
            self.assertNotIn("hosts.commands", source)
            self.assertNotIn("safe_read_hosts_file", source)
            self.assertNotIn("safe_write_hosts_file", source)
        self.assertIn("open_hosts_file", inspect.getsource(hosts_commands.open_hosts_file))

    def test_hosts_restore_permissions_runs_through_worker(self) -> None:
        # Отдельный permission_restore_worker.py ушёл вместе со старой
        # страницей hosts: теперь любой вызов фасада hosts идёт через общий
        # HostsCallWorker (QThread). Смысл проверки прежний — восстановление
        # прав не выполняется в GUI-потоке и не зовёт hosts.commands напрямую.
        from PyQt6.QtCore import QThread

        from app.feature_facades import hosts as hosts_feature_module
        from hosts.call_worker import HostsCallWorker

        restore_source = inspect.getsource(HostsPage._restore_permissions)
        facade_source = inspect.getsource(hosts_feature_module.build_hosts_feature)

        self.assertIn("start_qthread_worker", restore_source)
        self.assertIn("self._hosts.create_permission_restore_worker", restore_source)
        self.assertNotIn("restore_hosts_permissions(", restore_source)
        self.assertNotIn("hosts.commands", restore_source)
        self.assertIn("restore_hosts_permissions()", facade_source)
        self.assertTrue(issubclass(HostsCallWorker, QThread))
        self.assertIn("self._call()", inspect.getsource(HostsCallWorker.run))
        self.assertIn("restore_hosts_permissions", inspect.getsource(hosts_commands.restore_hosts_permissions))


    def test_dns_isp_warning_settings_access_runs_through_worker(self) -> None:
        dns_workers = importlib.import_module("dns.page_workers")
        dns_feature_module = importlib.import_module("app.feature_facades.dns")

        page_source = inspect.getsource(dns_page.NetworkPage)
        feature_source = inspect.getsource(dns_feature_module.DnsFeature)

        self.assertTrue(hasattr(dns_workers, "DnsIspWarningWorker"))
        worker_source = inspect.getsource(dns_workers.DnsIspWarningWorker.run)
        self.assertIn("self._isp_lane.request()", page_source)
        self.assertIn("create_isp_dns_warning_worker", page_source)
        self.assertNotIn("self._dns.is_isp_dns_warning_shown", page_source)
        self.assertNotIn("self._dns.mark_isp_dns_warning_shown", page_source)
        self.assertIn("LatestWorkerLane", page_source)
        self.assertIn("create_isp_dns_warning_worker", feature_source)
        self.assertIn("is_isp_dns_warning_shown", worker_source)
        self.assertIn("mark_isp_dns_warning_shown", worker_source)


    def test_network_and_telegram_ui_do_not_create_python_threads(self) -> None:
        modules = (
            dns_page,
            telegram_diag_workflow,
            telegram_runtime_workflow,
            telegram_page,
        )

        for module in modules:
            source = inspect.getsource(module)
            self.assertNotIn("threading.Thread", source)

    def test_dns_page_worker_returns_state_instead_of_calling_page_method(self) -> None:
        feature_source = inspect.getsource(__import__("app.feature_facades.dns", fromlist=["build_dns_feature"]).build_dns_feature)
        page_source = inspect.getsource(dns_page.NetworkPage)
        init_source = inspect.getsource(dns_page.NetworkPage._run_runtime_init_once)
        worker_source = inspect.getsource(DnsPageLoadWorker)

        self.assertIn("create_page_load_worker", feature_source)
        self.assertIn("create_page_load_worker", page_source)
        self.assertIn('result_signal="loaded"', page_source)
        self.assertIn("self._load_lane.request()", init_source)
        self.assertIn("loaded = pyqtSignal", worker_source)
        self.assertIn("self.loaded.emit", worker_source)
        self.assertNotIn("load_page_data", page_source)

    def test_dns_page_has_no_force_dns_worker(self) -> None:
        page_workers = importlib.import_module("dns.page_workers")
        feature_source = inspect.getsource(__import__("app.feature_facades.dns", fromlist=["DnsFeature"]).DnsFeature)
        page_source = inspect.getsource(dns_page.NetworkPage)

        self.assertFalse(hasattr(page_workers, "DnsForceDnsActionWorker"))
        self.assertFalse(hasattr(page_workers, "DnsConnectivityTestWorker"))
        self.assertNotIn("create_force_dns_action_worker", feature_source)
        self.assertNotIn("force_dns_action", page_source)
        self.assertNotIn("_force_dns_active", page_source)

    def test_dns_flush_cache_runs_through_worker(self) -> None:
        page_workers = importlib.import_module("dns.page_workers")
        feature_source = inspect.getsource(__import__("app.feature_facades.dns", fromlist=["DnsFeature"]).DnsFeature)
        page_source = inspect.getsource(dns_page.NetworkPage)
        flush_source = inspect.getsource(dns_page.NetworkPage._flush_cache)

        self.assertTrue(hasattr(page_workers, "DnsFlushCacheWorker"))
        worker_source = inspect.getsource(page_workers.DnsFlushCacheWorker)

        self.assertIn("self._flush_lane.request()", flush_source)
        self.assertNotIn(".flush_dns_cache(", flush_source)
        self.assertIn("create_dns_flush_cache_worker", feature_source)
        self.assertIn("create_dns_flush_cache_worker", page_source)
        self.assertIn("_flush_dns_cache", worker_source)
        self.assertNotIn("dns_public.flush_dns_cache", worker_source)
        self.assertIn("build_flush_dns_cache_result_plan", worker_source)

    def test_dns_apply_actions_run_through_worker(self) -> None:
        page_workers = importlib.import_module("dns.page_workers")
        feature_source = inspect.getsource(__import__("app.feature_facades.dns", fromlist=["DnsFeature"]).DnsFeature)
        page_source = inspect.getsource(dns_page.NetworkPage)

        self.assertTrue(hasattr(page_workers, "DnsApplyWorker"))
        worker_source = inspect.getsource(page_workers.DnsApplyWorker)

        for method_name in ("_choose_provider", "_confirm_reset_to_auto"):
            source = inspect.getsource(getattr(dns_page.NetworkPage, method_name))
            self.assertIn("self._apply_lane.request(", source)
            self.assertNotIn(".apply_auto_dns(", source)
            self.assertNotIn(".apply_provider_dns(", source)

        self.assertIn("create_dns_apply_worker", feature_source)
        self.assertIn("create_dns_apply_worker", page_source)
        self.assertIn("self._apply_dns(", worker_source)
        self.assertIn("self._reset_to_auto(", worker_source)
        self.assertNotIn("apply_custom_dns", worker_source)
        self.assertIn("self._load_state()", worker_source)
        self.assertIsNone(importlib.util.find_spec("dns.page_apply_workflow"))
        self.assertIsNone(importlib.util.find_spec("dns.page_force_dns_workflow"))

    def test_network_page_builds_dns_choices_before_runtime_load(self) -> None:
        init_source = inspect.getsource(dns_page.NetworkPage.__init__)
        build_source = inspect.getsource(dns_page.NetworkPage._build_ui)

        self.assertIn("self.grid = DnsProviderGrid(self.content)", build_source)
        self.assertLess(init_source.index("self._build_ui()"), init_source.index("self._render()"))
        self.assertNotIn("self._load_lane.request()", init_source)
        self.assertNotIn("refresh_dns_info", build_source)

    def test_telegram_diagnostics_worker_uses_progress_signal(self) -> None:
        workflow_source = inspect.getsource(telegram_diag_workflow.start_diagnostics)
        page_source = inspect.getsource(TelegramProxyPage)
        worker_source = inspect.getsource(TelegramProxyDiagnosticsWorker)

        self.assertNotIn("progress_callback=publish_diag_result", workflow_source)
        self.assertIn("worker.progress.connect(publish_diag_result)", workflow_source)
        self.assertIn("progress = pyqtSignal", worker_source)
        self.assertIn("progress_callback=self.progress.emit", worker_source)
        self.assertIn("_diag_runtime", page_source)
        self.assertIn("start_qthread_worker", workflow_source)
        self.assertNotIn("_diag_worker", page_source)
        self.assertNotIn("worker.start()", workflow_source)


if __name__ == "__main__":
    unittest.main()
