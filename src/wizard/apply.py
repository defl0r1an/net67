"""Применение результатов мастера первого запуска.

Записывает настройки и возвращает запрос для оркестратора. Операции
записи внедряются снаружи, поэтому модуль тестируется без доступа к
настоящему файлу настроек.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from oneclick.plans import OneClickRequest
from wizard.plans import (
    WizardSettingsPlan,
    build_oneclick_request,
    build_hosts_service_profiles,
    build_settings_plan,
    normalize_selection,
)


@dataclass(slots=True)
class WizardWriters:
    """Функции записи настроек."""

    set_gui_autostart_enabled: Callable[[bool], object]
    set_dpi_autostart: Callable[[bool], object]
    set_tray_close_mode: Callable[[str], object]
    #: Возвращает текст ошибки или пустую строку.
    apply_hosts: Callable[[dict], object]
    set_wizard_services: Callable[[list], object]
    set_wizard_completed: Callable[[bool], object]


@dataclass(frozen=True, slots=True)
class WizardResult:
    request: OneClickRequest
    settings: WizardSettingsPlan
    saved: bool
    message: str = ""
    #: Настройки сохранены, но что-то из них не применилось к системе.
    warnings: tuple[str, ...] = ()


def _apply_gui_autostart(enabled: bool) -> str:
    """Создаёт или удаляет задачу автозапуска. Возвращает текст ошибки.

    Здесь легко ошибиться: в проекте две функции с именем
    set_gui_autostart_enabled. Та, что в settings.store, лишь пишет флаг
    в settings.json — именно её мастер и вызывал, поэтому галочка
    «Запускать вместе с Windows» сохранялась, а в планировщике не
    появлялось ничего. Задачу регистрирует одноимённая функция из
    program_settings.commands, она же потом сохраняет флаг.
    """
    from program_settings.commands import set_gui_autostart_enabled as register_autostart

    result = register_autostart(bool(enabled))
    if str(getattr(result, "level", "") or "") in ("error", "warning"):
        return str(getattr(result, "content", "") or "Не удалось настроить автозапуск.")
    return ""


def _apply_hosts_entries(service_profiles: dict) -> str:
    """Мастер больше не пишет в hosts сам.

    Раньше здесь применялся выбор категорий — подмножество каталога. Но
    теперь после установки включается весь каталог сервисов, и делает это
    hosts.first_run_defaults в отдельном потоке при запуске.

    Два писателя в один системный файл — гарантированная гонка: поток с
    умолчаниями и завершение мастера легко попадают в одно и то же окно
    времени, а результат зависит от того, кто допишет последним. Поэтому
    здесь остаётся только проверка, что однократный шаг вообще запланирован.
    """
    _ = service_profiles
    try:
        from hosts.first_run_defaults import is_needed

        if is_needed():
            # Шаг ещё впереди — предупреждать человека не о чем.
            return ""
    except Exception as exc:
        return f"Не удалось проверить настройку сервисов: {exc}"
    return ""


def build_default_writers() -> WizardWriters:
    from settings.store import (
        set_dpi_autostart,
        set_tray_close_mode,
        set_wizard_completed,
        set_wizard_services,
    )

    return WizardWriters(
        set_gui_autostart_enabled=_apply_gui_autostart,
        set_dpi_autostart=set_dpi_autostart,
        set_tray_close_mode=set_tray_close_mode,
        apply_hosts=_apply_hosts_entries,
        set_wizard_services=set_wizard_services,
        set_wizard_completed=set_wizard_completed,
    )


def apply_wizard(
    *,
    selection,
    autostart_with_windows: bool,
    minimize_to_tray: bool,
    writers: WizardWriters | None = None,
) -> WizardResult:
    """Сохраняет ответы мастера и готовит запрос на включение.

    Флаг завершения выставляется последним: если запись настроек упала,
    мастер должен открыться снова, а не считаться пройденным.
    """
    writers = writers or build_default_writers()
    selected = normalize_selection(selection)
    settings = build_settings_plan(
        autostart_with_windows=autostart_with_windows,
        minimize_to_tray=minimize_to_tray,
    )
    request = build_oneclick_request(selected)

    warnings: list[str] = []
    try:
        # Регистрация задачи в планировщике может не пройти — например,
        # если политика запрещает. Настройки от этого не теряются, но
        # промолчать нельзя: пользователь включил галочку и ждёт
        # автозапуска.
        problem = writers.set_gui_autostart_enabled(settings.gui_autostart_enabled)
        if problem:
            warnings.append(str(problem))

        writers.set_dpi_autostart(settings.dpi_autostart)
        writers.set_tray_close_mode(settings.tray_close_mode)
        writers.set_wizard_services(sorted(selected))

        # Записи hosts применяем сразу, а не откладываем до «Включить».
        # Иначе человек отмечает «Нейросети», открывает редактор hosts и
        # видит там пусто — выбор как будто не сохранился.
        hosts_problem = writers.apply_hosts(build_hosts_service_profiles(selected))
        if hosts_problem:
            warnings.append(str(hosts_problem))

        writers.set_wizard_completed(True)
    except Exception as exc:
        return WizardResult(
            request=request,
            settings=settings,
            saved=False,
            message=f"Не удалось сохранить настройки: {exc}",
            warnings=tuple(warnings),
        )

    return WizardResult(
        request=request,
        settings=settings,
        saved=True,
        warnings=tuple(warnings),
    )


def is_wizard_needed() -> bool:
    """Открывать ли мастер при запуске."""
    try:
        from settings.store import get_wizard_completed

        return not bool(get_wizard_completed())
    except Exception:
        # Не смогли прочитать настройки — лучше показать мастер лишний
        # раз, чем оставить пользователя с ненастроенным приложением.
        return True


def build_request_from_settings() -> OneClickRequest:
    """Запрос для кнопки «Включить» из сохранённых ответов мастера."""
    try:
        from settings.store import get_wizard_services

        return build_oneclick_request(get_wizard_services())
    except Exception:
        return build_oneclick_request(())


__all__ = [
    "WizardResult",
    "WizardWriters",
    "apply_wizard",
    "build_default_writers",
    "build_request_from_settings",
    "is_wizard_needed",
]
