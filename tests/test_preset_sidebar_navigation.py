"""Навигация сайдбара по режимам запуска.

Проверяется фильтрация по движку (net67 v1 против net67 v2), поэтому
всюду передаётся advanced=True: без него сработает фильтр простого
интерфейса и в сайдбаре останутся только главная и оформление.
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class PresetSidebarNavigationTests(unittest.TestCase):


    def test_preset_setup_page_deps_open_profile_order_page(self) -> None:
        import ui.page_deps.presets as preset_deps
        import ui.page_composition as page_composition

        deps_source = inspect.getsource(preset_deps.build_preset_setup_page_kwargs)
        composition_source = inspect.getsource(page_composition)

        self.assertIn("open_profile_order", deps_source)
        self.assertIn("resolve_profile_order_page_for_method", deps_source)
        self.assertIn("build_profile_order_page_kwargs", composition_source)


    def test_common_sidebar_groups_keep_tools_and_diagnostics_separate(self) -> None:
        from app.page_names import PageName
        from settings.mode import ZAPRET2_MODE
        from ui.navigation.layout_plan import build_sidebar_group_plans

        plans = {
            group_plan.group_name: group_plan
            for group_plan in build_sidebar_group_plans(ZAPRET2_MODE, advanced=True)
        }

        self.assertEqual(
            plans["system"].page_names,
            (
                PageName.NETWORK,
                PageName.HOSTS,
                PageName.TELEGRAM_PROXY,
                PageName.VPN,
            ),
        )
        self.assertEqual(
            plans["diagnostics"].page_names,
            (
                PageName.BLOCKCHECK,
                PageName.WINWS_LOG_ANALYZER,
            ),
        )

    def test_common_sidebar_labels_use_dns_and_hosts_wording(self) -> None:
        from app.page_names import PageName
        from app.ui_texts import get_nav_page_label, tr

        self.assertEqual(tr("nav.header.system", language="ru"), "Инструменты")
        self.assertEqual(get_nav_page_label(PageName.NETWORK, language="ru"), "Настройка DNS")
        self.assertEqual(get_nav_page_label(PageName.HOSTS, language="ru"), "Редактор hosts")
        self.assertEqual(
            tr("page.network.subtitle", language="ru"),
            "Выберите DNS-сервер — он сразу встанет на отмеченные сетевые адаптеры. "
            "Кнопка «Замерить скорость» покажет, какой сервер отвечает быстрее.",
        )


    def test_initial_sidebar_build_defers_secondary_groups_until_after_interactive(self) -> None:
        from app.page_names import PageName
        from settings.mode import ZAPRET2_MODE
        import ui.navigation.sidebar_builder as sidebar_builder

        class FakeSignal:
            def __init__(self) -> None:
                self.connected = []

            def connect(self, callback) -> None:
                self.connected.append(callback)

            def emit(self) -> None:
                for callback in list(self.connected):
                    callback("ui_ready")

        class FakeNavigationInterface:
            def __init__(self) -> None:
                self.headers = []
                self.displayModeChanged = FakeSignal()

            # Имя группы приходит отдельным ключом: на него опираются
            # вкладки разделов в полосе заголовка. Заглушка обязана его
            # принимать, иначе она расходится с настоящей панелью.
            def addItemHeader(self, text, position, *, group=None, **_ignored):
                header = SimpleNamespace(text=text, position=position, group=group, setVisible=Mock())
                self.headers.append(header)
                return header

            def setMinimumExpandWidth(self, width) -> None:
                self.minimum_expand_width = width

        added_pages: list[PageName] = []
        signal = FakeSignal()
        session = SimpleNamespace(
            nav_scroll_position=None,
            ui_language="ru",
            nav_items={},
            nav_headers=[],
            nav_header_by_group={},
            nav_mode_visibility={},
            pages={},
            nav_labels={},
        )
        window = SimpleNamespace(
            ui_session=session,
            navigationInterface=FakeNavigationInterface(),
            startup_state=SimpleNamespace(interactive_logged=False),
            startup_interactive_ready=signal,
            get_launch_method=lambda: ZAPRET2_MODE,
            log_startup_metric=Mock(),
        )
        scheduled: list[tuple[int, object]] = []

        def _fake_add_nav_item(current_window, page_name, *_args, **_kwargs):
            added_pages.append(page_name)
            session.nav_items[page_name] = SimpleNamespace(setVisible=Mock())

        with (
            patch.object(sidebar_builder, "_schedule_hidden_mode_nav_items_after_interactive", side_effect=lambda current_window: None),
            patch.object(sidebar_builder.QTimer, "singleShot", side_effect=lambda delay_ms, callback: scheduled.append((delay_ms, callback))),
            patch.object(sidebar_builder, "add_nav_item", side_effect=_fake_add_nav_item),
            patch("settings.store.get_ui_state_settings", return_value={"sidebar_expanded": True}),
        ):
            sidebar_builder.init_navigation(window)

            self.assertIn(PageName.ZAPRET2_MODE_CONTROL, added_pages)
            self.assertNotIn(PageName.ZAPRET2_USER_PRESETS, added_pages)
            self.assertNotIn(PageName.ZAPRET2_PRESET_SETUP, added_pages)
            self.assertNotIn(PageName.NETWORK, added_pages)
            # Сразу после init_navigation запланирована только страховочная
            # перепроверка состояния сайдбара, но не вторичные группы.
            self.assertEqual(
                [delay for delay, _callback in scheduled],
                [sidebar_builder.SIDEBAR_INTENT_RECHECK_AFTER_INIT_MS],
            )

            signal.emit()

            self.assertEqual(len(scheduled), 2)
            self.assertLessEqual(scheduled[1][0], 1_000)

            next_callback_index = 0
            while next_callback_index < len(scheduled):
                scheduled[next_callback_index][1]()
                next_callback_index += 1

        self.assertIn(PageName.ZAPRET2_USER_PRESETS, added_pages)
        self.assertIn(PageName.ZAPRET2_PRESET_SETUP, added_pages)
        self.assertIn(PageName.NETWORK, added_pages)
        self.assertIn(PageName.LOGS, added_pages)

    def test_initial_sidebar_build_restores_saved_expanded_state(self) -> None:
        from settings.mode import ZAPRET2_MODE
        from ui.navigation.sidebar_state import store_warmed_sidebar_expanded
        import ui.navigation.sidebar_builder as sidebar_builder

        class FakeSignal:
            def connect(self, callback) -> None:
                _ = callback

        class FakeNavigationInterface:
            def __init__(self) -> None:
                self.headers = []
                self.expand_calls = []
                self.displayModeChanged = FakeSignal()

            # Имя группы приходит отдельным ключом: на него опираются
            # вкладки разделов в полосе заголовка. Заглушка обязана его
            # принимать, иначе она расходится с настоящей панелью.
            def addItemHeader(self, text, position, *, group=None, **_ignored):
                header = SimpleNamespace(text=text, position=position, group=group)
                self.headers.append(header)
                return header

            def setMinimumExpandWidth(self, width) -> None:
                self.minimum_expand_width = width

            def expand(self, useAni=True) -> None:
                self.expand_calls.append(useAni)

        session = SimpleNamespace(
            nav_scroll_position=None,
            ui_language="ru",
            nav_items={},
            nav_headers=[],
            nav_header_by_group={},
            nav_mode_visibility={},
            pages={},
        )
        nav = FakeNavigationInterface()
        window = SimpleNamespace(
            ui_session=session,
            navigationInterface=nav,
            get_launch_method=lambda: ZAPRET2_MODE,
            # шире порога 700: на узком окне восстановление не разворачивает
            # панель, чтобы не открывать MENU-оверлей поверх контента
            width=lambda: 900,
        )
        store_warmed_sidebar_expanded(True)

        with (
            patch.object(
                sidebar_builder,
                "_schedule_hidden_mode_nav_items_after_interactive",
                side_effect=lambda current_window: None,
            ),
            patch.object(
                sidebar_builder,
                "add_nav_item",
                side_effect=lambda current_window, page_name, *_args, **_kwargs: None,
            ),
            patch(
                "settings.store.get_ui_state_settings",
                side_effect=AssertionError("sidebar restore must use warmed state"),
            ),
        ):
            sidebar_builder.init_navigation(window)

        self.assertEqual(nav.expand_calls, [False])

    def test_initial_sidebar_build_restores_saved_collapsed_state(self) -> None:
        from settings.mode import ZAPRET2_MODE
        from ui.navigation.sidebar_state import store_warmed_sidebar_expanded
        import ui.navigation.sidebar_builder as sidebar_builder

        class FakeSignal:
            def connect(self, callback) -> None:
                _ = callback

        class FakePanel:
            def __init__(self) -> None:
                self.collapse_calls = 0

            def collapse(self) -> None:
                self.collapse_calls += 1

        class FakeNavigationInterface:
            def __init__(self) -> None:
                self.headers = []
                self.panel = FakePanel()
                self.displayModeChanged = FakeSignal()

            # Имя группы приходит отдельным ключом: на него опираются
            # вкладки разделов в полосе заголовка. Заглушка обязана его
            # принимать, иначе она расходится с настоящей панелью.
            def addItemHeader(self, text, position, *, group=None, **_ignored):
                header = SimpleNamespace(text=text, position=position, group=group)
                self.headers.append(header)
                return header

            def setMinimumExpandWidth(self, width) -> None:
                self.minimum_expand_width = width

        session = SimpleNamespace(
            nav_scroll_position=None,
            ui_language="ru",
            nav_items={},
            nav_headers=[],
            nav_header_by_group={},
            nav_mode_visibility={},
            pages={},
        )
        nav = FakeNavigationInterface()
        window = SimpleNamespace(
            ui_session=session,
            navigationInterface=nav,
            get_launch_method=lambda: ZAPRET2_MODE,
        )
        store_warmed_sidebar_expanded(False)

        with (
            patch.object(
                sidebar_builder,
                "_schedule_hidden_mode_nav_items_after_interactive",
                side_effect=lambda current_window: None,
            ),
            patch.object(
                sidebar_builder,
                "add_nav_item",
                side_effect=lambda current_window, page_name, *_args, **_kwargs: None,
            ),
            patch(
                "settings.store.get_ui_state_settings",
                side_effect=AssertionError("sidebar restore must use warmed state"),
            ),
        ):
            sidebar_builder.init_navigation(window)

        self.assertEqual(nav.panel.collapse_calls, 1)

    def test_initial_sidebar_build_keeps_indicator_animation_policy_untouched(self) -> None:
        from settings.mode import ZAPRET2_MODE
        import ui.navigation.sidebar_builder as sidebar_builder

        class FakeSignal:
            def connect(self, callback) -> None:
                _ = callback

        class FakePanel:
            def __init__(self) -> None:
                self.indicator_animation_values = []

            def setIndicatorAnimationEnabled(self, enabled: bool) -> None:
                self.indicator_animation_values.append(bool(enabled))

        class FakeNavigationInterface:
            def __init__(self) -> None:
                self.headers = []
                self.panel = FakePanel()
                self.displayModeChanged = FakeSignal()

            # Имя группы приходит отдельным ключом: на него опираются
            # вкладки разделов в полосе заголовка. Заглушка обязана его
            # принимать, иначе она расходится с настоящей панелью.
            def addItemHeader(self, text, position, *, group=None, **_ignored):
                header = SimpleNamespace(text=text, position=position, group=group)
                self.headers.append(header)
                return header

            def setMinimumExpandWidth(self, width) -> None:
                self.minimum_expand_width = width

        session = SimpleNamespace(
            nav_scroll_position=None,
            ui_language="ru",
            nav_items={},
            nav_headers=[],
            nav_header_by_group={},
            nav_mode_visibility={},
            pages={},
        )
        nav = FakeNavigationInterface()
        window = SimpleNamespace(
            ui_session=session,
            navigationInterface=nav,
            get_launch_method=lambda: ZAPRET2_MODE,
        )

        with (
            patch.object(sidebar_builder, "_schedule_hidden_mode_nav_items_after_interactive", side_effect=lambda *_args: None),
            patch.object(sidebar_builder, "add_nav_item", side_effect=lambda *_args, **_kwargs: None),
            patch("settings.store.get_ui_state_settings", return_value={"sidebar_expanded": True}),
        ):
            sidebar_builder.init_navigation(window)

        self.assertEqual(nav.panel.indicator_animation_values, [])

    def test_sidebar_display_mode_change_is_saved(self) -> None:
        from settings.mode import ZAPRET2_MODE
        import ui.navigation.sidebar_builder as sidebar_builder

        class FakeSignal:
            def __init__(self) -> None:
                self.connected = []

            def connect(self, callback) -> None:
                self.connected.append(callback)

            def emit(self, display_mode) -> None:
                for callback in self.connected:
                    callback(display_mode)

        class FakeNavigationInterface:
            def __init__(self) -> None:
                self.headers = []
                self.displayModeChanged = FakeSignal()
                menu_button = SimpleNamespace(event_filter=None)
                menu_button.installEventFilter = (
                    lambda event_filter: setattr(menu_button, "event_filter", event_filter)
                )
                self.panel = SimpleNamespace(
                    minimumExpandWidth=700,
                    isCollapsed=lambda: False,
                    menuButton=menu_button,
                )

            # Имя группы приходит отдельным ключом: на него опираются
            # вкладки разделов в полосе заголовка. Заглушка обязана его
            # принимать, иначе она расходится с настоящей панелью.
            def addItemHeader(self, text, position, *, group=None, **_ignored):
                header = SimpleNamespace(text=text, position=position, group=group)
                self.headers.append(header)
                return header

            def setMinimumExpandWidth(self, width) -> None:
                self.minimum_expand_width = width

            def expand(self, useAni=True) -> None:
                _ = useAni

        session = SimpleNamespace(
            nav_scroll_position=None,
            ui_language="ru",
            nav_items={},
            nav_headers=[],
            nav_header_by_group={},
            nav_mode_visibility={},
            pages={},
        )
        nav = FakeNavigationInterface()
        window = SimpleNamespace(
            ui_session=session,
            navigationInterface=nav,
            get_launch_method=lambda: ZAPRET2_MODE,
            # шире порога 700: только на широком окне COMPACT означает
            # осознанное сворачивание, а не responsive-механику библиотеки
            width=lambda: 900,
        )

        from ui.navigation.sidebar_state import store_warmed_sidebar_expanded

        store_warmed_sidebar_expanded(True)
        self.addCleanup(store_warmed_sidebar_expanded, None)

        with (
            patch.object(
                sidebar_builder,
                "_schedule_hidden_mode_nav_items_after_interactive",
                side_effect=lambda current_window: None,
            ),
            patch.object(
                sidebar_builder,
                "add_nav_item",
                side_effect=lambda current_window, page_name, *_args, **_kwargs: None,
            ),
            patch("settings.store.get_ui_state_settings", return_value={"sidebar_expanded": True}),
            patch("settings.store.set_ui_state_settings") as save_ui_state,
        ):
            create_worker = Mock()
            session.sidebar_expanded_save_worker_factory = create_worker
            worker = SimpleNamespace(
                isRunning=Mock(return_value=False),
                saved=SimpleNamespace(connect=Mock()),
                failed=SimpleNamespace(connect=Mock()),
                finished=SimpleNamespace(connect=Mock()),
                start=Mock(),
                deleteLater=Mock(),
            )
            create_worker.return_value = worker
            sidebar_builder.init_navigation(window)
            from PyQt6.QtCore import QEvent

            nav.panel.menuButton.event_filter.eventFilter(
                nav.panel.menuButton,
                QEvent(QEvent.Type.MouseButtonRelease),
            )
            nav.displayModeChanged.emit(SimpleNamespace(name="COMPACT"))

        create_worker.assert_called_once()
        self.assertFalse(create_worker.call_args.kwargs["expanded"])
        worker.start.assert_called_once_with()
        save_ui_state.assert_not_called()

    def test_sidebar_responsive_collapse_on_narrow_window_is_not_saved(self) -> None:
        from settings.mode import ZAPRET2_MODE
        import ui.navigation.sidebar_builder as sidebar_builder
        from ui.navigation.sidebar_state import store_warmed_sidebar_expanded

        class FakeSignal:
            def __init__(self) -> None:
                self.connected = []

            def connect(self, callback) -> None:
                self.connected.append(callback)

            def emit(self, display_mode) -> None:
                for callback in self.connected:
                    callback(display_mode)

        class FakeNavigationInterface:
            def __init__(self) -> None:
                self.headers = []
                self.displayModeChanged = FakeSignal()

            # Имя группы приходит отдельным ключом: на него опираются
            # вкладки разделов в полосе заголовка. Заглушка обязана его
            # принимать, иначе она расходится с настоящей панелью.
            def addItemHeader(self, text, position, *, group=None, **_ignored):
                header = SimpleNamespace(text=text, position=position, group=group)
                self.headers.append(header)
                return header

            def setMinimumExpandWidth(self, width) -> None:
                self.minimum_expand_width = width

            def expand(self, useAni=True) -> None:
                _ = useAni

        session = SimpleNamespace(
            nav_scroll_position=None,
            ui_language="ru",
            nav_items={},
            nav_headers=[],
            nav_header_by_group={},
            nav_mode_visibility={},
            pages={},
        )
        nav = FakeNavigationInterface()
        window = SimpleNamespace(
            ui_session=session,
            navigationInterface=nav,
            get_launch_method=lambda: ZAPRET2_MODE,
            width=lambda: 680,
        )

        store_warmed_sidebar_expanded(True)
        self.addCleanup(store_warmed_sidebar_expanded, None)

        with (
            patch.object(
                sidebar_builder,
                "_schedule_hidden_mode_nav_items_after_interactive",
                side_effect=lambda current_window: None,
            ),
            patch.object(
                sidebar_builder,
                "add_nav_item",
                side_effect=lambda current_window, page_name, *_args, **_kwargs: None,
            ),
            patch("settings.store.get_ui_state_settings", return_value={"sidebar_expanded": True}),
        ):
            create_worker = Mock()
            session.sidebar_expanded_save_worker_factory = create_worker
            sidebar_builder.init_navigation(window)
            nav.displayModeChanged.emit(SimpleNamespace(name="COMPACT"))

        create_worker.assert_not_called()
        self.assertTrue(session.sidebar_intent_controller.intent)

    def test_sidebar_display_mode_save_is_queued_while_worker_runs(self) -> None:
        import ui.navigation.sidebar_builder as sidebar_builder
        from ui.one_shot_worker_runtime import OneShotWorkerRuntime

        worker = SimpleNamespace(isRunning=Mock(return_value=True))
        runtime = OneShotWorkerRuntime()
        runtime.worker = worker
        session = SimpleNamespace(
            sidebar_expanded_save_runtime=runtime,
            sidebar_expanded_save_worker_factory=Mock(),
        )
        window = SimpleNamespace(ui_session=session)

        sidebar_builder._start_sidebar_expanded_save_worker(window, False)

        self.assertFalse(session.sidebar_expanded_save_state.pending)
        session.sidebar_expanded_save_worker_factory.assert_not_called()

    def test_sidebar_pending_save_restarts_after_event_loop_turn(self) -> None:
        import ui.navigation.sidebar_builder as sidebar_builder
        from ui.latest_value_worker_state import LatestValueWorkerState

        session = SimpleNamespace(
            sidebar_expanded_save_state=LatestValueWorkerState(object(), empty_value=None, pending=False),
            sidebar_expanded_save_runtime_worker=None,
        )
        window = SimpleNamespace(ui_session=session)
        single_shot = Mock(side_effect=lambda _delay, _callback: None)

        with (
            patch.object(sidebar_builder, "QTimer", SimpleNamespace(singleShot=single_shot), create=True),
            patch.object(sidebar_builder, "_start_sidebar_expanded_save_worker") as start_worker,
        ):
            sidebar_builder._on_sidebar_expanded_save_worker_finished(window, None)

            single_shot.assert_called_once()
            self.assertEqual(single_shot.call_args.args[0], 0)
            start_worker.assert_not_called()

            single_shot.call_args.args[1]()

            start_worker.assert_called_once_with(window, False)

    def test_stale_sidebar_pending_save_finish_does_not_restart_save(self) -> None:
        import ui.navigation.sidebar_builder as sidebar_builder
        from ui.latest_value_worker_state import LatestValueWorkerState

        current_worker = object()
        session = SimpleNamespace(
            sidebar_expanded_save_state=LatestValueWorkerState(object(), empty_value=None, pending=False),
            sidebar_expanded_save_runtime_worker=current_worker,
        )
        window = SimpleNamespace(ui_session=session)
        single_shot = Mock()

        with (
            patch.object(sidebar_builder, "QTimer", SimpleNamespace(singleShot=single_shot), create=True),
            patch.object(sidebar_builder, "_start_sidebar_expanded_save_worker") as start_worker,
        ):
            sidebar_builder._on_sidebar_expanded_save_worker_finished(window, object())

        single_shot.assert_not_called()
        start_worker.assert_not_called()
        self.assertFalse(session.sidebar_expanded_save_state.pending)
        self.assertIs(session.sidebar_expanded_save_runtime_worker, current_worker)


    def test_sidebar_nav_item_exposes_screen_reader_name(self) -> None:
        from app.page_names import PageName
        from settings.mode import ZAPRET2_MODE
        import ui.navigation.sidebar_builder as sidebar_builder

        class FakeNavItem:
            def __init__(self) -> None:
                self._accessible_name = ""
                self._accessible_description = ""
                self._properties = {}

            def accessibleName(self):  # noqa: N802
                return self._accessible_name

            def setAccessibleName(self, value):  # noqa: N802
                self._accessible_name = str(value)

            def accessibleDescription(self):  # noqa: N802
                return self._accessible_description

            def setAccessibleDescription(self, value):  # noqa: N802
                self._accessible_description = str(value)

            def property(self, name):
                return self._properties.get(str(name))

            def setProperty(self, name, value):  # noqa: N802
                self._properties[str(name)] = value

        class FakeNavigationInterface:
            def addItem(self, *, routeKey, icon, text, onClick, selectable, position):
                _ = routeKey, icon, text, onClick, selectable, position
                return FakeNavItem()

        session = SimpleNamespace(
            nav_items={},
            nav_icons={},
            nav_labels={PageName.NETWORK: "DNS и сеть"},
            nav_scroll_position=None,
            default_nav_icon=None,
            ui_language="ru",
            page_host=SimpleNamespace(ensure_page=lambda page_name: None),
        )
        window = SimpleNamespace(
            ui_session=session,
            navigationInterface=FakeNavigationInterface(),
            get_launch_method=lambda: ZAPRET2_MODE,
        )

        with patch.object(sidebar_builder, "get_eager_page_names_for_method", return_value=()):
            sidebar_builder.add_nav_item(window, PageName.NETWORK, None)

        item = session.nav_items[PageName.NETWORK]

        self.assertEqual(item.accessibleName(), "Открыть раздел: Настройка DNS")
        self.assertEqual(
            item.accessibleDescription(),
            "Открывает раздел Настройка DNS в боковом меню.",
        )
        self.assertEqual(item.property("screenReaderStateText"), "Открыть раздел: Настройка DNS")


    def test_add_nav_item_reuses_loaded_eager_page_without_second_ensure(self) -> None:
        from app.page_names import PageName
        from settings.mode import ZAPRET2_MODE
        import ui.navigation.sidebar_builder as sidebar_builder

        class FakePage:
            def __init__(self) -> None:
                self.name = ""

            def objectName(self) -> str:
                return self.name

            def setObjectName(self, name: str) -> None:
                self.name = name

        class FakeNavigationInterface:
            def __init__(self) -> None:
                self.added_pages = []

            def addItem(self, **_kwargs):
                raise AssertionError("eager page should use addSubInterface")

        loaded_page = FakePage()
        session = SimpleNamespace(
            nav_items={},
            nav_icons={},
            nav_labels={},
            nav_scroll_position=None,
            default_nav_icon=None,
            ui_language="ru",
            pages={PageName.ZAPRET2_MODE_CONTROL: loaded_page},
        )
        window = SimpleNamespace(
            ui_session=session,
            navigationInterface=FakeNavigationInterface(),
            get_launch_method=lambda: ZAPRET2_MODE,
            addSubInterface=Mock(return_value=object()),
        )

        with patch.object(sidebar_builder, "_ensure_page", side_effect=AssertionError("page is already loaded")):
            sidebar_builder.add_nav_item(window, PageName.ZAPRET2_MODE_CONTROL, None)

        window.addSubInterface.assert_called_once()
        self.assertIs(window.addSubInterface.call_args.args[0], loaded_page)
        self.assertIn(PageName.ZAPRET2_MODE_CONTROL, session.nav_items)

    def test_hidden_mode_sidebar_items_are_delayed_until_interactive_ready(self) -> None:
        import ui.navigation.sidebar_builder as sidebar_builder

        class Signal:
            def __init__(self) -> None:
                self._callbacks = []

            def connect(self, callback) -> None:
                self._callbacks.append(callback)

            def emit(self) -> None:
                for callback in list(self._callbacks):
                    callback("ui_ready")

        signal = Signal()
        window = SimpleNamespace(
            ui_session=SimpleNamespace(),
            startup_state=SimpleNamespace(interactive_logged=False),
            startup_interactive_ready=signal,
            log_startup_metric=Mock(),
        )
        scheduled = []
        installed = []

        with (
            patch.object(
                sidebar_builder.QTimer,
                "singleShot",
                side_effect=lambda delay_ms, callback: scheduled.append((int(delay_ms), callback)),
            ),
            patch.object(
                sidebar_builder,
                "_install_hidden_mode_nav_items",
                side_effect=lambda current_window: installed.append(current_window),
            ),
        ):
            sidebar_builder._schedule_hidden_mode_nav_items_after_interactive(window)
            self.assertEqual(scheduled, [])
            self.assertEqual(installed, [])

            signal.emit()

            self.assertEqual(len(scheduled), 1)
            self.assertEqual(scheduled[0][0], sidebar_builder.SIDEBAR_HIDDEN_MODE_ITEMS_AFTER_INTERACTIVE_MS)
            self.assertEqual(installed, [])

            scheduled[0][1]()

        self.assertEqual(installed, [window])

    def test_group_build_reads_launch_method_once_not_per_item(self) -> None:
        from app.page_names import PageName
        import ui.navigation.sidebar_builder as sidebar_builder
        from settings.mode import ZAPRET2_MODE

        launch_method_reads: list[str] = []
        added: list[tuple[PageName, str | None]] = []

        def _get_launch_method() -> str:
            # Настоящее чтение берёт общий замок настроек. В первую секунду
            # после запуска его держат фоновые задачи, и чтение на каждый
            # пункт меню задерживало кадр на 65–100 мс.
            launch_method_reads.append("read")
            return ZAPRET2_MODE

        session = SimpleNamespace(
            nav_scroll_position=None,
            nav_header_by_group={},
            nav_headers=[],
            ui_language="ru",
        )
        window = SimpleNamespace(
            ui_session=session,
            navigationInterface=SimpleNamespace(addItemHeader=lambda *_args: object()),
            get_launch_method=_get_launch_method,
        )
        group_plan = SimpleNamespace(
            header_key="",
            group_name="settings",
            page_names=(PageName.NETWORK, PageName.HOSTS, PageName.ABOUT),
        )

        with patch.object(
            sidebar_builder,
            "add_nav_item",
            side_effect=lambda _window, page_name, _position, **kwargs: added.append(
                (page_name, kwargs.get("launch_method"))
            ),
        ):
            sidebar_builder._add_sidebar_group(window, group_plan, {}, ZAPRET2_MODE)

        self.assertEqual(launch_method_reads, [])
        self.assertEqual(
            added,
            [
                (PageName.NETWORK, ZAPRET2_MODE),
                (PageName.HOSTS, ZAPRET2_MODE),
                (PageName.ABOUT, ZAPRET2_MODE),
            ],
        )

    def test_add_nav_item_uses_given_launch_method_without_settings_read(self) -> None:
        from app.page_names import PageName
        import ui.navigation.sidebar_builder as sidebar_builder
        from settings.mode import ZAPRET2_MODE

        class FakeNavItem:
            def setVisible(self, _visible) -> None:
                pass

            def setAccessibleName(self, _text) -> None:
                pass

            def setAccessibleDescription(self, _text) -> None:
                pass

            def setProperty(self, _name, _value) -> None:
                pass

        class FakeNavigationInterface:
            def addItem(self, *, routeKey, icon, text, onClick, selectable, position):
                _ = routeKey, icon, text, onClick, selectable, position
                return FakeNavItem()

        session = SimpleNamespace(
            nav_items={},
            nav_icons={},
            nav_labels={PageName.NETWORK: "DNS и сеть"},
            nav_scroll_position=None,
            default_nav_icon=None,
            ui_language="ru",
            page_host=SimpleNamespace(ensure_page=lambda page_name: None),
        )

        def _fail_read() -> str:
            raise AssertionError("режим запуска уже передан, читать настройки незачем")

        window = SimpleNamespace(
            ui_session=session,
            navigationInterface=FakeNavigationInterface(),
            get_launch_method=_fail_read,
        )
        seen_methods: list[str] = []

        with patch.object(
            sidebar_builder,
            "get_eager_page_names_for_method",
            side_effect=lambda method: seen_methods.append(method) or (),
        ):
            sidebar_builder.add_nav_item(window, PageName.NETWORK, None, launch_method=ZAPRET2_MODE)

        self.assertEqual(seen_methods, [ZAPRET2_MODE])
        self.assertIn(PageName.NETWORK, session.nav_items)

if __name__ == "__main__":
    unittest.main()
