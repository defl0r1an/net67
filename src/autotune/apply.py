"""Запись найденной стратегии в именованные профили пресета.

Существующее применение из «Подбора стратегии» ищет профиль по цели: по
совпадению фильтров или по хостлисту, содержащему домен. Этого мало.
Автоподбор должен положить найденное ещё и в общий профиль по адресам —
у того никакого хостлиста с youtube.com нет, и по цели он не найдётся.

Поэтому здесь адресация по имени профиля. Имена сверяются с пресетом
тестом: опечатка не упала бы с ошибкой, а тихо положила стратегию мимо,
и человек увидел бы «применено» при неработающем сайте.
"""

from __future__ import annotations

from log.log import log


def apply_strategy_to_named_profiles(
    *,
    presets_feature,
    strategy_lines,
    profile_names,
) -> tuple[str, ...]:
    """Кладёт строки стратегии в профили с указанными именами.

    Возвращает имена профилей, которые действительно обновились. Пустой
    ответ — повод сказать человеку «не применилось», а не «готово».
    """
    from profile.parser import parse_preset_text
    from profile.serializer import (
        serialize_preset,
        with_profile_enabled,
        with_profile_strategy_lines,
    )
    from settings.mode import ENGINE_WINWS2, ZAPRET2_MODE

    wanted = [str(name or "").strip() for name in profile_names or ()]
    wanted = [name for name in wanted if name]
    lines = [str(line or "").strip() for line in strategy_lines or ()]
    lines = [line for line in lines if line]
    if not wanted or not lines:
        return ()

    manifest = presets_feature.get_selected_source_preset_manifest(ZAPRET2_MODE)
    file_name = str(getattr(manifest, "file_name", "") or "").strip()
    if not file_name:
        raise RuntimeError("Не удалось определить выбранный пресет")

    source_text = presets_feature.read_preset_source_by_file_name(ZAPRET2_MODE, file_name)
    preset = parse_preset_text(source_text, engine=ENGINE_WINWS2, source_name=file_name)

    by_name = {
        str(getattr(profile, "name", "") or "").strip(): profile
        for profile in preset.profiles
    }

    updated: list[str] = []
    for name in wanted:
        profile = by_name.get(name)
        if profile is None:
            # Не молчим: расхождение имён — это тихая потеря правки.
            log(f"Автоподбор: профиля «{name}» нет в пресете {file_name}", "⚠ WARNING")
            continue
        preset = with_profile_strategy_lines(preset, profile.index, list(lines))
        preset = with_profile_enabled(preset, profile.index, True)
        updated.append(name)

    if not updated:
        return ()

    presets_feature.save_preset_source_by_file_name(
        ZAPRET2_MODE,
        file_name,
        serialize_preset(preset),
    )
    log(f"Автоподбор: обновлены профили {', '.join(updated)} в {file_name}", "INFO")
    return tuple(updated)


__all__ = ["apply_strategy_to_named_profiles"]
