"""Запущен ли Telegram Desktop.

Прокси поднимается ради одного действия: открыть ссылку `tg://`, чтобы
мессенджер сам предложил подключиться. Если Telegram не запущен, ссылку
некому обработать — Windows либо промолчит, либо предложит выбрать
программу из списка. Прокси при этом останется висеть на порту, а
человек будет думать, что всё сработало.

Поэтому перед запуском спрашиваем систему, есть ли процесс. Ответ «нет»
не ошибка приложения: это ситуация, о которой надо сказать словами и не
делать бессмысленную работу.

## Имена процессов

У Telegram Desktop их несколько. Официальная сборка — `Telegram.exe`.
Портативные и магазинные сборки встречаются под `Telegram Desktop.exe`,
а форк Ayugram и сборки из Microsoft Store — под своими именами. Список
здесь открытый: лишнее имя стоит одного сравнения строк, а пропущенное —
ложного «у вас не запущен Telegram» у человека, у которого он запущен.

Веб-версию в браузере поймать нельзя, и это честное ограничение:
процесса с отличимым именем у неё нет. Для неё прокси всё равно
бесполезен — ссылку `tg://` браузер не обработает.
"""

from __future__ import annotations


#: Имена процессов, под которыми встречается Telegram Desktop.
TELEGRAM_PROCESS_NAMES: tuple[str, ...] = (
    "telegram.exe",
    "telegram desktop.exe",
    "telegramdesktop.exe",
    "ayugram.exe",
    "64gram.exe",
    "kotatogram.exe",
    "unigram.exe",
)


#: Что сказать человеку, когда мессенджер не запущен.
NOT_RUNNING_MESSAGE = (
    "Telegram Desktop не запущен, поэтому прокси не поднимался и "
    "переадресации не было. Откройте Telegram и включите обход заново."
)

#: Что сказать перед переадресацией.
REDIRECT_NOTICE = (
    "Сейчас откроется Telegram и предложит включить прокси net67 — "
    "подтвердите в его окне."
)


def normalize_process_name(value: str) -> str:
    """Имя процесса в сравнимом виде: без пути, регистра и пробелов."""
    text = str(value or "").strip().strip('"').replace("/", "\\")
    if "\\" in text:
        text = text.rsplit("\\", 1)[-1]
    return text.strip().lower()


def is_telegram_process(name: str) -> bool:
    """Похоже ли имя процесса на Telegram Desktop."""
    return normalize_process_name(name) in TELEGRAM_PROCESS_NAMES


def is_telegram_running(*, iter_processes=None) -> bool:
    """Есть ли среди запущенных процессов Telegram Desktop.

    `iter_processes` подменяется в тестах: настоящий обход процессов
    доступен только на Windows, а правило «имя из списка — значит
    запущен» проверять надо везде.

    Неизвестность трактуется как «запущен». Это не небрежность: если
    перечислить процессы не удалось, честнее попробовать поднять прокси
    и дать человеку увидеть результат, чем отказать со ссылкой на сбой,
    которого он не совершал.
    """
    if iter_processes is None:
        try:
            from utils.process_killer import iter_process_records_winapi

            iter_processes = iter_process_records_winapi
        except Exception:
            return True

    try:
        for record in iter_processes():
            name = record[1] if isinstance(record, (tuple, list)) else record
            if is_telegram_process(name):
                return True
    except Exception:
        return True

    return False


__all__ = [
    "NOT_RUNNING_MESSAGE",
    "REDIRECT_NOTICE",
    "TELEGRAM_PROCESS_NAMES",
    "is_telegram_process",
    "is_telegram_running",
    "normalize_process_name",
]
