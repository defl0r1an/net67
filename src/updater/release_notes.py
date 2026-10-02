"""История выпусков для окна «Доступно обновление» и «Что нового».

Раньше об обновлении спрашивало окошко в одну строку: «Выпущена версия
X. Установить?» — что в ней нового, человек узнать не мог. Теперь окно
показывает изменения всех версий, которые он пропустил, и пару
предыдущих — раздел «Ранее».

Здесь нет ни Qt, ни сети: список выпусков приходит снаружи (его отдаёт
источник обновлений), а модуль решает, что показать, и собирает текст.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from typing import Any

#: Сколько прошлых выпусков добавить под заголовком «Ранее».
#:
#: Описание выпуска — рассказ обо всём, что изменилось с прошлого; десять
#: таких подряд никто читать не станет, а два-три дают понять, куда
#: программа движется.
EARLIER_LIMIT = 3

_MONTHS_RU = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
_MONTHS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

_URL_RE = re.compile(r"(https?://[^\s<>\"']+)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")
#: Строки, которые GitHub дописывает в автоматическое описание выпуска.
#: Человеку они ничего не говорят: это ссылка на сравнение коммитов.
_GENERATED_LINE_RE = re.compile(r"^\s*(\*\*Full Changelog\*\*:.*|##\s*What's Changed\s*|##\s*New Contributors\s*)$", re.IGNORECASE)


def version_key(version: object) -> tuple[int, ...]:
    """Числовой ключ версии: «0.13.67» → (0, 13, 67). ValueError, если не числа."""
    text = str(version or "").strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    parts = text.split(".")
    if len(parts) < 2 or any(not part.isdigit() for part in parts):
        raise ValueError(f"неверная запись версии: {version!r}")
    numbers = [int(part) for part in parts]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers)


def release_page_url(version: object, repo: str) -> str:
    """Страница выпуска на GitHub; пусто, если репозиторий не задан."""
    repo = str(repo or "").strip().strip("/")
    text = str(version or "").strip().lstrip("vV")
    if not repo or not text:
        return ""
    return f"https://github.com/{repo}/releases/tag/v{text}"


def clean_release_notes(notes: object) -> str:
    """Описание выпуска без строк, которые GitHub дописал сам."""
    lines = [line for line in str(notes or "").replace("\r\n", "\n").split("\n") if not _GENERATED_LINE_RE.match(line)]
    return "\n".join(lines).strip()


def build_history(
    releases: Iterable[Mapping[str, Any]],
    *,
    current_version: str,
    target_version: str,
    repo: str = "",
    earlier_limit: int = EARLIER_LIMIT,
) -> tuple[dict[str, Any], ...]:
    """Что показать в окне: от новых выпусков к старым.

    Выпуски новее установленной версии и не новее предлагаемой попадают
    все и помечены ``is_new``; под ними — до ``earlier_limit`` предыдущих.
    Версии новее предлагаемой не показываются: окно про то обновление,
    которое сейчас поставится.
    """
    try:
        top = version_key(target_version)
    except ValueError:
        return ()
    try:
        current = version_key(current_version)
    except ValueError:
        current = None

    by_key: dict[tuple[int, ...], dict[str, Any]] = {}
    for item in releases or ():
        if not isinstance(item, Mapping):
            continue
        try:
            key = version_key(item.get("version"))
        except ValueError:
            continue
        if key > top or key in by_key:
            continue
        version = str(item.get("version") or "").strip().lstrip("vV")
        by_key[key] = {
            "version": version,
            "notes": clean_release_notes(item.get("release_notes") or item.get("notes")),
            "published_at": str(item.get("published_at") or ""),
            "url": str(item.get("url") or "") or release_page_url(version, repo),
            "is_new": current is None or key > current,
        }
    ordered = [by_key[key] for key in sorted(by_key, reverse=True)]
    fresh = [item for item in ordered if item["is_new"]]
    earlier = [item for item in ordered if not item["is_new"]][: max(0, int(earlier_limit))]
    return tuple(fresh + earlier)


def count_new_versions(history: Iterable[Mapping[str, Any]]) -> int:
    return sum(1 for item in history or () if isinstance(item, Mapping) and item.get("is_new", True))


def versions_word(count: int) -> str:
    """«1 версию», «2 версии», «5 версий»."""
    number = abs(int(count))
    if number % 10 == 1 and number % 100 != 11:
        return "версию"
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return "версии"
    return "версий"


def format_release_date(published_at: object, language: str = "ru") -> str:
    """«2026-10-02T08:19:51Z» → «2 октября 2026». Пусто, если не разобрать."""
    text = str(published_at or "").strip()
    if len(text) < 10:
        return ""
    try:
        year, month, day = int(text[0:4]), int(text[5:7]), int(text[8:10])
    except ValueError:
        return ""
    if not 1 <= month <= 12:
        return ""
    if str(language or "").lower().startswith("en"):
        return f"{_MONTHS_EN[month - 1]} {day}, {year}"
    return f"{day} {_MONTHS_RU[month - 1]} {year}"


def _inline(text: str, accent_hex: str) -> str:
    """Экранирует строку и возвращает ей ссылки, **жирное** и `код`."""
    escaped = html.escape(text)

    def link(match: re.Match) -> str:
        url, tail = match.group(1), ""
        while url and url[-1] in ".,;:!?)":
            url, tail = url[:-1], url[-1] + tail
        return f'<a href="{url}" style="color: {accent_hex}; text-decoration: none;">{url}</a>{tail}'

    escaped = _URL_RE.sub(link, escaped)
    escaped = _BOLD_RE.sub(r"<b>\1</b>", escaped)
    return _CODE_RE.sub(r"<span style='font-family: Consolas, monospace;'>\1</span>", escaped)


def notes_html(notes: object, *, accent_hex: str) -> str:
    """Текст одного выпуска: «- …» — список, «# …» — подзаголовок, остальное — абзацы."""
    blocks: list[str] = []
    items: list[str] = []

    def flush() -> None:
        if items:
            blocks.append("<ul style='margin: 2px 0 6px 0;'>" + "".join(items) + "</ul>")
            items.clear()

    for raw in str(notes or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        bullet = next((line[len(mark):].strip() for mark in ("- ", "* ", "• ", "— ", "– ") if line.startswith(mark)), None)
        if bullet is not None:
            items.append(f"<li style='margin-bottom: 3px;'>{_inline(bullet, accent_hex)}</li>")
        elif raw[:1] in (" ", "\t") and items:
            # Продолжение пункта списка, перенесённое на новую строку.
            items[-1] = items[-1][: -len("</li>")] + " " + _inline(line, accent_hex) + "</li>"
        else:
            flush()
            if line.startswith("#"):
                blocks.append(f"<p style='margin: 8px 0 2px 0;'><b>{_inline(line.lstrip('#').strip(), accent_hex)}</b></p>")
            else:
                blocks.append(f"<p style='margin: 2px 0 4px 0;'>{_inline(line, accent_hex)}</p>")
    flush()
    return "".join(blocks)


def history_html(
    history: Iterable[Mapping[str, Any]],
    *,
    accent_hex: str,
    muted_hex: str,
    language: str = "ru",
    empty_text: str = "Описание изменений не опубликовано.",
    new_badge_text: str = "новое",
    earlier_text: str = "Ранее",
) -> str:
    """Выпуски подряд: версия, дата и текст. Новые — ярко, «Ранее» — приглушённо."""
    entries = [item for item in history or () if isinstance(item, Mapping)]
    fresh = [item for item in entries if item.get("is_new", True)]
    earlier = [item for item in entries if not item.get("is_new", True)]
    mixed = bool(fresh) and bool(earlier)

    def block(item: Mapping[str, Any], *, is_new: bool) -> str:
        version = html.escape(str(item.get("version") or ""))
        colour, size = (accent_hex, 15) if is_new else (muted_hex, 13)
        header = f"<span style='font-size: {size}pt; font-weight: 600; color: {colour};'>v{version}</span>"
        if is_new and mixed:
            header += f"&nbsp;&nbsp;<span style='color: {accent_hex}; font-size: 9pt; font-weight: 600;'>{html.escape(new_badge_text)}</span>"
        date = html.escape(format_release_date(item.get("published_at"), language))
        if date:
            header += f"<span style='color: {muted_hex};'>&nbsp;&nbsp;·&nbsp;&nbsp;{date}</span>"
        body = notes_html(item.get("notes"), accent_hex=accent_hex if is_new else muted_hex)
        if not body:
            body = f"<p style='color: {muted_hex};'>{html.escape(empty_text)}</p>"
        tone = "" if is_new else f" color: {muted_hex};"
        return f"<div style='margin-bottom: 18px;{tone}'><p style='margin: 0 0 6px 0;'>{header}</p>{body}</div>"

    parts = [block(item, is_new=True) for item in fresh]
    if earlier:
        if fresh:
            parts.append(
                f"<p style='margin: 10px 0 12px 0; font-size: 11pt; font-weight: 600; color: {muted_hex};'>"
                f"{html.escape(earlier_text)}</p>"
            )
        parts.extend(block(item, is_new=not fresh) for item in earlier)
    return "".join(parts)


__all__ = [
    "EARLIER_LIMIT",
    "build_history",
    "clean_release_notes",
    "count_new_versions",
    "format_release_date",
    "history_html",
    "notes_html",
    "release_page_url",
    "version_key",
    "versions_word",
]
