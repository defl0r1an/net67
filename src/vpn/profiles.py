"""Хранилище VPN-профилей.

Профили лежат отдельным файлом в папке настроек, а не в общем
settings.json: там приватные ключи, и держать их в файле, который
попадает в диагностические архивы поддержки, не стоит.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from vpn.parser import AmneziaParams, VpnProfile

PROFILES_FILE_NAME = "vpn_profiles.json"


def profiles_path(root: Path | str) -> Path:
    return Path(root) / PROFILES_FILE_NAME


def _profile_to_dict(profile: VpnProfile) -> dict:
    data = asdict(profile)
    awg = data.pop("awg", None) or {}
    data["awg"] = dict(awg.get("values") or {})
    return data


def _profile_from_dict(data: dict) -> VpnProfile:
    payload = dict(data or {})
    awg_values = payload.pop("awg", None) or {}
    # Значения хранятся строками: H1..H4 бывают диапазонами "мин-макс".
    # Профили, сохранённые ранней версией, держат числа — приводим к
    # строке, иначе клиент получит конфиг с int вместо исходной записи.
    clean: dict[str, str] = {}
    for key, value in dict(awg_values).items():
        text = str(value).strip()
        if text:
            clean[str(key)] = text

    allowed = {f for f in VpnProfile.__slots__} if hasattr(VpnProfile, "__slots__") else set(payload)
    payload = {k: v for k, v in payload.items() if k in allowed}
    return VpnProfile(**payload, awg=AmneziaParams(values=clean))


def load_profiles(root: Path | str) -> list[VpnProfile]:
    path = profiles_path(root)
    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Битый файл не должен мешать работе страницы.
        return []

    items = raw.get("profiles") if isinstance(raw, dict) else raw
    profiles: list[VpnProfile] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        try:
            profiles.append(_profile_from_dict(item))
        except Exception:
            continue
    return profiles


def save_profiles(root: Path | str, profiles: list[VpnProfile]) -> tuple[bool, str]:
    path = profiles_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "profiles": [_profile_to_dict(p) for p in profiles]}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        return (False, f"Не удалось сохранить профили: {exc}")
    return (True, "")


def upsert_profile(profiles: list[VpnProfile], profile: VpnProfile) -> list[VpnProfile]:
    """Добавляет профиль или заменяет существующий с тем же адресом.

    Ключ уникальности — endpoint, а не имя: один и тот же сервер,
    добавленный дважды, должен обновиться, а не задвоиться.
    """
    result = [p for p in profiles if p.endpoint != profile.endpoint]
    result.append(profile)
    return result


def remove_profile(profiles: list[VpnProfile], endpoint: str) -> list[VpnProfile]:
    return [p for p in profiles if p.endpoint != str(endpoint or "")]


def display_name(profile) -> str:
    """Что показать в списке.

    Список один на оба рода профилей, и имя у них зовётся по-разному:
    у конфигурации WireGuard это `name`, у сервера из ссылки — `title`.
    Обращение к `profile.name` напрямую роняло страницу целиком:

        AttributeError: 'LinkProfile' object has no attribute 'name'

    Падало это не при добавлении, а при показе — то есть подписка
    скачивалась, серверы разбирались и сохранялись, а потом окно
    обрывалось на попытке их нарисовать.
    """
    name = getattr(profile, "name", "") or getattr(profile, "title", "")
    if name:
        return str(name)

    host = getattr(profile, "endpoint_host", "") or getattr(profile, "host", "")
    if host:
        return str(host)

    return "Профиль без имени"


__all__ = [
    "PROFILES_FILE_NAME",
    "display_name",
    "load_profiles",
    "profiles_path",
    "remove_profile",
    "save_profiles",
    "upsert_profile",
]
