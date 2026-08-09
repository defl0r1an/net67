"""Логика системы конфигураций.

Три задачи: именованные наборы настроек, перенос настроек между машинами
и безопасная правка файла настроек.

Главное здесь — разделение полей на три класса. Настройки приложения
содержат не только предпочтения:

* **Секреты.** Пароль апстрим-прокси, логин и секрет MTProxy. Выгрузить
  их в файл и переслать коллеге — это утечка учётных данных, поэтому по
  умолчанию они вырезаются, а включаются только явным согласием.

* **Машинно-зависимое.** Геометрия окна, идентификатор устройства,
  подпись состояния файла hosts. Переносить это на другой компьютер
  бессмысленно и вредно: чужая геометрия окна на другом разрешении
  выкинет окно за пределы экрана.

* **Переносимое.** Всё остальное — то, ради чего перенос и делается.

Модуль чистый: ни файлов, ни Qt.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

#: Формат файла конфигурации. Повышается при несовместимых изменениях.
CONFIG_FORMAT_VERSION = 1

#: Разделы, которые никогда не переносятся между машинами.
MACHINE_SPECIFIC_SECTIONS: frozenset[str] = frozenset(
    {
        "window",   # геометрия окна конкретного экрана
        "premium",  # идентификатор устройства, остался от убранной подписки
    }
)

#: Отдельные поля внутри разделов, которые тоже не переносятся.
MACHINE_SPECIFIC_FIELDS: dict[str, frozenset[str]] = {
    "hosts": frozenset({"bootstrap_signature", "active_domains"}),
    "dns": frozenset({"dns_crash_count"}),
}

#: Поля с учётными данными. Вырезаются, если явно не запрошено обратное.
SECRET_FIELDS: dict[str, frozenset[str]] = {
    "telegram_proxy": frozenset({"upstream_user", "upstream_pass", "mtproxy_secret"}),
}

#: Чем заменяется вырезанный секрет, чтобы структура файла не поехала.
REDACTED_PLACEHOLDER = ""


@dataclass(frozen=True, slots=True)
class ExportOptions:
    include_secrets: bool = False
    include_machine_specific: bool = False
    #: Разделы, которые нужно выгрузить. Пусто — все переносимые.
    sections: frozenset[str] = frozenset()


@dataclass(slots=True)
class ExportReport:
    """Что именно попало в файл и что было вырезано."""

    sections: list[str] = field(default_factory=list)
    redacted: list[str] = field(default_factory=list)
    skipped_sections: list[str] = field(default_factory=list)

    @property
    def has_redactions(self) -> bool:
        return bool(self.redacted)


def portable_sections(settings: dict) -> list[str]:
    """Разделы, пригодные для переноса."""
    return sorted(
        name
        for name in (settings or {})
        if name != "version" and name not in MACHINE_SPECIFIC_SECTIONS
    )


def build_export(
    settings: dict,
    options: ExportOptions | None = None,
) -> tuple[dict, ExportReport]:
    """Готовит содержимое файла конфигурации."""
    options = options or ExportOptions()
    source = copy.deepcopy(dict(settings or {}))
    report = ExportReport()

    wanted = set(options.sections) if options.sections else None
    payload: dict = {}

    for name, value in source.items():
        if name == "version":
            continue

        if name in MACHINE_SPECIFIC_SECTIONS and not options.include_machine_specific:
            report.skipped_sections.append(name)
            continue

        if wanted is not None and name not in wanted:
            continue

        section = copy.deepcopy(value)

        if isinstance(section, dict) and not options.include_machine_specific:
            for dropped in MACHINE_SPECIFIC_FIELDS.get(name, ()):  # noqa: B007
                section.pop(dropped, None)

        if isinstance(section, dict) and not options.include_secrets:
            for secret in SECRET_FIELDS.get(name, ()):
                if section.get(secret):
                    section[secret] = REDACTED_PLACEHOLDER
                    report.redacted.append(f"{name}.{secret}")

        payload[name] = section
        report.sections.append(name)

    report.sections.sort()
    report.redacted.sort()
    report.skipped_sections.sort()

    document = {
        "format": "net67-config",
        "format_version": CONFIG_FORMAT_VERSION,
        "settings_version": int(source.get("version") or 1),
        "contains_secrets": bool(options.include_secrets and report.sections),
        "sections": payload,
    }
    return document, report


@dataclass(slots=True)
class ImportReport:
    ok: bool
    message: str = ""
    sections: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)


def validate_document(document: object) -> tuple[bool, str]:
    """Проверяет, что перед нами файл конфигурации, а не что-то ещё."""
    if not isinstance(document, dict):
        return (False, "Файл не содержит конфигурацию")
    if document.get("format") != "net67-config":
        return (False, "Это не файл конфигурации net67")

    try:
        version = int(document.get("format_version") or 0)
    except (TypeError, ValueError):
        return (False, "Не удалось определить версию файла")

    if version <= 0:
        return (False, "Не удалось определить версию файла")
    if version > CONFIG_FORMAT_VERSION:
        return (
            False,
            f"Файл создан более новой версией приложения (формат {version}). "
            "Обновите net67.",
        )
    if not isinstance(document.get("sections"), dict):
        return (False, "В файле нет ни одного раздела настроек")

    return (True, "")


def build_import_patch(
    document: dict,
    *,
    current: dict,
    keep_machine_specific: bool = True,
) -> tuple[dict, ImportReport]:
    """Накладывает разделы из файла на текущие настройки.

    Возвращает полный словарь настроек — его всё равно обязан пропустить
    через себя normalize_settings, иначе кривой или враждебный файл
    испортит состояние приложения.
    """
    ok, message = validate_document(document)
    if not ok:
        return (dict(current or {}), ImportReport(ok=False, message=message))

    result = copy.deepcopy(dict(current or {}))
    report = ImportReport(ok=True)

    for name, value in dict(document.get("sections") or {}).items():
        if keep_machine_specific and name in MACHINE_SPECIFIC_SECTIONS:
            report.ignored.append(name)
            continue
        if name not in result:
            # Неизвестный раздел молча пропускаем: нормализация всё равно
            # его выбросит, а пользователю честнее показать список.
            report.ignored.append(name)
            continue

        if isinstance(value, dict) and isinstance(result.get(name), dict):
            merged = copy.deepcopy(result[name])
            for key, item in value.items():
                # Пустой секрет означает «в файле его вырезали» —
                # затирать им рабочий пароль нельзя.
                if key in SECRET_FIELDS.get(name, ()) and item == REDACTED_PLACEHOLDER:
                    continue
                merged[key] = copy.deepcopy(item)
            result[name] = merged
        else:
            result[name] = copy.deepcopy(value)

        report.sections.append(name)

    report.sections.sort()
    report.ignored.sort()

    if not report.sections:
        report.ok = False
        report.message = "В файле нет разделов, которые можно применить"

    return (result, report)


def describe_export(report: ExportReport) -> str:
    """Текст для интерфейса после выгрузки."""
    parts = [f"Разделов сохранено: {len(report.sections)}"]
    if report.redacted:
        parts.append(f"Учётные данные вырезаны ({len(report.redacted)})")
    if report.skipped_sections:
        parts.append("Настройки этого компьютера пропущены")
    return ". ".join(parts)


__all__ = [
    "CONFIG_FORMAT_VERSION",
    "MACHINE_SPECIFIC_FIELDS",
    "MACHINE_SPECIFIC_SECTIONS",
    "REDACTED_PLACEHOLDER",
    "SECRET_FIELDS",
    "ExportOptions",
    "ExportReport",
    "ImportReport",
    "build_export",
    "build_import_patch",
    "describe_export",
    "portable_sections",
    "validate_document",
]
