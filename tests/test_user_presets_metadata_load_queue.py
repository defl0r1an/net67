from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication


class _Signal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _MetadataWorker:
    instances = []

    def __init__(self, request_id, load_all_metadata, load_folder_state, page) -> None:
        self.request_id = request_id
        self.load_all_metadata = load_all_metadata
        self.load_folder_state = load_folder_state
        self.page = page
        self.loaded = _Signal()
        self.failed = _Signal()
        self.finished = _Signal()
        self.start_calls = 0
        self.delete_later_calls = 0
        self._running = False
        self.__class__.instances.append(self)

    def isRunning(self) -> bool:  # noqa: N802
        return self._running

    def start(self) -> None:
        self.start_calls += 1
        self._running = True

    def deleteLater(self) -> None:  # noqa: N802
        self.delete_later_calls += 1
        self._running = False


class _SingleMetadataWorker:
    instances = []

    def __init__(self, request_id, file_name, read_single_metadata, page) -> None:
        self.request_id = request_id
        self.file_name = file_name
        self.read_single_metadata = read_single_metadata
        self.page = page
        self.loaded = _Signal()
        self.failed = _Signal()
        self.finished = _Signal()
        self.start_calls = 0
        self._running = False
        self.__class__.instances.append(self)

    def isRunning(self) -> bool:  # noqa: N802
        return self._running

    def start(self) -> None:
        self.start_calls += 1
        self._running = True

    def deleteLater(self) -> None:  # noqa: N802
        self._running = False


class _RowsPlanWorker:
    instances = []

    def __init__(
        self,
        request_id,
        build_rows_plan,
        *,
        all_presets,
        query,
        selected_source_file_name,
        language,
        folder_state,
        started_at,
        parent,
    ) -> None:
        self.request_id = request_id
        self.build_rows_plan = build_rows_plan
        self.all_presets = all_presets
        self.query = query
        self.selected_source_file_name = selected_source_file_name
        self.language = language
        self.folder_state = folder_state
        self.started_at = started_at
        self.parent = parent
        self.loaded = _Signal()
        self.failed = _Signal()
        self.finished = _Signal()
        self.start_calls = 0
        self._running = False
        self.__class__.instances.append(self)

    def isRunning(self) -> bool:  # noqa: N802
        return self._running

    def start(self) -> None:
        self.start_calls += 1
        self._running = True

    def deleteLater(self) -> None:  # noqa: N802
        self._running = False


class _Watcher:
    def __init__(self, files=()) -> None:
        self._files = set(files or ())
        self.add_calls: list[list[str]] = []
        self.remove_calls: list[list[str]] = []

    def files(self):
        return sorted(self._files)

    def addPaths(self, paths):  # noqa: N802
        normalized = [str(path) for path in paths]
        self.add_calls.append(normalized)
        self._files.update(normalized)

    def removePaths(self, paths):  # noqa: N802
        normalized = [str(path) for path in paths]
        self.remove_calls.append(normalized)
        for path in normalized:
            self._files.discard(path)


class UserPresetsMetadataLoadQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        _MetadataWorker.instances.clear()
        _SingleMetadataWorker.instances.clear()
        _RowsPlanWorker.instances.clear()

    def test_single_metadata_queue_state_lives_in_queued_worker_state(self) -> None:
        import inspect
        from presets.user_presets_runtime_service import UserPresetsRuntimeService
        from ui.queued_worker_state import QueuedWorkerState

        service = UserPresetsRuntimeService()
        module_source = inspect.getsource(
            __import__("presets.user_presets_runtime_service", fromlist=[""])
        )
        init_source = inspect.getsource(UserPresetsRuntimeService.__init__)
        request_source = inspect.getsource(UserPresetsRuntimeService._request_single_metadata_refresh)
        finished_source = inspect.getsource(UserPresetsRuntimeService._on_single_metadata_worker_finished)
        run_scheduled_source = inspect.getsource(UserPresetsRuntimeService._run_scheduled_single_metadata_refresh)

        self.assertIsInstance(service._single_metadata_state_obj(), QueuedWorkerState)
        self.assertIn("from ui.queued_worker_state import QueuedWorkerState", module_source)
        self.assertIn("_single_metadata_state = QueuedWorkerState", init_source)
        self.assertIn("_single_metadata_state_obj()", request_source)
        self.assertIn("schedule_next_after_finish", finished_source)
        self.assertIn("state.pop_next()", run_scheduled_source)

    def test_full_metadata_load_replays_latest_request_after_running_worker_finishes(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)

        scheduled_callbacks = []

        with patch(
            "presets.user_presets_runtime_service.UserPresetsMetadataLoadWorker",
            _MetadataWorker,
        ), patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            side_effect=lambda _delay, callback: scheduled_callbacks.append(callback),
        ):
            service.load_presets(page)
            service.load_presets(page)

            self.assertEqual(len(_MetadataWorker.instances), 1)

            service._metadata_load_runtime.worker = None
            service._on_metadata_worker_finished(_MetadataWorker.instances[0])

            self.assertEqual(len(_MetadataWorker.instances), 1)
            self.assertEqual(len(scheduled_callbacks), 1)
            scheduled_callbacks[0]()

        self.assertEqual(len(_MetadataWorker.instances), 2)
        self.assertEqual(_MetadataWorker.instances[1].request_id, 2)
        self.assertEqual(_MetadataWorker.instances[1].start_calls, 1)

    def test_full_metadata_scheduled_restart_waits_for_event_loop_callback(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        scheduled_callbacks = []

        with patch(
            "presets.user_presets_runtime_service.UserPresetsMetadataLoadWorker",
            _MetadataWorker,
        ), patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            side_effect=lambda _delay, callback: scheduled_callbacks.append(callback),
        ):
            service.load_presets(page)
            service.load_presets(page)
            service._metadata_load_runtime.worker = None
            service._on_metadata_worker_finished(_MetadataWorker.instances[0])
            service.load_presets(page)

            self.assertEqual(len(_MetadataWorker.instances), 1)
            self.assertEqual(len(scheduled_callbacks), 1)

            scheduled_callbacks[0]()

        self.assertEqual(len(_MetadataWorker.instances), 2)
        self.assertEqual(_MetadataWorker.instances[1].start_calls, 1)

    def test_stale_full_metadata_worker_finish_does_not_restart_pending_load(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._metadata_load_request_id = 2
        service._metadata_load_pending_page = page
        service._schedule_metadata_load = Mock()

        service._on_metadata_worker_finished(SimpleNamespace(_request_id=1))

        service._schedule_metadata_load.assert_not_called()
        self.assertIs(service._metadata_load_pending_page, page)

    def test_stale_full_metadata_worker_object_finish_does_not_restart_pending_load(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._metadata_load_runtime.worker = object()
        service._metadata_load_pending_page = page
        service._schedule_metadata_load = Mock()

        service._on_metadata_worker_finished(object())

        service._schedule_metadata_load.assert_not_called()
        self.assertIs(service._metadata_load_pending_page, page)

    def test_duplicate_single_metadata_update_skips_visible_refresh(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        metadata = {
            "display_name": "Default",
            "description": "",
            "modified_display": "today",
        }
        service._single_metadata_request_id = 3
        service._cached_presets_metadata = {"Default.txt": dict(metadata)}
        service.try_apply_single_preset_metadata_update = Mock(
            side_effect=AssertionError("duplicate metadata must not repaint preset row")
        )
        service.refresh_presets_view_from_cache = Mock(
            side_effect=AssertionError("duplicate metadata must not refresh preset list")
        )

        service._on_single_metadata_loaded(3, "Default.txt", ("Default.txt", dict(metadata)), page)

        self.assertEqual(service._cached_presets_metadata, {"Default.txt": metadata})

    def test_single_metadata_result_ignored_when_same_file_is_pending(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._single_metadata_request_id = 3
        service._single_metadata_pending = ["Default.txt"]
        service._cached_presets_metadata = {"Default.txt": {"display_name": "Old"}}
        service.try_apply_single_preset_metadata_update = Mock()
        service.refresh_presets_view_from_cache = Mock()

        service._on_single_metadata_loaded(
            3,
            "Default.txt",
            ("Default.txt", {"display_name": "New"}),
            page,
        )

        self.assertEqual(service._cached_presets_metadata, {"Default.txt": {"display_name": "Old"}})
        service.try_apply_single_preset_metadata_update.assert_not_called()
        service.refresh_presets_view_from_cache.assert_not_called()

    def test_single_metadata_error_ignored_when_same_file_is_pending(self) -> None:
        import presets.user_presets_runtime_service as runtime_service
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._single_metadata_request_id = 3
        service._single_metadata_pending = ["Default.txt"]
        service._ui_dirty = False
        service.schedule_presets_reload = Mock()

        with patch.object(runtime_service, "log") as log_mock:
            service._on_single_metadata_failed(3, "Default.txt", "stale error", page)

        self.assertFalse(service._ui_dirty)
        service.schedule_presets_reload.assert_not_called()
        log_mock.assert_not_called()

    def test_store_switch_defers_dirty_list_reload_after_local_active_marker_update(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        page.refresh_presets_view_if_possible = Mock(
            side_effect=AssertionError("preset switch must not rebuild the list inline")
        )
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "Next.txt",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._ui_dirty = True
        service.apply_active_preset_marker_for_file = Mock(return_value=True)
        service.schedule_presets_reload = Mock()

        service.on_store_switched("Next.txt", page)

        service.apply_active_preset_marker_for_file.assert_called_once_with("Next.txt", page=page)
        page.refresh_presets_view_if_possible.assert_not_called()
        service.schedule_presets_reload.assert_called_once_with(page)

    def test_store_switch_defers_dirty_list_reload_after_optimistic_marker(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        page.refresh_presets_view_if_possible = Mock(
            side_effect=AssertionError("preset switch must not rebuild the list inline")
        )
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "Next.txt",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._ui_dirty = True
        service.apply_active_preset_marker_for_file = Mock(return_value=False)
        service.schedule_presets_reload = Mock()

        service.on_store_switched("Next.txt", page)

        service.apply_active_preset_marker_for_file.assert_called_once_with("Next.txt", page=page)
        page.refresh_presets_view_if_possible.assert_not_called()
        service.schedule_presets_reload.assert_called_once_with(page)

    def test_active_preset_marker_defers_current_index_until_next_qt_tick(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeService

        class _Index:
            def __init__(self, row: int) -> None:
                self.row = row

            def isValid(self) -> bool:  # noqa: N802
                return self.row >= 0

            def __eq__(self, other) -> bool:
                return isinstance(other, _Index) and self.row == other.row

        class _Model:
            def __init__(self) -> None:
                self.active_names: list[str] = []

            def set_active_preset(self, file_name: str) -> bool:
                self.active_names.append(file_name)
                return True

            def find_preset_row(self, file_name: str) -> int:
                return {"First.txt": 1, "Second.txt": 2}.get(file_name, -1)

            def index(self, row: int, _column: int):
                return _Index(row)

        class _List:
            def __init__(self) -> None:
                self.current = _Index(-1)
                self.set_indexes: list[int] = []

            def currentIndex(self):  # noqa: N802
                return self.current

            def setCurrentIndex(self, index):  # noqa: N802
                self.current = index
                self.set_indexes.append(index.row)

        model = _Model()
        presets_list = _List()
        page = SimpleNamespace(_presets_model=model, presets_list=presets_list)
        service = UserPresetsRuntimeService()
        scheduled: list[tuple[int, object]] = []

        with patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            side_effect=lambda delay, callback: scheduled.append((delay, callback)),
        ):
            self.assertTrue(service.apply_active_preset_marker_for_file("First.txt", page=page))
            self.assertTrue(service.apply_active_preset_marker_for_file("Second.txt", page=page))

        self.assertEqual(model.active_names, ["First.txt", "Second.txt"])
        self.assertEqual(presets_list.set_indexes, [])
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], 0)

        scheduled[0][1]()

        self.assertEqual(presets_list.set_indexes, [2])

    def test_metadata_loaded_resets_dir_snapshot_before_rows_request(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._metadata_load_request_id = 7
        service._user_dir_snapshot = {"Stale.txt": (1, 1)}
        service._request_rows_plan_refresh = Mock()

        service._on_metadata_loaded(7, {"Default.txt": {}}, {}, 0.0, page)

        self.assertIsNone(service._user_dir_snapshot)
        service._request_rows_plan_refresh.assert_called_once()

    def test_metadata_load_result_ignored_when_new_load_is_pending(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._metadata_load_request_id = 7
        service._metadata_load_pending_page = page
        service._cached_presets_metadata = {"Old.txt": {}}
        service._cached_folder_state = {"items": {"Old.txt": {}}}
        service._request_rows_plan_refresh = Mock()

        service._on_metadata_loaded(7, {"New.txt": {}}, {"items": {"New.txt": {}}}, 1.5, page)

        self.assertEqual(service._cached_presets_metadata, {"Old.txt": {}})
        self.assertEqual(service._cached_folder_state, {"items": {"Old.txt": {}}})
        service._request_rows_plan_refresh.assert_not_called()

    def test_metadata_load_error_ignored_when_new_load_is_pending(self) -> None:
        import presets.user_presets_runtime_service as runtime_service
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._metadata_load_request_id = 7
        service._metadata_load_pending_page = page
        service._ui_dirty = False

        with patch.object(runtime_service, "log") as log_mock:
            service._on_metadata_failed(7, "stale error", page)

        self.assertFalse(service._ui_dirty)
        log_mock.assert_not_called()

    def test_single_metadata_pending_refresh_restarts_after_worker_signal_returns(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        worker = SimpleNamespace(deleteLater=Mock())
        service._single_metadata_worker = worker
        service._single_metadata_pending = ["Default.txt"]
        service._request_single_metadata_refresh = Mock()
        scheduled_callbacks = []

        with patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            side_effect=lambda _delay, callback: scheduled_callbacks.append(callback),
        ):
            service._on_single_metadata_worker_finished(worker, page)

        service._request_single_metadata_refresh.assert_not_called()
        self.assertEqual(len(scheduled_callbacks), 1)

        scheduled_callbacks[0]()

        service._request_single_metadata_refresh.assert_called_once_with("Default.txt", page)

    def test_stale_single_metadata_worker_finish_does_not_restart_pending_refresh(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._single_metadata_request_id = 2
        service._single_metadata_pending = ["Default.txt"]
        service._request_single_metadata_refresh = Mock()
        single_shot = Mock()

        with patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            single_shot,
        ):
            service._on_single_metadata_worker_finished(SimpleNamespace(_request_id=1), page)

        single_shot.assert_not_called()
        service._request_single_metadata_refresh.assert_not_called()
        self.assertEqual(service._single_metadata_pending, ["Default.txt"])

    def test_stale_single_metadata_worker_object_finish_does_not_restart_pending_refresh(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._single_metadata_runtime.worker = object()
        service._single_metadata_pending = ["Default.txt"]
        service._request_single_metadata_refresh = Mock()
        single_shot = Mock()

        with patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            single_shot,
        ):
            service._on_single_metadata_worker_finished(object(), page)

        single_shot.assert_not_called()
        service._request_single_metadata_refresh.assert_not_called()
        self.assertEqual(service._single_metadata_pending, ["Default.txt"])

    def test_single_metadata_scheduled_restart_queues_next_file_without_immediate_worker(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        worker = SimpleNamespace(deleteLater=Mock())
        service._single_metadata_worker = worker
        service._single_metadata_pending = ["First.txt"]
        scheduled_callbacks = []

        with patch(
            "presets.user_presets_runtime_service.UserPresetsSingleMetadataWorker",
            _SingleMetadataWorker,
        ), patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            side_effect=lambda _delay, callback: scheduled_callbacks.append(callback),
        ):
            service._on_single_metadata_worker_finished(worker, page)
            service._request_single_metadata_refresh("Second.txt", page)

            self.assertEqual(_SingleMetadataWorker.instances, [])
            self.assertEqual(service._single_metadata_pending, ["Second.txt"])

            scheduled_callbacks[0]()

        self.assertEqual([worker.file_name for worker in _SingleMetadataWorker.instances], ["First.txt"])
        self.assertEqual(service._single_metadata_pending, ["Second.txt"])

    def test_rows_plan_pending_refresh_restarts_after_worker_signal_returns(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        worker = SimpleNamespace(deleteLater=Mock())
        service._rows_plan_worker = worker
        service._rows_plan_pending = ({"Default.txt": {}}, {"items": {}}, 1.5, page)
        service._request_rows_plan_refresh = Mock()
        scheduled_callbacks = []

        with patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            side_effect=lambda _delay, callback: scheduled_callbacks.append(callback),
        ):
            service._on_rows_plan_worker_finished(worker)

        service._request_rows_plan_refresh.assert_not_called()
        self.assertEqual(len(scheduled_callbacks), 1)

        scheduled_callbacks[0]()

        service._request_rows_plan_refresh.assert_called_once_with({"Default.txt": {}}, {"items": {}}, 1.5, page)

    def test_stale_rows_plan_worker_finish_does_not_restart_pending_refresh(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._rows_plan_request_id = 2
        service._rows_plan_pending = ({"Default.txt": {}}, {"items": {}}, 1.5, page)
        service._request_rows_plan_refresh = Mock()
        single_shot = Mock()

        with patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            single_shot,
        ):
            service._on_rows_plan_worker_finished(SimpleNamespace(_request_id=1))

        single_shot.assert_not_called()
        service._request_rows_plan_refresh.assert_not_called()
        self.assertEqual(service._rows_plan_pending, ({"Default.txt": {}}, {"items": {}}, 1.5, page))

    def test_stale_rows_plan_worker_object_finish_does_not_restart_pending_refresh(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._rows_plan_runtime.worker = object()
        service._rows_plan_pending = ({"Default.txt": {}}, {"items": {}}, 1.5, page)
        service._request_rows_plan_refresh = Mock()
        single_shot = Mock()

        with patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            single_shot,
        ):
            service._on_rows_plan_worker_finished(object())

        single_shot.assert_not_called()
        service._request_rows_plan_refresh.assert_not_called()
        self.assertEqual(service._rows_plan_pending, ({"Default.txt": {}}, {"items": {}}, 1.5, page))

    def test_rows_plan_scheduled_restart_uses_latest_pending_request(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        worker = SimpleNamespace(deleteLater=Mock())
        service._rows_plan_worker = worker
        service._rows_plan_pending = ({"Old.txt": {}}, {"items": {}}, 1.5, page)
        scheduled_callbacks = []

        with patch(
            "presets.user_presets_runtime_service.UserPresetsRowsPlanWorker",
            _RowsPlanWorker,
        ), patch(
            "presets.user_presets_runtime_service.QTimer.singleShot",
            side_effect=lambda _delay, callback: scheduled_callbacks.append(callback),
        ):
            service._on_rows_plan_worker_finished(worker)
            service._request_rows_plan_refresh({"Latest.txt": {}}, {"items": {"Latest.txt": {}}}, 2.5, page)

            self.assertEqual(_RowsPlanWorker.instances, [])
            self.assertEqual(len(scheduled_callbacks), 1)

            scheduled_callbacks[0]()

        self.assertEqual(len(_RowsPlanWorker.instances), 1)
        self.assertEqual(_RowsPlanWorker.instances[0].all_presets, {"Latest.txt": {}})
        self.assertEqual(_RowsPlanWorker.instances[0].started_at, 2.5)

    def test_rows_plan_result_ignored_when_new_plan_is_pending(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._rows_plan_request_id = 4
        service._rows_plan_pending = ({"Latest.txt": {}}, {"items": {}}, 2.5, page)
        service._schedule_rows_plan_apply = Mock()

        service._on_rows_plan_loaded(4, "old-plan", 1.5, page)

        service._schedule_rows_plan_apply.assert_not_called()

    def test_pending_rows_plan_apply_is_ignored_when_new_plan_is_pending(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=Mock(),
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._pending_rows_plan_apply = ("old-plan", 1.5, page)
        service._rows_plan_apply_scheduled = True
        service._rows_plan_pending = ({"Latest.txt": {}}, {"items": {}}, 2.5, page)

        service._run_scheduled_rows_plan_apply()

        adapter.apply_rows_plan.assert_not_called()

    def test_rows_plan_error_ignored_when_new_plan_is_pending(self) -> None:
        import presets.user_presets_runtime_service as runtime_service
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._rows_plan_request_id = 4
        service._rows_plan_pending = ({"Latest.txt": {}}, {"items": {}}, 2.5, page)
        service._ui_dirty = False

        with patch.object(runtime_service, "log") as log_mock:
            service._on_rows_plan_failed(4, "old error", page)

        self.assertFalse(service._ui_dirty)
        log_mock.assert_not_called()

    def test_remove_deleted_preset_locally_does_not_write_folder_meta_from_gui_path(self) -> None:
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        model = Mock()
        model.find_preset_row.return_value = 0
        model.remove_preset.return_value = True
        page = SimpleNamespace(isVisible=lambda: True, _presets_model=model)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: False,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._cached_presets_metadata = {"Deleted.txt": {}}

        self.assertTrue(service.remove_deleted_preset_locally("Deleted.txt", page))

        self.assertFalse(hasattr(adapter, "delete_preset_item_meta"))

    def _make_flush_service(self, *, bulk_reset_running: bool = False):
        from presets.user_presets_runtime_service import UserPresetsRuntimeAdapter, UserPresetsRuntimeService

        page = SimpleNamespace(isVisible=lambda: True)
        adapter = UserPresetsRuntimeAdapter(
            bulk_reset_running=lambda: bulk_reset_running,
            read_single_metadata=lambda _name: None,
            selected_source_file_name=lambda: "",
            presets_dir=lambda: None,
            cached_metadata=lambda: {},
            load_all_metadata=lambda: {},
            load_folder_state=lambda: {},
            build_rows_plan=lambda _metadata, _folder_state: object(),
            apply_rows_plan=lambda _plan, _started_at: None,
        )
        service = UserPresetsRuntimeService()
        service.attach_page(page, adapter)
        service._request_single_metadata_refresh = Mock()
        service.schedule_presets_reload = Mock()
        return service, page

    def test_watch_events_flush_applies_point_refresh_for_small_batches(self) -> None:
        service, page = self._make_flush_service()
        service._watcher_mode = "native"
        service._pending_watch_event_names = {"Alpha.txt", "Beta.txt"}

        service._flush_pending_watch_events(page)

        self.assertEqual(service._pending_watch_event_names, set())
        self.assertEqual(
            [call.args[0] for call in service._request_single_metadata_refresh.call_args_list],
            ["Alpha.txt", "Beta.txt"],
        )
        service.schedule_presets_reload.assert_not_called()

    def test_watch_events_flush_falls_back_to_full_reload_on_overflow(self) -> None:
        service, page = self._make_flush_service()
        service._watcher_mode = "native"
        service._pending_watch_event_names = {"Alpha.txt"}
        service._pending_watch_overflow = True

        service._flush_pending_watch_events(page)

        service._request_single_metadata_refresh.assert_not_called()
        service.schedule_presets_reload.assert_called_once()
        self.assertTrue(service._ui_dirty)

    def test_watch_events_flush_falls_back_to_full_reload_on_large_batches(self) -> None:
        service, page = self._make_flush_service()
        service._watcher_mode = "native"
        service._pending_watch_event_names = {f"Preset{i}.txt" for i in range(9)}

        service._flush_pending_watch_events(page)

        service._request_single_metadata_refresh.assert_not_called()
        service.schedule_presets_reload.assert_called_once()

    def test_watch_events_flush_marks_dirty_without_reload_during_bulk_reset(self) -> None:
        service, page = self._make_flush_service(bulk_reset_running=True)
        service._watcher_mode = "native"
        service._pending_watch_event_names = {"Alpha.txt"}

        service._flush_pending_watch_events(page)

        service._request_single_metadata_refresh.assert_not_called()
        service.schedule_presets_reload.assert_not_called()
        self.assertTrue(service._ui_dirty)

    def test_watch_events_flush_in_qfsw_mode_requests_dir_diff(self) -> None:
        service, page = self._make_flush_service()
        service._watcher_mode = "qfsw"
        service._request_user_dir_diff = Mock()

        service._flush_pending_watch_events(page)

        service._request_user_dir_diff.assert_called_once()

    def test_native_watch_events_filter_non_preset_names(self) -> None:
        service, page = self._make_flush_service()
        service._restart_watch_flush_timer = Mock()

        service._on_native_watch_events(
            [
                (3, "Alpha.txt"),
                (1, "editor.tmp"),
                (3, "nested\\Beta.txt"),
                (2, ""),
            ],
            page,
        )

        self.assertEqual(service._pending_watch_event_names, {"Alpha.txt"})
        service._restart_watch_flush_timer.assert_called_once()

    def test_initial_dir_diff_reconciles_names_with_cached_metadata(self) -> None:
        service, page = self._make_flush_service()
        service._apply_watch_event_names = Mock()
        service._dir_diff_request_id = 5
        service._cached_presets_metadata = {
            "Gone.txt": {"is_builtin": False},
            "Builtin.txt": {"is_builtin": True},
            "Same.txt": {"is_builtin": False},
        }

        service._on_user_dir_diff_loaded(
            5,
            ({"Same.txt": (1, 1), "New.txt": (2, 2)}, [], True),
            page,
        )

        self.assertEqual(service._user_dir_snapshot, {"Same.txt": (1, 1), "New.txt": (2, 2)})
        service._apply_watch_event_names.assert_called_once()
        names = service._apply_watch_event_names.call_args.args[0]
        self.assertEqual(names, {"New.txt", "Gone.txt"})

    def test_dir_diff_worker_reports_added_removed_and_changed_names(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from presets.user_presets_runtime_service import UserPresetsDirDiffWorker

        with TemporaryDirectory() as temp_dir:
            presets_dir = Path(temp_dir)
            (presets_dir / "Kept.txt").write_text("--new\n", encoding="utf-8")
            (presets_dir / "Added.txt").write_text("--new\n", encoding="utf-8")
            (presets_dir / "Changed.txt").write_text("--new\n--extra\n", encoding="utf-8")
            (presets_dir / "ignored.log").write_text("noise", encoding="utf-8")

            kept_key = (
                int((presets_dir / "Kept.txt").stat().st_mtime_ns),
                int((presets_dir / "Kept.txt").stat().st_size),
            )
            worker = UserPresetsDirDiffWorker(
                1,
                presets_dir=presets_dir,
                previous_snapshot={
                    "Kept.txt": kept_key,
                    "Removed.txt": (10, 10),
                    "Changed.txt": (1, 1),
                },
            )
            results: list = []
            worker.loaded.connect(lambda _rid, result: results.append(result))

            worker.run()

        self.assertEqual(len(results), 1)
        snapshot, changed_names, is_initial = results[0]
        self.assertFalse(is_initial)
        self.assertEqual(set(snapshot), {"Kept.txt", "Added.txt", "Changed.txt"})
        self.assertEqual(changed_names, ["Added.txt", "Changed.txt", "Removed.txt"])


if __name__ == "__main__":
    unittest.main()
