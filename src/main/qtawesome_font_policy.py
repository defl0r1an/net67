"""Единая политика наборов иконок qtawesome для runtime и сборщика."""

from __future__ import annotations

from types import ModuleType
from typing import Iterable, Sequence


# Поиск по исходникам должен подтверждать, что все используемые префиксы
# перечислены здесь. Сборщик оставляет данные только этих наборов.
#
# В исходном проекте здесь два набора, fa5s и fa5b. У net67 ещё mdi: им
# нарисованы страница прокси Telegram, группа «ИИ» на «Сервисах» и значок
# ChatGPT. Без него эти значки молча пропали бы — qtawesome не падает на
# неизвестном наборе, а рисует пустоту.
QT_AWESOME_ALLOWED_PREFIXES = ("fa5s", "fa5b", "mdi")


def select_qtawesome_bundles(
    bundles: Iterable[Sequence[str]],
) -> tuple[tuple[str, ...], ...]:
    """Оставляет только разрешённые наборы и проверяет полноту политики."""
    normalized = tuple(tuple(str(value) for value in bundle) for bundle in bundles)
    by_prefix = {
        bundle[0]: bundle
        for bundle in normalized
        if len(bundle) >= 3 and bundle[0]
    }
    missing = [prefix for prefix in QT_AWESOME_ALLOWED_PREFIXES if prefix not in by_prefix]
    if missing:
        raise RuntimeError(
            "qtawesome не содержит обязательные наборы иконок: "
            + ", ".join(missing)
        )
    return tuple(by_prefix[prefix] for prefix in QT_AWESOME_ALLOWED_PREFIXES)


def configure_qtawesome_module(module: ModuleType) -> tuple[str, ...]:
    """Ограничивает qtawesome до наборов, реально используемых net67."""
    bundles = getattr(module, "_BUNDLED_FONTS", None)
    if not isinstance(bundles, (tuple, list)):
        raise RuntimeError("qtawesome не предоставляет список _BUNDLED_FONTS")

    selected = select_qtawesome_bundles(bundles)
    module._BUNDLED_FONTS = selected
    return tuple(bundle[0] for bundle in selected)


__all__ = [
    "QT_AWESOME_ALLOWED_PREFIXES",
    "configure_qtawesome_module",
    "select_qtawesome_bundles",
]
