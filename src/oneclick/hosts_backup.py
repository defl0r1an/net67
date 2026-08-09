"""Резервная копия системного файла hosts.

В приложении не было бэкапа содержимого hosts — только восстановление прав
(`restore_hosts_permissions`). Для «одной кнопки» этого мало: правка hosts
переживает и закрытие, и удаление приложения, поэтому без копии откат
невозможен в принципе.

Храним две копии:

* ``hosts.net67.original`` — самое первое состояние, до любых наших правок.
  Пишется один раз и больше никогда не перезаписывается. Это то, к чему
  ведёт кнопка «Вернуть как было» в расширенных настройках.
* ``hosts.net67.bak`` — состояние перед последним включением. Используется
  для автоматического отката, если включение сорвалось.

Функции принимают операции чтения и записи снаружи, чтобы модуль можно
было тестировать без доступа к системному файлу.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

ORIGINAL_BACKUP_NAME = "hosts.net67.original"
LAST_BACKUP_NAME = "hosts.net67.bak"


def _backup_dir(root: Path | str) -> Path:
    return Path(root)


def original_backup_path(root: Path | str) -> Path:
    return _backup_dir(root) / ORIGINAL_BACKUP_NAME


def last_backup_path(root: Path | str) -> Path:
    return _backup_dir(root) / LAST_BACKUP_NAME


def create_backup(
    *,
    root: Path | str,
    read_hosts: Callable[[], str | None],
) -> tuple[bool, str]:
    """Сохраняет текущий hosts перед правкой.

    Первый вызов дополнительно создаёт неприкосновенную копию original.
    """
    try:
        content = read_hosts()
    except Exception as exc:
        return (False, f"Не удалось прочитать hosts: {exc}")

    if content is None:
        return (False, "Не удалось прочитать hosts")

    try:
        directory = _backup_dir(root)
        directory.mkdir(parents=True, exist_ok=True)

        original = original_backup_path(root)
        if not original.exists():
            # Пишем только один раз: если приложение уже правило hosts,
            # текущее содержимое — не оригинал, и перезапись затёрла бы
            # единственный шанс вернуть исходное состояние.
            original.write_text(content, encoding="utf-8")

        last_backup_path(root).write_text(content, encoding="utf-8")
    except Exception as exc:
        return (False, f"Не удалось сохранить копию hosts: {exc}")

    return (True, "Копия hosts сохранена")


def restore_backup(
    *,
    root: Path | str,
    write_hosts: Callable[[str], bool],
    use_original: bool = False,
) -> tuple[bool, str]:
    """Возвращает hosts из копии.

    use_original=True — вернуть самое первое состояние (кнопка «Вернуть
    как было»). По умолчанию откатывается последнее включение.
    """
    path = original_backup_path(root) if use_original else last_backup_path(root)

    if not path.exists():
        return (False, "Копия hosts не найдена")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        return (False, f"Не удалось прочитать копию hosts: {exc}")

    try:
        if not write_hosts(content):
            return (False, "Не удалось записать hosts")
    except Exception as exc:
        return (False, f"Не удалось записать hosts: {exc}")

    return (True, "Файл hosts восстановлен")


def has_backup(root: Path | str, *, original: bool = False) -> bool:
    path = original_backup_path(root) if original else last_backup_path(root)
    try:
        return path.exists()
    except Exception:
        return False


__all__ = [
    "LAST_BACKUP_NAME",
    "ORIGINAL_BACKUP_NAME",
    "create_backup",
    "has_backup",
    "last_backup_path",
    "original_backup_path",
    "restore_backup",
]
