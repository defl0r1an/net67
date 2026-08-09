"""Применение выбора провайдера: пресет и запись в настройки.

Отделено от каталога и от интерфейса: запись в настройки — побочный
эффект, и его надо уметь подменять в тестах.
"""

from __future__ import annotations

from log.log import log

from provider.catalog import get_provider, preset_for_provider


def apply_provider_choice(provider_key: str, *, engine: str = "winws2") -> tuple[bool, str]:
    """Запоминает провайдера и выбирает стартовый пресет.

    Возвращает (успех, сообщение). Неудача выбора пресета не критична:
    останется тот, что был, и человек всё равно сможет включить защиту.
    """
    provider = get_provider(provider_key)

    try:
        from settings.store import set_provider_key

        set_provider_key(provider.key)
    except Exception as exc:
        log(f"Провайдер не сохранён: {exc}", "⚠ WARNING")

    preset = preset_for_provider(provider.key)
    try:
        from settings.store import set_selected_source_preset_file_name

        set_selected_source_preset_file_name(engine, preset)
    except Exception as exc:
        return (False, f"Не удалось выбрать пресет: {exc}")

    log(f"Провайдер: {provider.title}, стартовый пресет: {preset}", "INFO")
    return (True, preset)


__all__ = ["apply_provider_choice"]
