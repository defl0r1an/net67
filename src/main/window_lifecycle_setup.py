from __future__ import annotations

import time as _time

from config.window_metrics import MIN_HEIGHT, MIN_WIDTH
from main.application_lifecycle import ApplicationLifecycle
from main.application_lifecycle_port import build_application_lifecycle_window_port
from main.runtime_state import log_startup_metric as emit_startup_metric
from ui.window_close_flow import WindowCloseFlow
from ui.window_geometry_runtime import WindowGeometryRuntime


def attach_window_lifecycle(window, features) -> None:
    from config.window_metrics import (
        SIMPLE_MIN_HEIGHT,
        SIMPLE_MIN_WIDTH,
        get_window_size_for_mode,
    )
    from ui.navigation.schema import is_advanced_mode_enabled
    from ui.window_mode_geometry import apply_window_size_for_mode

    try:
        advanced = bool(is_advanced_mode_enabled())
    except Exception:
        advanced = True

    # Размер окно получит от WindowGeometryRuntime — либо сохранённый,
    # либо default_* ниже. Здесь только нижняя граница под режим.
    apply_window_size_for_mode(window, advanced, resize=False)

    default_width, default_height = get_window_size_for_mode(advanced)

    window.window_geometry_runtime = WindowGeometryRuntime(
        window,
        # Нижняя граница для проверки сохранённой геометрии берётся
        # самая мягкая. Иначе размер, выставленный в простом виде, при
        # следующем запуске сочли бы слишком маленьким и отбросили.
        min_width=min(MIN_WIDTH, SIMPLE_MIN_WIDTH),
        min_height=min(MIN_HEIGHT, SIMPLE_MIN_HEIGHT),
        default_width=default_width,
        default_height=default_height,
        close_state=window.close_state,
        create_geometry_save_worker=features.window_geometry.create_geometry_save_worker,
    )
    window.application_lifecycle = ApplicationLifecycle(
        window_port=build_application_lifecycle_window_port(window),
        close_state=window.close_state,
        runtime_feature=features.runtime,
        telegram_proxy_feature=features.telegram_proxy,
        tray_feature=features.tray,
    )
    window.window_close_flow = WindowCloseFlow(
        parent=window,
        close_state=window.close_state,
        get_launch_state_snapshot=features.runtime.snapshot,
        close_to_tray=window.close_to_tray,
        exit_stop_dpi=window.exit_stop_dpi,
        exit_keep_dpi=window.exit_keep_dpi,
        tray_close_mode=features.program_settings.tray_close_mode,
    )


def restore_window_geometry(window) -> None:
    t_geometry = _time.perf_counter()
    window.window_geometry_runtime.restore_geometry()
    emit_startup_metric(
        "StartupWindowInitRestoreGeometry",
        f"{(_time.perf_counter() - t_geometry) * 1000:.0f}ms",
    )


__all__ = ["attach_window_lifecycle", "restore_window_geometry"]
