from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresetManifest:
    file_name: str
    name: str
    updated_at: str
    kind: str = "user"
    storage_scope: str = "user"
