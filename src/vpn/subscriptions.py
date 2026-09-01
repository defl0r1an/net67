"""Подписки: адрес, срок, остаток трафика и серверы под ним.

## Зачем понадобилось

Раньше подписка разворачивалась в список серверов при добавлении и на
этом забывалась: в файл попадали только сами серверы. Отсюда три вещи,
которых не было и не могло быть.

Обновить подписку нечем — адрес не сохранён. Показать остаток трафика
нечем — он приходит в заголовке ответа, который никто не прочёл.
Сгруппировать серверы по подпискам нечем — в записи сервера не сказано,
откуда он взялся, и двадцать пять строк лежат вперемешку.

Здесь всё это хранится: адрес, имя, когда обновляли, что сервер сказал
про трафик и срок.

## Про заголовок с трафиком

Панели отдают его в `subscription-userinfo` — строка вида
``upload=0; download=312000000000; total=2048000000000; expire=1790000000``.
Это не стандарт, а сложившийся обычай, поэтому разбор терпимый: чего нет
— того нет, и на показ это не влияет. Врать округлением тоже нельзя:
если сервер прислал только общий лимит, показываем его и молчим про
остаток.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


STORE_NAME = "vpn_subscriptions.json"
FORMAT_VERSION = 1

#: Заголовок, в котором панели отдают трафик и срок.
USERINFO_HEADER = "subscription-userinfo"

#: Заголовок с именем подписки. Тоже обычай, а не стандарт.
PROFILE_TITLE_HEADER = "profile-title"


@dataclass(frozen=True, slots=True)
class SubscriptionUsage:
    """Что сервер сказал про трафик и срок. Любое поле может отсутствовать."""

    upload: int | None = None
    download: int | None = None
    total: int | None = None
    expires_at: int | None = None

    @property
    def used(self) -> int | None:
        """Израсходовано. Сумма, если есть обе половины."""
        if self.upload is None and self.download is None:
            return None
        return int(self.upload or 0) + int(self.download or 0)

    @property
    def left(self) -> int | None:
        used = self.used
        if used is None or self.total is None:
            return None
        return max(0, int(self.total) - used)

    def describe(self) -> str:
        """Короткая строка для интерфейса. Пусто — значит сказать нечего."""
        parts = []
        used, total = self.used, self.total
        if used is not None and total:
            parts.append(f"{format_bytes(used)} из {format_bytes(total)}")
        elif total:
            parts.append(f"лимит {format_bytes(total)}")
        elif used is not None:
            parts.append(f"израсходовано {format_bytes(used)}")

        if self.expires_at:
            parts.append(f"до {format_date(self.expires_at)}")
        return " · ".join(parts)


@dataclass(slots=True)
class Subscription:
    """Одна подписка и всё, что о ней известно."""

    url: str
    title: str = ""
    updated_at: float = 0.0
    server_count: int = 0
    usage: SubscriptionUsage = field(default_factory=SubscriptionUsage)

    @property
    def key(self) -> str:
        """По адресу отличаем подписки друг от друга. Имя может меняться."""
        return normalize_url(self.url)

    def display_title(self) -> str:
        title = str(self.title or "").strip()
        if title:
            return title
        # Без имени показываем узел адреса: «sub.example.org» понятнее,
        # чем полная ссылка с ключом на пол-экрана.
        return host_of(self.url) or "Подписка"


def normalize_url(url: str) -> str:
    return str(url or "").strip()


def host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return str(urlparse(str(url or "")).hostname or "")
    except Exception:
        return ""


def format_bytes(value: int | None) -> str:
    """Человеческий размер. Подписки меряют гигабайтами, не байтами."""
    if value is None:
        return "—"
    size = float(value)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024 or unit == "ТБ":
            # Целые до мегабайт, дробные дальше: «312.4 ГБ» читается, а
            # «312.4 КБ» — лишняя точность.
            if unit in ("Б", "КБ", "МБ"):
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


def format_date(timestamp: int | None) -> str:
    if not timestamp:
        return "—"
    try:
        return time.strftime("%d.%m.%Y", time.localtime(int(timestamp)))
    except Exception:
        return "—"


def parse_usage(header_value: str) -> SubscriptionUsage:
    """Разбирает `subscription-userinfo`.

    Терпимо к мусору: заголовок — обычай, а не стандарт, и панели пишут
    его по-разному. Чего не поняли — того нет, и на показ это не влияет.
    """
    values: dict[str, int] = {}
    for chunk in str(header_value or "").split(";"):
        name, _, raw = chunk.partition("=")
        name = name.strip().lower()
        raw = raw.strip()
        if not name or not raw:
            continue
        try:
            values[name] = int(float(raw))
        except (TypeError, ValueError):
            continue

    return SubscriptionUsage(
        upload=values.get("upload"),
        download=values.get("download"),
        # Ноль в total означает «без лимита», а не «нисколько». Показывать
        # «0 из 0» было бы неправдой, поэтому такой total отбрасываем.
        total=values.get("total") or None,
        expires_at=values.get("expire") or None,
    )


def store_path(root: str | Path) -> Path:
    return Path(root) / STORE_NAME


def load_subscriptions(root: str | Path) -> list[Subscription]:
    path = store_path(root)
    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Битый файл не должен ронять страницу: подписки — сведения
        # вспомогательные, серверы лежат отдельно и работают без них.
        return []

    items = raw.get("subscriptions") if isinstance(raw, dict) else raw
    result: list[Subscription] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = normalize_url(item.get("url"))
        if not url:
            continue
        usage_raw = item.get("usage") or {}
        result.append(
            Subscription(
                url=url,
                title=str(item.get("title") or ""),
                updated_at=float(item.get("updated_at") or 0),
                server_count=int(item.get("server_count") or 0),
                usage=SubscriptionUsage(
                    upload=usage_raw.get("upload"),
                    download=usage_raw.get("download"),
                    total=usage_raw.get("total"),
                    expires_at=usage_raw.get("expires_at"),
                ),
            )
        )
    return result


def save_subscriptions(root: str | Path, subscriptions) -> tuple[bool, str]:
    path = store_path(root)
    payload = {
        "version": FORMAT_VERSION,
        "subscriptions": [
            {
                "url": item.url,
                "title": item.title,
                "updated_at": item.updated_at,
                "server_count": item.server_count,
                "usage": {
                    "upload": item.usage.upload,
                    "download": item.usage.download,
                    "total": item.usage.total,
                    "expires_at": item.usage.expires_at,
                },
            }
            for item in (subscriptions or ())
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return (True, "")
    except Exception as exc:
        return (False, f"Не удалось сохранить подписки: {exc}")


def upsert(subscriptions, subscription: Subscription) -> list[Subscription]:
    """Добавляет подписку или обновляет существующую с тем же адресом."""
    result = [item for item in (subscriptions or ()) if item.key != subscription.key]
    result.append(subscription)
    return result


def remove(subscriptions, url: str) -> list[Subscription]:
    key = normalize_url(url)
    return [item for item in (subscriptions or ()) if item.key != key]


def find(subscriptions, url: str) -> Subscription | None:
    key = normalize_url(url)
    for item in subscriptions or ():
        if item.key == key:
            return item
    return None


def describe_updated(timestamp: float) -> str:
    """«Обновлено» человеческим языком.

    Точное время здесь лишнее: важно, свежий список или ему неделя.
    """
    if not timestamp:
        return "ещё не обновлялась"

    delta = time.time() - float(timestamp)
    if delta < 60:
        return "обновлено только что"
    if delta < 3600:
        return f"обновлено {int(delta // 60)} мин назад"
    if delta < 86400:
        return f"обновлено {int(delta // 3600)} ч назад"
    return f"обновлено {time.strftime('%d.%m.%Y', time.localtime(timestamp))}"


def group_by_subscription(profiles, subscriptions) -> list[tuple[str, str, list[int]]]:
    """Делит серверы на группы по подпискам.

    Возвращает тройки «ключ, заголовок, номера серверов в исходном
    списке». Ключ — адрес подписки, по нему группу отличают от соседних:
    заголовок для этого не годится, в нём меняется и трафик, и время
    обновления, а свёрнутой группа должна оставаться после любого из
    этих изменений.

    Порядок групп — порядок первого появления: подписка, добавленная
    первой, и в списке идёт первой, а не прыгает при каждом обновлении.

    Пустой заголовок означает, что подписывать нечего: группа
    единственная и ни к какой подписке не относится. Рисовать шапку над
    списком, у которого нет соседей, значит тратить строку впустую.
    """
    order: list[str] = []
    buckets: dict[str, list[int]] = {}
    for position, profile in enumerate(profiles or ()):
        key = normalize_url(getattr(profile, "source", ""))
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(position)

    if not order:
        return []
    if len(order) == 1 and not order[0]:
        return [("", "", buckets[order[0]])]

    result: list[tuple[str, str, list[int]]] = []
    for key in order:
        members = buckets[key]
        if not key:
            result.append((key, f"Мои серверы · {len(members)}", members))
            continue

        info = find(subscriptions, key)
        if info is None:
            # Серверы с меткой подписки есть, а записи о подписке нет:
            # так выглядит список, добавленный до того, как подписки
            # начали сохраняться. Узла адреса хватает, чтобы группа была
            # узнаваемой.
            result.append((key, f"{host_of(key) or 'Подписка'} · {len(members)}", members))
            continue

        parts = [info.display_title(), f"{len(members)} серверов"]
        usage = info.usage.describe()
        if usage:
            parts.append(usage)
        parts.append(describe_updated(info.updated_at))
        result.append((key, " · ".join(parts), members))

    return result


__all__ = [
    "group_by_subscription",
    "FORMAT_VERSION",
    "PROFILE_TITLE_HEADER",
    "STORE_NAME",
    "USERINFO_HEADER",
    "Subscription",
    "SubscriptionUsage",
    "describe_updated",
    "find",
    "format_bytes",
    "format_date",
    "host_of",
    "load_subscriptions",
    "normalize_url",
    "parse_usage",
    "remove",
    "save_subscriptions",
    "store_path",
    "upsert",
]
