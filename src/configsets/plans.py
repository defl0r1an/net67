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

Кроме настроек, файл переноса несёт свои пресеты человека (папка
presets\\winws2). Без них перенос не работал: настройки помнили имя
выбранного пресета, а на другом компьютере такого файла не было.

Модуль чистый: ни файлов, ни Qt.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

#: Формат файла конфигурации. Повышается при несовместимых изменениях.
CONFIG_FORMAT_VERSION = 1

#: Разделы, которые никогда не переносятся между машинами.
MACHINE_SPECIFIC_SECTIONS: frozenset[str] = frozenset(
    {
        "window",  # геометрия окна конкретного экрана
        # Кэш выпусков и лимиты запросов к серверам обновлений — сведения
        # этой машины. Чужой кэш показал бы «обновлений нет», пока не
        # истечёт его срок.
        "updater",
    }
)

#: Значения, которые при загрузке заменяются целиком, а не сливаются.
#:
#: Выбор сервисов hosts — это ответ «какие сервисы включены». Слей его с
#: выбором этого компьютера, и выключенный в файле сервис остался бы
#: включённым здесь: перенос «сделай как там» делал бы «как там, плюс
#: всё, что было здесь». Указатели вроде реестра пресетов, наоборот,
#: сливаются: в них есть записи этого компьютера, которых в файле нет.
REPLACED_ON_IMPORT: frozenset[tuple[str, ...]] = frozenset({("hosts", "selection")})

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


#: Свой пресет — текстовый файл с простым именем, без пути.
#:
#: Имена приходят из файла переноса, то есть снаружи. Разделитель пути или
#: «..» в имени записал бы файл мимо папки пресетов.
_PRESET_NAME_RE = re.compile(r'^[^\\/:*?"<>|\x00-\x1f]{1,140}\.txt$', re.IGNORECASE)

#: Пределы размера пресетов в файле переноса.
#:
#: Пресет — несколько десятков строк, самые длинные встроенные — около
#: 40 КБ. Мегабайт на файл и двадцать на все — с запасом для настоящих и
#: заслон от файла, который заполнил бы диск.
MAX_PRESET_BYTES = 1_000_000
MAX_PRESETS_TOTAL_BYTES = 20_000_000

#: Чем помечается пресет из файла, если здесь есть свой с тем же именем.
IMPORTED_PRESET_SUFFIX = " (из файла)"


def is_safe_preset_name(name: object) -> bool:
    text = str(name or "")
    if text != text.strip() or text.startswith("."):
        return False
    return bool(_PRESET_NAME_RE.match(text)) and ".." not in text


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
    presets: list[str] = field(default_factory=list)

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
    *,
    presets: dict[str, str] | None = None,
) -> tuple[dict, ExportReport]:
    """Готовит содержимое файла конфигурации.

    ``presets`` — свои пресеты {имя файла: текст}. Наборы на этом же
    компьютере их не передают: файлы и так лежат здесь.
    """
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
    if presets:
        document["presets"] = {
            name: str(text) for name, text in sorted(presets.items()) if is_safe_preset_name(name)
        }
        report.presets = sorted(document["presets"])
    return document, report


@dataclass(slots=True)
class ImportReport:
    ok: bool
    message: str = ""
    sections: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PresetImportPlan:
    """Что сделать с пресетами из файла.

    Свой пресет с тем же именем, но другим текстом не затирается: человек
    мог поправить его здесь, и загрузка чужого файла молча стёрла бы
    правку. Пресет из файла ложится рядом под новым именем, а ссылки на
    него в настройках из файла переставляются на это имя.
    """

    writes: dict[str, str] = field(default_factory=dict)
    renamed: dict[str, str] = field(default_factory=dict)
    same: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def plan_preset_import(document: dict, *, existing: dict[str, str]) -> PresetImportPlan:
    """Решает, какие пресеты из файла записать и под какими именами."""
    plan = PresetImportPlan()
    incoming = document.get("presets") if isinstance(document, dict) else None
    if not isinstance(incoming, dict):
        return plan

    taken = {name.casefold() for name in existing}
    total = 0
    for name, text in sorted(incoming.items(), key=lambda item: str(item[0])):
        if not is_safe_preset_name(name) or not isinstance(text, str):
            plan.rejected.append(str(name))
            continue
        size = len(text.encode("utf-8"))
        total += size
        if size > MAX_PRESET_BYTES or total > MAX_PRESETS_TOTAL_BYTES:
            plan.rejected.append(name)
            continue

        own = next((value for key, value in existing.items() if key.casefold() == name.casefold()), None)
        if own is None:
            plan.writes[name] = text
            taken.add(name.casefold())
            continue
        if _same_text(own, text):
            plan.same.append(name)
            continue

        stem = name[: -len(".txt")]
        candidate = f"{stem}{IMPORTED_PRESET_SUFFIX}.txt"
        number = 2
        while candidate.casefold() in taken:
            candidate = f"{stem}{IMPORTED_PRESET_SUFFIX} {number}.txt"
            number += 1
        taken.add(candidate.casefold())
        plan.writes[candidate] = text
        plan.renamed[name] = candidate

    plan.same.sort()
    plan.rejected.sort()
    return plan


def _same_text(left: str, right: str) -> bool:
    # Переводы строк меняют редакторы и git — это не правка пресета.
    return left.replace("\r\n", "\n").rstrip() == right.replace("\r\n", "\n").rstrip()


def remap_preset_names(sections: dict, renamed: dict[str, str]) -> dict:
    """Переставляет ссылки на переименованные пресеты внутри разделов из файла.

    Ссылки на пресет по имени файла лежат в нескольких местах: выбранный
    пресет, реестр (по нему находятся оценки), привязки к ссылке и папки
    списка. Переставляются именно разделы из файла — до слияния: свой
    пресет этого компьютера с тем же именем остаётся со своими записями.
    """
    if not renamed:
        return sections
    result = copy.deepcopy(sections)

    program = result.get("program")
    if isinstance(program, dict):
        for key, value in list(program.items()):
            if key.startswith("selected_source_preset_file_name") and value in renamed:
                program[key] = renamed[value]

    for section in ("preset_registry", "remote_presets"):
        scopes = result.get(section)
        if isinstance(scopes, dict) and isinstance(scopes.get("winws2"), dict):
            scopes["winws2"] = {renamed.get(name, name): value for name, value in scopes["winws2"].items()}

    folders = result.get("folders")
    presets = folders.get("presets") if isinstance(folders, dict) else None
    state = presets.get("winws2") if isinstance(presets, dict) else None
    if isinstance(state, dict) and isinstance(state.get("items"), dict):
        state["items"] = {renamed.get(name, name): value for name, value in state["items"].items()}
    return result


def _merge(current, incoming, path: tuple[str, ...]):
    """Накладывает значение из файла на текущее: словари — по ключам, вглубь."""
    if path in REPLACED_ON_IMPORT or not isinstance(current, dict) or not isinstance(incoming, dict):
        return copy.deepcopy(incoming)
    merged = copy.deepcopy(current)
    for key, item in incoming.items():
        if key in merged:
            merged[key] = _merge(merged[key], item, (*path, key))
        else:
            merged[key] = copy.deepcopy(item)
    return merged


@dataclass(frozen=True, slots=True)
class PostApplyActions:
    """Что применить в системе после записи новых настроек.

    settings.json — не вся правда. Автозапуск живёт задачей планировщика
    Windows, выбор сервисов hosts — строками системного файла. Запиши
    одни настройки, и на экране «включено», а в системе — как было.
    None — менять не нужно.
    """

    hosts_selection: dict | None = None
    gui_autostart: bool | None = None

    @property
    def any(self) -> bool:
        return self.hosts_selection is not None or self.gui_autostart is not None


def post_apply_actions(before: dict, after: dict) -> PostApplyActions:
    def hosts_selection(data):
        hosts = data.get("hosts") if isinstance(data, dict) else None
        selection = hosts.get("selection") if isinstance(hosts, dict) else None
        return dict(selection) if isinstance(selection, dict) else {}

    def gui_autostart(data):
        program = data.get("program") if isinstance(data, dict) else None
        return bool(program.get("gui_autostart_enabled")) if isinstance(program, dict) else False

    new_selection = hosts_selection(after)
    new_autostart = gui_autostart(after)
    return PostApplyActions(
        hosts_selection=new_selection if new_selection != hosts_selection(before) else None,
        gui_autostart=new_autostart if new_autostart != gui_autostart(before) else None,
    )


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
    renamed_presets: dict[str, str] | None = None,
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
    sections = remap_preset_names(dict(document.get("sections") or {}), dict(renamed_presets or {}))

    for name, value in sections.items():
        if keep_machine_specific and name in MACHINE_SPECIFIC_SECTIONS:
            report.ignored.append(name)
            continue
        if name not in result:
            # Неизвестный раздел молча пропускаем: нормализация всё равно
            # его выбросит, а пользователю честнее показать список.
            report.ignored.append(name)
            continue

        if isinstance(value, dict) and isinstance(result.get(name), dict):
            # Пустой секрет означает «в файле его вырезали» — затирать им
            # рабочий пароль нельзя.
            incoming = {
                key: item
                for key, item in value.items()
                if not (key in SECRET_FIELDS.get(name, ()) and item == REDACTED_PLACEHOLDER)
            }
            # Слияние вглубь, а не по верхним ключам. По верхним реестр
            # пресетов из файла целиком заменял реестр этого компьютера, и
            # свои пресеты здесь теряли привязку к своим оценкам.
            result[name] = _merge(result[name], incoming, (name,))
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
    if report.presets:
        parts.append(f"своих пресетов: {len(report.presets)}")
    if report.redacted:
        parts.append(f"Учётные данные вырезаны ({len(report.redacted)})")
    if report.skipped_sections:
        parts.append("Настройки этого компьютера пропущены")
    return ". ".join(parts)


__all__ = [
    "CONFIG_FORMAT_VERSION",
    "IMPORTED_PRESET_SUFFIX",
    "MACHINE_SPECIFIC_FIELDS",
    "MACHINE_SPECIFIC_SECTIONS",
    "REDACTED_PLACEHOLDER",
    "REPLACED_ON_IMPORT",
    "SECRET_FIELDS",
    "ExportOptions",
    "ExportReport",
    "ImportReport",
    "PostApplyActions",
    "PresetImportPlan",
    "build_export",
    "build_import_patch",
    "describe_export",
    "is_safe_preset_name",
    "plan_preset_import",
    "portable_sections",
    "post_apply_actions",
    "remap_preset_names",
    "validate_document",
]
