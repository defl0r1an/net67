"""Локальные предпочтения списка: без ключей, ссылок и адресов подписок."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from utils.atomic_text import atomic_write_text


def profile_id(profile) -> str:
    # Название подписки может обновиться; секрет самой ссылки в файл не попадает.
    raw = str(getattr(profile, "raw", "") or "")
    if not raw:
        raw = "\0".join(str(getattr(profile, name, "") or "") for name in
                        ("protocol", "endpoint", "public_key", "name"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class VpnViewState:
    def __init__(self, root: Path):
        self.path = Path(root) / "vpn-view.json"
        self.favorites: set[str] = set()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.favorites = {value for value in data.get("favorites", [])
                              if isinstance(value, str) and len(value) == 64}
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def is_favorite(self, profile) -> bool:
        return profile_id(profile) in self.favorites

    def toggle_favorite(self, profile) -> None:
        updated = self.favorites ^ {profile_id(profile)}
        # Сначала запись: при отказе диска интерфейс не обещает сохранённый выбор.
        atomic_write_text(self.path, json.dumps({"favorites": sorted(updated)},
                                               ensure_ascii=False) + "\n")
        self.favorites = updated
