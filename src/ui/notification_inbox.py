"""Колокольчик уведомлений: что всплывает, а что тихо копится.

Раньше каждое уведомление вылезало плашкой поверх окна — и ошибки из
журнала, и проверки при запуске, и ответы на нажатия. У человека на
первом же запуске под OneDrive сыпались две плашки об одном и том же,
перекрывая мастер, а в ошибке подбора стратегии на экране стоял
Python-traceback на английском. Руководителю это ничего не говорит,
зато пугает.

Теперь всплывает только ответ на то, что человек сделал сам: нажал
«Включить» — и не вышло. Всё фоновое — ошибки из журнала, проверки
при запуске, синхронизация — копится за колокольчиком в заголовке окна.
Счётчик на нём считает только предупреждения и ошибки: «обновлений нет»
историю пополняет, но внимания не требует.

Модуль чистый, без Qt: правило разделения проверяется тестами.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

__all__ = [
    "INBOX_LIMIT",
    "InboxEntry",
    "NotificationInbox",
    "human_content",
    "human_title",
    "routes_to_inbox",
]

#: Сколько записей держит история. Старые вытесняются: это не журнал, а
#: «что случилось за сеанс», а полный журнал лежит в logs.
INBOX_LIMIT = 60

_BACKGROUND_PREFIXES = ("global_logger", "startup.", "deferred.")
_BACKGROUND_SOURCES = frozenset({"startup", "presets.remote_sync", "installation.repair"})
_ATTENTION_LEVELS = frozenset({"warning", "error"})
_SERVICE_PREFIX_RE = re.compile(r"^\[[^\[\]]{1,32}\]\s*")
_LEVEL_WORD_RE = re.compile(r"^(ERROR|WARNING|CRITICAL|INFO)\s*:\s*", re.IGNORECASE)


def routes_to_inbox(payload: dict) -> bool:
    """Уходит ли уведомление в колокольчик, а не всплывает.

    Фоновое — то, что программа сделала или заметила сама. Ответ на
    кнопку внутри уведомления (источник с «.action» на конце) — уже
    действие человека, и он ждёт увидеть результат сразу.
    """
    source = str(payload.get("source") or "").strip()
    if source.endswith(".action"):
        return False
    return source in _BACKGROUND_SOURCES or source.startswith(_BACKGROUND_PREFIXES)


def human_title(payload: dict) -> str:
    source = str(payload.get("source") or "")
    title = str(payload.get("title") or "").strip()
    if source == "global_logger":
        # «Ошибка» над английской строкой из кода ничего не объясняет.
        return "Техническая ошибка"
    return title or {
        "success": "Готово",
        "info": "Информация",
        "warning": "Предупреждение",
        "error": "Ошибка",
    }.get(str(payload.get("level") or "info"), "Уведомление")


def human_content(text: str) -> str:
    """Текст без служебных префиксов и без traceback.

    Traceback нужен разработчику, и он остаётся в журнале целиком. На
    экране — только первая строка, то есть сама суть.
    """
    raw = str(text or "")
    head = raw.split("Traceback (most recent call last)", 1)[0]
    lines = [line.strip() for line in head.splitlines() if line.strip()]
    if not lines:
        return "Подробности — в журнале программы"
    first = lines[0]
    while True:
        trimmed = _SERVICE_PREFIX_RE.sub("", first, count=1).strip()
        trimmed = _LEVEL_WORD_RE.sub("", trimmed, count=1).strip()
        if trimmed == first:
            break
        first = trimmed
    return first


@dataclass(slots=True)
class InboxEntry:
    level: str
    title: str
    content: str
    source: str
    buttons: tuple[dict, ...] = ()
    count: int = 1
    unread: bool = True
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.level, self.title, self.content)

    @property
    def needs_attention(self) -> bool:
        return self.level in _ATTENTION_LEVELS


class NotificationInbox:
    """История уведомлений сеанса. Одинаковые склеиваются в одну запись «×N»."""

    def __init__(self, limit: int = INBOX_LIMIT) -> None:
        self._limit = max(1, int(limit))
        self._entries: list[InboxEntry] = []

    def add(self, payload: dict, *, seen: bool = False, now: float | None = None) -> InboxEntry:
        """Кладёт уведомление наверх. ``seen`` — человек его уже видел плашкой."""
        stamp = time.time() if now is None else float(now)
        level = str(payload.get("level") or "info").strip().lower()
        entry = InboxEntry(
            level=level,
            title=human_title(payload),
            content=human_content(str(payload.get("content") or "")),
            source=str(payload.get("source") or ""),
            buttons=tuple(payload.get("buttons") or ()),
            unread=not seen and level in _ATTENTION_LEVELS,
            first_seen=stamp,
            last_seen=stamp,
        )
        for index, existing in enumerate(self._entries):
            if existing.key == entry.key:
                existing.count += 1
                existing.last_seen = stamp
                existing.unread = existing.unread or entry.unread
                if entry.buttons:
                    existing.buttons = entry.buttons
                self._entries.insert(0, self._entries.pop(index))
                return existing
        self._entries.insert(0, entry)
        del self._entries[self._limit :]
        return entry

    def entries(self) -> list[InboxEntry]:
        return list(self._entries)

    def unread_count(self) -> int:
        return sum(1 for entry in self._entries if entry.unread)

    def worst_unread_level(self) -> str:
        levels = {entry.level for entry in self._entries if entry.unread}
        if "error" in levels:
            return "error"
        if "warning" in levels:
            return "warning"
        return ""

    def mark_all_read(self) -> None:
        for entry in self._entries:
            entry.unread = False

    def remove(self, entry: InboxEntry) -> None:
        self._entries = [item for item in self._entries if item is not entry]

    def clear(self) -> None:
        self._entries.clear()
