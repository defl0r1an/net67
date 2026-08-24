"""Хранение серверов, добавленных по ссылке.

Отдельно от профилей WireGuard намеренно. Те лежат файлами `.conf` и
поднимаются службой Windows; эти — строки ссылок, которые отдаются ядру
Xray как есть. Сложить их в одно хранилище значило бы завести поле
«а это какого рода профиль» и разбирать его в каждом месте, где список
читают.

## Что хранится

Только ссылка и имя. Всё остальное — хост, порт, протокол, параметры
маскировки — разбирается из ссылки при чтении. Так сделано потому, что
разбор со временем улучшается: сегодня мы не понимаем какой-нибудь
`fp=chrome`, завтра поймём, и старые записи начнут работать сами.
Хранить разобранное значило бы законсервировать сегодняшнее незнание.

## Про подписку

Ссылка на подписку разворачивается в список серверов при добавлении, и
в файл попадают уже сами серверы. Хранить подписку и ходить за ней
каждый раз — значит зависеть от чужого сервера при каждом открытии
страницы.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path


#: Имя файла со ссылками.
STORE_NAME = "vpn-links.json"

#: Версия формата. Пишется в файл, чтобы будущая правка формата могла
#: отличить свои записи от чужих, а не гадать по составу полей.
FORMAT_VERSION = 1


def store_path(root: Path) -> Path:
    return Path(root) / STORE_NAME


def to_record(profile) -> dict:
    """Запись для файла: имя и ссылка, больше ничего."""
    return {
        "title": str(getattr(profile, "title", "") or ""),
        "link": str(getattr(profile, "raw", "") or ""),
    }


def load_links(root: Path) -> tuple[list, list[str]]:
    """Читает сохранённые ссылки. Возвращает (профили, ошибки).

    Ошибки не проглатываются: молча потерять три сервера из тридцати —
    значит показать неполный список и не сказать об этом.
    """
    from vpn.links import LinkError, parse_link

    path = store_path(root)
    if not path.is_file():
        return ([], [])

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ([], [f"файл со ссылками не читается: {exc}"])

    records = data.get("links") if isinstance(data, dict) else data
    if not isinstance(records, list):
        return ([], ["в файле со ссылками нет списка"])

    profiles: list = []
    errors: list[str] = []
    for record in records:
        link = ""
        title = ""
        if isinstance(record, dict):
            link = str(record.get("link") or "")
            title = str(record.get("title") or "")
        elif isinstance(record, str):
            link = record
        if not link:
            continue
        try:
            profile = parse_link(link)
        except LinkError as exc:
            errors.append(f"{link[:40]}…: {exc}")
            continue
        if title and title != profile.title:
            # Имя, данное человеком, важнее имени из ссылки: он его и
            # будет искать глазами в списке.
            #
            # Через replace, а не присваиванием: LinkProfile — frozen
            # dataclass, и присваивание там падает с FrozenInstanceError.
            # Неизменяемость здесь к месту: профиль читают из нескольких
            # мест, и правка на месте разошлась бы с файлом.
            profile = dataclasses.replace(profile, title=title)
        profiles.append(profile)
    return (profiles, errors)


def save_links(root: Path, profiles) -> tuple[bool, str]:
    """Пишет список. Возвращает (получилось, сообщение об ошибке)."""
    path = store_path(root)
    payload = {
        "version": FORMAT_VERSION,
        "links": [to_record(profile) for profile in (profiles or ())],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return (True, "")
    except Exception as exc:
        return (False, f"Не удалось сохранить список серверов: {exc}")


def merge(existing, added) -> list:
    """Добавляет новые серверы, не плодя дубликатов.

    Совпадением считаем одинаковую ссылку: у одного сервера в подписке
    может быть разное имя в разные дни, а ссылка та же.
    """
    result = list(existing or ())
    known = {str(getattr(item, "raw", "")) for item in result}
    for profile in added or ():
        link = str(getattr(profile, "raw", ""))
        if not link or link in known:
            continue
        known.add(link)
        result.append(profile)
    return result


__all__ = [
    "FORMAT_VERSION",
    "STORE_NAME",
    "load_links",
    "merge",
    "save_links",
    "store_path",
    "to_record",
]
