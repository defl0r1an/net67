from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.feature_facades import (
        AppearanceFeature,
        BlockcheckFeature,
        DnsFeature,
        ExternalActionsFeature,
        FakesFeature,
        HostsFeature,
        ListsFeature,
        LogsFeature,
        PresetsFeature,
        ProfileFeature,
        ProgramSettingsFeature,
        RuntimeFeature,
        TelegramProxyFeature,
        TrayFeature,
        UpdaterFeature,
        WindowGeometryFeature,
    )


@dataclass(frozen=True, slots=True)
class AppFeatures:
    appearance: AppearanceFeature
    runtime: RuntimeFeature
    presets: PresetsFeature
    profile: ProfileFeature
    blockcheck: BlockcheckFeature
    dns: DnsFeature
    fakes: FakesFeature
    hosts: HostsFeature
    lists: ListsFeature
    logs: LogsFeature
    telegram_proxy: TelegramProxyFeature
    tray: TrayFeature
    updater: UpdaterFeature
    external_actions: ExternalActionsFeature
    program_settings: ProgramSettingsFeature
    window_geometry: WindowGeometryFeature
