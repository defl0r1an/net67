"""Приведение строки лога к читаемому виду.

Лог писали шесть лет и все по-разному. В поле уровня оказалось всё
подряд: и настоящие уровни, и значки («⚠ WARNING», «❌ ERROR»), и вообще
не уровни, а откуда пришло сообщение («📱 TG», «🔄 CACHE», «POOL»).
Замер по проекту: 86 вызовов с «❌ ERROR», 35 с «🔄 RELEASE», 31 с
«⚠ WARNING», 26 с «🔁 UPDATE», и так далее — больше двух сотен мест.

Править двести мест вручную бессмысленно: следующая правка добавит
двести первое. Поэтому разбор один и здесь, на входе в лог.

## Что делает разбор

Отделяет уровень от источника. `«📱 TG»` — это не уровень, а метка
подсистемы: она уходит в поле компонента, а уровнем становится обычный
INFO. `«🔁❌ ERROR»` — это ERROR с двумя значками, значки снимаются.

Убирает значки из самого сообщения. Строка «✅ Готово» и строка
«Готово» несут одно и то же, но первую нельзя ни найти поиском, ни
прочитать вслух программе экранного доступа.

## Чего разбор не делает

Не меняет смысл и не сокращает текст. Задача — снять украшения, а не
переписать сообщение: то, что человек напишет в вызове, он и увидит.
"""

from __future__ import annotations

import re
import unicodedata


#: Настоящие уровни. Всё остальное в поле уровня — источник сообщения.
KNOWN_LEVELS: frozenset[str] = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)

#: Уровни-синонимы. Слева то, что пишут в вызовах, справа настоящий.
#:
#: SUCCESS и START — про исход и про этап, а не про важность. В логе
#: они всегда были обычными сообщениями, поэтому и становятся INFO.
LEVEL_ALIASES: dict[str, str] = {
    "SUCCESS": "INFO",
    "OK": "INFO",
    "START": "INFO",
    "DIAG": "DEBUG",
    "TRACE": "DEBUG",
    "WARN": "WARNING",
    "FATAL": "CRITICAL",
}

#: Уровень для сообщений, у которых его не разобрать.
DEFAULT_LEVEL = "INFO"

#: Диапазоны, которые считаем украшениями.
#:
#: Берём по классу символа Unicode, а не списком: перечислять эмодзи
#: поимённо — это гонка, которую не выиграть. So = «символ, прочее»,
#: туда попадают и эмодзи, и стрелки, и галочки.
_DECORATION_CATEGORIES = frozenset({"So", "Sk", "Cn"})

_SPACES = re.compile(r"[ \t]{2,}")


def strip_decorations(text: str) -> str:
    """Снимает значки и лишние пробелы, оставляя текст."""
    raw = str(text or "")
    kept = [
        char
        for char in raw
        if unicodedata.category(char) not in _DECORATION_CATEGORIES
    ]
    cleaned = "".join(kept)
    # Значок обычно стоял с пробелом, после снятия остаётся двойной.
    cleaned = _SPACES.sub(" ", cleaned)
    return cleaned.strip()


def split_level(value: str) -> tuple[str, str]:
    """Делит поле уровня на (уровень, источник).

    Источник — пустая строка, если в поле был обычный уровень.

    >>> split_level("❌ ERROR")
    ('ERROR', '')
    >>> split_level("📱 TG")
    ('INFO', 'TG')
    """
    cleaned = strip_decorations(value).upper()
    if not cleaned:
        return (DEFAULT_LEVEL, "")

    words = cleaned.split()

    # Уровень может стоять не первым: «🔁 UPDATE» это источник, а
    # «🔁❌ ERROR» — уровень. Ищем среди слов известное имя.
    for word in words:
        canonical = LEVEL_ALIASES.get(word, word)
        if canonical in KNOWN_LEVELS:
            source = " ".join(other for other in words if other != word)
            return (canonical, source)

    return (DEFAULT_LEVEL, cleaned)


def normalize(message: str, level: str, component: str | None = None) -> tuple[str, str, str]:
    """Готовит запись к выводу. Возвращает (сообщение, уровень, компонент).

    Компонент из поля уровня не затирает переданный явно: явный
    указывает вызывающий код, и он точнее.
    """
    parsed_level, source = split_level(level)
    resolved_component = str(component or "").strip() or source
    return (strip_decorations(message), parsed_level, resolved_component)


__all__ = [
    "DEFAULT_LEVEL",
    "KNOWN_LEVELS",
    "LEVEL_ALIASES",
    "normalize",
    "split_level",
    "strip_decorations",
]
