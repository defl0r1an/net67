from __future__ import annotations


def build_window_page_deps_sources(*, features, state, page_actions) -> PageDepsSources:
    from ui.page_deps.common import PageDepsSources

    return PageDepsSources(
        feature_deps={
            "blockcheck": features.blockcheck,
            "dns": features.dns,
            "external_actions": features.external_actions,
            "hosts": features.hosts,
            "logs": features.logs,
            "presets": features.presets,
            "profile": features.profile,
            "program_settings": features.program_settings,
            "runtime": features.runtime,
            "telegram_proxy": features.telegram_proxy,
            "updater": features.updater,
        },
        ui_state_store=state.ui,
        actions={
            "after_launch_method_changed": page_actions.after_launch_method_changed,
            "notify": page_actions.notify,

            "on_profile_setup_changed": page_actions.on_profile_setup_changed,
            "open_connection_test": page_actions.open_connection_test,
            "open_folder": page_actions.open_folder,
            "open_preset_raw_editor": page_actions.open_preset_raw_editor,
            "open_profile_setup": page_actions.open_profile_setup,
            "request_exit": page_actions.request_exit,
            "set_status": page_actions.set_status,
            "show_active_mode_control_page": page_actions.show_active_mode_control_page,
            "show_page": page_actions.show_page,
            "start_onboarding_tour": page_actions.start_onboarding_tour,
        },
    )


def attach_window_ui_root(window, *, features, state, page_actions) -> None:
    import time as _time

    from main.runtime_state import log_startup_metric as emit_startup_metric

    t_import = _time.perf_counter()
    from ui.ui_root import WindowUiRoot
    from ui.window_bootstrap_runtime import WindowRuntimeBootstrapDeps

    emit_startup_metric(
        "StartupWindowUiRootImport",
        f"{(_time.perf_counter() - t_import) * 1000:.0f}ms",
    )

    t_construct = _time.perf_counter()
    runtime_bootstrap_deps = WindowRuntimeBootstrapDeps(
        runtime_feature=features.runtime,
        presets_feature=features.presets,
        profile_feature=features.profile,
        ui_state_store=state.ui,
        notify=page_actions.notify,
        set_status=page_actions.set_status,
        sidebar_expanded_save_worker_factory=features.program_settings.create_sidebar_expanded_save_worker,
    )
    window._ui_root = WindowUiRoot(
        window,
        build_window_page_deps_sources(
            features=features,
            state=state,
            page_actions=page_actions,
        ),
        runtime_bootstrap_deps,
    )
    emit_startup_metric(
        "StartupWindowUiRootConstruct",
        f"{(_time.perf_counter() - t_construct) * 1000:.0f}ms",
    )
    from shell.launch_badge import bind_launch_title_badge

    launch_control = _build_window_launch_control(
        window,
        features=features,
        state=state,
        page_actions=page_actions,
    )
    window.launchControl = launch_control
    bind_launch_title_badge(window, state.ui, launch_control)


def _build_window_launch_control(window, *, features, state, page_actions):
    """Пульт пуска/остановки для метки в заголовке окна.

    В zapret через него же ходят страница управления и трей. У net67
    своя страница управления (большая кнопка, простой и расширенный
    вид) и свой трей, их переделку не переносили; обе двери зовут одни
    и те же команды runtime и читают один UI-store.
    """
    from app.page_names import PageName
    from ui.launch_control import build_launch_control

    def _stop_conflicting_checks() -> bool:
        from ui.window_adapter import send_page_command

        return bool(
            send_page_command(
                window,
                PageName.BLOCKCHECK,
                "stop_runtime_conflicting_checks",
                {"source": "dpi_start"},
                ensure=False,
            )
        )

    launch_control = build_launch_control(
        runtime_feature=features.runtime,
        ui_state_store=state.ui,
        stop_conflicting_checks=_stop_conflicting_checks,
        set_status=page_actions.set_status,
        request_exit=page_actions.request_exit,
        parent=window,
    )
    return launch_control


__all__ = ["attach_window_ui_root", "build_window_page_deps_sources"]
