from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PresetServicesBundle:
    app_paths: object
    preset_mode_coordinator: object
    preset_file_store: object
    preset_selection_service: object
    preset_store_winws2: object
    preset_store_winws1: object


def create_preset_services(app_paths) -> PresetServicesBundle:
    from presets.file_store import PresetFileStore
    from presets.mode_coordinator import PresetModeCoordinator
    from presets.selection_service import PresetSelectionService
    from presets.ui_store import PresetUiStore
    from settings.mode import ENGINE_WINWS1, ENGINE_WINWS2

    preset_file_store = PresetFileStore(app_paths)
    preset_selection_service = PresetSelectionService(preset_file_store)
    return PresetServicesBundle(
        app_paths=app_paths,
        preset_mode_coordinator=PresetModeCoordinator(app_paths, preset_selection_service, preset_file_store),
        preset_file_store=preset_file_store,
        preset_selection_service=preset_selection_service,
        preset_store_winws2=PresetUiStore(ENGINE_WINWS2, preset_file_store, preset_selection_service),
        preset_store_winws1=PresetUiStore(ENGINE_WINWS1, preset_file_store, preset_selection_service),
    )


__all__ = ["PresetServicesBundle", "create_preset_services"]
