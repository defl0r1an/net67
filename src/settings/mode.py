"""Способ запуска обхода.

Способ ровно один — winws2. Так было не всегда: рядом жили winws1 и
оркестратор, между ними переключались на отдельной странице, и почти
каждый узел приложения умел спрашивать «а какой сейчас режим». Разница
между ними человеку ничего не давала, а стоила дорого: пресеты в двух
экземплярах, страницы в двух экземплярах, ветвления по всему коду и
целый класс ошибок, где половина программы уже в одном режиме, а
половина ещё в другом.

Вырезано по просьбе. Модуль оставлен, а не удалён: на него ссылается
множество мест, и все они продолжают спрашивать про режим — просто
ответ теперь всегда один. Функции-предикаты оставлены с тем же смыслом,
чтобы вызывающий код читался как прежде.
"""

from __future__ import annotations

import os

ZAPRET2_MODE = "zapret2_mode"

#: Способы, которых больше нет.
#:
#: Строки оставлены, а из ALL_LAUNCH_METHODS убраны. Это не половинчатая
#: мера, а порядок работ: на эти имена ссылаются полторы сотни мест, и
#: снести их одним движением значит получить приложение, которое не
#: запускается вовсе. Убрав их из списка допустимых, мы делаем режимы
#: недостижимыми: normalize_launch_method возвращает winws2 на любое
#: значение, страницы убраны из навигации, выбирать нечего.
#:
#: Дальше модули и страницы удаляются по одному, с проверкой на каждом
#: шаге. Когда последняя ссылка уйдёт — уйдут и эти строки.
ZAPRET1_MODE = "zapret1_mode"
ORCHESTRA_MODE = "orchestra"

DEFAULT_LAUNCH_METHOD = ZAPRET2_MODE

ALL_LAUNCH_METHODS = frozenset((ZAPRET2_MODE,))

PRESET_LAUNCH_METHODS = frozenset((ZAPRET2_MODE,))

ENGINE_WINWS1 = "winws1"
ENGINE_WINWS2 = "winws2"
ALL_ENGINES = frozenset((ENGINE_WINWS2,))

ENGINE_BY_LAUNCH_METHOD = {
    ZAPRET2_MODE: ENGINE_WINWS2,
}

DEFAULT_PRESET_FILE_NAME_BY_ENGINE = {
    ENGINE_WINWS2: "Стандартный 1.txt",
}

EXE_NAME_WINWS1 = "winws.exe"
EXE_NAME_WINWS2 = "winws2.exe"
#: Оба имени: winws.exe от прежнего движка ещё может висеть в системе
#: после обновления, и остановка обязана его снимать.
ALL_WINWS_EXE_NAMES = (EXE_NAME_WINWS1, EXE_NAME_WINWS2)
ALL_WINWS_EXE_NAME_SET = frozenset(ALL_WINWS_EXE_NAMES)
WINWS_ENGINE_FAMILY_LABEL = ENGINE_WINWS2
WINWS_EXE_FAMILY_LABEL = EXE_NAME_WINWS2

RELATIVE_EXE_PATH_WINWS1 = os.path.join("exe", EXE_NAME_WINWS1)
RELATIVE_EXE_PATH_WINWS2 = os.path.join("exe", EXE_NAME_WINWS2)

SELECTED_SOURCE_PRESET_FILE_NAME_KEY_WINWS1 = f"selected_source_preset_file_name_{ENGINE_WINWS1}"
SELECTED_SOURCE_PRESET_FILE_NAME_KEY_WINWS2 = f"selected_source_preset_file_name_{ENGINE_WINWS2}"

PRESETS_SCOPE_WINWS1 = ENGINE_WINWS1
PRESETS_SCOPE_WINWS2 = ENGINE_WINWS2
PRESETS_DIR_NAME_WINWS1 = PRESETS_SCOPE_WINWS1
PRESETS_DIR_NAME_WINWS2 = PRESETS_SCOPE_WINWS2
BUILTIN_PRESETS_DIR_NAME_WINWS1 = f"{PRESETS_DIR_NAME_WINWS1}_builtin"
BUILTIN_PRESETS_DIR_NAME_WINWS2 = f"{PRESETS_DIR_NAME_WINWS2}_builtin"

EXE_NAME_BY_LAUNCH_METHOD = {
    ZAPRET2_MODE: EXE_NAME_WINWS2,
}


def normalize_launch_method(value: object, *, default: str = DEFAULT_LAUNCH_METHOD) -> str:
    """Приводит значение к способу запуска.

    Способ один, поэтому любое сохранённое значение — в том числе
    «zapret1_mode» и «orchestra» из настроек, оставшихся от прежних
    версий, — превращается в него же. Молча и намеренно: человек,
    обновившийся со старой версии, должен получить работающий обход, а
    не отказ из-за режима, которого больше нет.
    """
    _ = value
    method = str(default or "").strip().lower()
    return method if method in ALL_LAUNCH_METHODS else DEFAULT_LAUNCH_METHOD


def require_launch_method(value: object) -> str:
    _ = value
    return DEFAULT_LAUNCH_METHOD


def is_known_launch_method(value: object) -> bool:
    return str(value or "").strip().lower() in ALL_LAUNCH_METHODS


def is_preset_launch_method(value: object) -> bool:
    _ = value
    return True


def is_orchestra_launch_method(value: object) -> bool:
    """Оркестратор вырезан — режима больше нет ни у кого."""
    _ = value
    return False


def is_zapret2_launch_method(value: object) -> bool:
    _ = value
    return True


def is_zapret1_launch_method(value: object) -> bool:
    """winws1 вырезан — режима больше нет ни у кого."""
    _ = value
    return False


def engine_for_launch_method(value: object) -> str:
    _ = value
    return ENGINE_WINWS2


def engine_for_launch_method_or_none(value: object) -> str | None:
    _ = value
    return ENGINE_WINWS2


def exe_name_for_launch_method(value: object) -> str:
    _ = value
    return EXE_NAME_WINWS2


def exe_path_for_launch_method(value: object) -> str:
    from config.runtime_layout import APPLICATION_PATHS

    return str(APPLICATION_PATHS.exe_dir / EXE_NAME_WINWS2)


__all__ = [
    "ALL_ENGINES",
    "ALL_LAUNCH_METHODS",
    "ALL_WINWS_EXE_NAME_SET",
    "ALL_WINWS_EXE_NAMES",
    "BUILTIN_PRESETS_DIR_NAME_WINWS1",
    "BUILTIN_PRESETS_DIR_NAME_WINWS2",
    "ENGINE_WINWS1",
    "EXE_NAME_WINWS1",
    "ORCHESTRA_MODE",
    "PRESETS_DIR_NAME_WINWS1",
    "PRESETS_SCOPE_WINWS1",
    "RELATIVE_EXE_PATH_WINWS1",
    "SELECTED_SOURCE_PRESET_FILE_NAME_KEY_WINWS1",
    "ZAPRET1_MODE",
    "DEFAULT_LAUNCH_METHOD",
    "DEFAULT_PRESET_FILE_NAME_BY_ENGINE",
    "ENGINE_BY_LAUNCH_METHOD",
    "ENGINE_WINWS2",
    "EXE_NAME_BY_LAUNCH_METHOD",
    "EXE_NAME_WINWS2",
    "PRESETS_DIR_NAME_WINWS2",
    "PRESETS_SCOPE_WINWS2",
    "PRESET_LAUNCH_METHODS",
    "RELATIVE_EXE_PATH_WINWS2",
    "SELECTED_SOURCE_PRESET_FILE_NAME_KEY_WINWS2",
    "WINWS_ENGINE_FAMILY_LABEL",
    "WINWS_EXE_FAMILY_LABEL",
    "ZAPRET2_MODE",
    "engine_for_launch_method",
    "engine_for_launch_method_or_none",
    "exe_name_for_launch_method",
    "exe_path_for_launch_method",
    "is_known_launch_method",
    "is_orchestra_launch_method",
    "is_preset_launch_method",
    "is_zapret1_launch_method",
    "is_zapret2_launch_method",
    "normalize_launch_method",
    "require_launch_method",
]
