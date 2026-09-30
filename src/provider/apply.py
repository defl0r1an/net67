"""Применение выбора провайдера: пресет и запись в настройки.

Отделено от каталога и от интерфейса: запись в настройки — побочный
эффект, и его надо уметь подменять в тестах.
"""

from __future__ import annotations

from collections.abc import Callable

from log.log import log

from provider.catalog import get_provider, preset_for_provider


def apply_provider_choice(
    provider_key: str,
    *,
    select_preset: Callable[[str], object] | None,
) -> tuple[bool, str]:
    """Запоминает провайдера и выбирает стартовый пресет.

    Возвращает (успех, сообщение). Неудача выбора пресета не критична:
    останется тот, что был, и человек всё равно сможет включить обход.

    Пресет выбирает ``select_preset`` — выбор пресета фасада пресетов.
    Раньше здесь стояла прямая запись в настройки: пресет менялся, а
    главная страница, runtime и списки об этом не узнавали — событие о
    смене выбора шлёт только PresetSelectionService (zapret 21.1.6.46
    сделал его единственным писателем, и architecture_checks это
    проверяет).
    """
    provider = get_provider(provider_key)

    try:
        from settings.store import set_provider_key

        set_provider_key(provider.key)
    except Exception as exc:
        log(f"Провайдер не сохранён: {exc}", "⚠ WARNING")

    preset = preset_for_provider(provider.key)
    if select_preset is None:
        return (False, "Пресет не выбран: нет доступа к выбору пресета")
    try:
        select_preset(preset)
    except Exception as exc:
        return (False, f"Не удалось выбрать пресет: {exc}")

    log(f"Провайдер: {provider.title}, стартовый пресет: {preset}", "INFO")
    return (True, preset)


__all__ = ["apply_provider_choice"]
