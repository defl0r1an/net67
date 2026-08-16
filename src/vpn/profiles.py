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
            profile = _profile_from_dict(item)
        except Exception:
            continue
        if _is_empty_profile(profile):
            continue
        profiles.append(profile)
    return profiles


def _is_empty_profile(profile: VpnProfile) -> bool:
    """Профиль, которым нельзя подключиться и который не назвать.

    Такие записи остались в файлах у тех, кто держал рядом конфигурации
    и ссылки: ссылки записывались в файл конфигураций и при чтении
    теряли все свои поля. Правку в `save_profiles` они бы пережили —
    файл-то уже испорчен, — поэтому отсеиваются и на чтении.

    Условие намеренно жёсткое: нет ни адреса, ни ключа, ни имени.
    Настоящий профиль без адреса бесполезен, а ошибиться и выкинуть
    чужое здесь нельзя — это чужие ключи.
    """
    if str(getattr(profile, "endpoint_host", "") or "").strip():
        return False
    if str(getattr(profile, "private_key", "") or "").strip():
        return False
    if str(getattr(profile, "name", "") or "").strip():
        return False
    return True


def save_profiles(root: Path | str, profiles: list[VpnProfile]) -> tuple[bool, str]:
    """Пишет конфигурации WireGuard. Чужое сюда не попадает.

    Отбор — не перестраховка, а заплата на дыре, которая уже сработала.
    Страница держит один список на оба рода профилей: к конфигурациям
    подмешаны серверы из ссылок, они поднимаются другим клиентом и лежат
    в своём файле. Этот общий список отдавали сюда целиком, и ссылки
    записывались в файл конфигураций.

    Обратно они уже не читались: `VpnProfile` объявлен со `slots=True`,
    и `_profile_from_dict` выбрасывает поля, которых у него нет — а у
    ссылки это все поля разом, вместе с адресом и названием. Из каждой
    ссылки получался пустой профиль: «Профиль без имени» без адреса,
    да ещё и на вкладке Amnezia, потому что признак ссылки тоже терялся.
    Двадцать пять серверов подписки превращались в двадцать пять
    пустышек при первом же сохранении конфигурации рядом с ними.
    """
    path = profiles_path(root)
    own = [p for p in (profiles or ()) if isinstance(p, VpnProfile)]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "profiles": [_profile_to_dict(p) for p in own]}
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
