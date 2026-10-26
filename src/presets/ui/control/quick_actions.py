"""Плитки «Быстрые действия» на вкладке «Обход».

Раньше это были строки с одинаковой кнопкой «Открыть»: туры — в
«Настройках программы», остальное — в «Дополнительных действиях» в самом
низу страницы, куда простой вид вовсе не пускал. Теперь это ряд плиток
сразу под сводкой.

Список действий описан один раз (``quick_action_specs``): по нему плитки
строятся и по нему же переводятся при смене языка.

«Тест соединения» сюда не взят: у net67 проверку сети делает BlockCheck,
и вторая кнопка «проверить» только путала бы. «Обновления» оставлены:
другого входа на страницу обновлений в окне нет.

Простой вид прячет плитку сброса сети: в нём она «только пугает», как
раньше строка (presets/ui/control/simple_view.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from qfluentwidgets import BodyLabel
from qfluentwidgets.common.font import setFont

from ui.accessibility import set_state_text
from ui.widgets.action_tile import ActionTile
from ui.widgets.tile_grid import TileGrid


QUICK_ACTION_MIN_WIDTH = 190
#: Предел ширины плитки — тот же принцип, что у сводки (TILE_MAX_WIDTH):
#: на широком окне плитки не растягиваются в полосы.
QUICK_ACTION_MAX_WIDTH = 260
QUICK_ACTIONS_TITLE_KEY = "page.control.section.quick_actions"
QUICK_ACTIONS_TITLE_DEFAULT = "Быстрые действия"

@dataclass(frozen=True, slots=True)
class QuickActionSpec:
    key: str
    icon_name: str
    icon_color: str
    title: tuple[str, str]
    content: tuple[str, str]
    accessible_name: tuple[str, str]


@dataclass(slots=True)
class QuickActionWidgets:
    title_label: object
    grid: object
    tiles: dict


def quick_action_specs(text_prefix: str) -> tuple[QuickActionSpec, ...]:
    """Действия по порядку. Каждый текст — пара (ключ каталога, текст по умолчанию)."""
    return (
        QuickActionSpec(
            key="tour",
            icon_name="fa5s.graduation-cap",
            icon_color="#b39ddb",
            title=("page.control.onboarding_tour.title", "Как пользоваться программой"),
            content=("page.control.quick.tour.desc", "Пошаговая экскурсия по программе"),
            accessible_name=("page.control.onboarding_tour.accessible_name", "Показать обучающий тур"),
        ),
        QuickActionSpec(
            key="bypass_tour",
            icon_name="fa5s.route",
            icon_color="#9fa8da",
            title=("page.control.bypass_tour.title", "Как работает обход"),
            content=("page.control.quick.bypass_tour.desc", "Схемы: как провайдер узнаёт сайт"),
            accessible_name=("page.control.bypass_tour.accessible_name", "Показать экскурсию по обходу"),
        ),
        QuickActionSpec(
            key="internet_cleanup",
            icon_name="fa5s.network-wired",
            icon_color="#4cc38a",
            title=("page.control.internet_cleanup.title", "Сбросить сеть Windows"),
            content=("page.control.quick.internet_cleanup.desc", "DNS, прокси и Winsock — если сеть сломалась"),
            accessible_name=("page.control.internet_cleanup.accessible_name", "Сбросить сеть Windows"),
        ),
        QuickActionSpec(
            key="folder",
            icon_name="fa5s.folder-open",
            icon_color="#f5c04d",
            title=(f"{text_prefix}.button.open_folder", "Открыть папку"),
            content=("page.control.quick.folder.desc", "Папка программы и её файлов"),
            accessible_name=(f"{text_prefix}.button.open_folder.accessible_name", "Открыть папку программы"),
        ),
        QuickActionSpec(
            key="docs",
            icon_name="fa5s.book",
            icon_color="#8ab4f8",
            title=("page.control.docs.title", "Документация"),
            content=("page.control.quick.docs.desc", "Справка: установка, обход, решение проблем"),
            accessible_name=("page.control.docs.accessible_name", "Открыть документацию"),
        ),
        QuickActionSpec(
            key="updates",
            icon_name="fa5s.sync-alt",
            icon_color="#7ee2b8",
            title=("page.control.updates.title", "Обновления"),
            content=("page.control.quick.updates.desc", "Проверить версию и обновиться"),
            accessible_name=("page.control.updates.accessible_name", "Открыть раздел обновлений"),
        ),
        QuickActionSpec(
            key="source",
            icon_name="fa5b.github",
            icon_color="#c9d1d9",
            title=("page.control.source.title", "Исходный код"),
            content=("page.control.quick.source.desc", "Репозиторий net67 на GitHub"),
            accessible_name=("page.control.source.accessible_name", "Открыть исходный код net67 на GitHub"),
        ),
    )


def build_quick_actions(*, tr_fn, text_prefix: str, handlers: dict, parent=None) -> QuickActionWidgets:
    """``handlers`` — обработчик на каждый ключ из ``quick_action_specs``."""
    # Заголовок того же вида, что у групп настроек ниже по странице.
    title_text = tr_fn(QUICK_ACTIONS_TITLE_KEY, QUICK_ACTIONS_TITLE_DEFAULT)
    title_label = BodyLabel(title_text, parent)
    setFont(title_label, 20)
    set_state_text(title_label, f"Раздел страницы: {title_text}")
    grid = TileGrid(
        parent,
        min_tile_width=QUICK_ACTION_MIN_WIDTH,
        max_tile_width=QUICK_ACTION_MAX_WIDTH,
        spacing=12,
    )
    tiles: dict[str, ActionTile] = {}
    for spec in quick_action_specs(text_prefix):
        tile = ActionTile(
            grid,
            icon_name=spec.icon_name,
            icon_color=spec.icon_color,
            title=tr_fn(*spec.title),
            content=tr_fn(*spec.content),
            accessible_name=tr_fn(*spec.accessible_name),
        )
        tile.clicked.connect(handlers[spec.key])
        grid.add_tile(tile)
        tiles[spec.key] = tile
    return QuickActionWidgets(title_label=title_label, grid=grid, tiles=tiles)


def apply_quick_actions_language(*, tr_fn, text_prefix: str, title_label=None, tiles=None) -> None:
    """Переводит плитки на текущий язык по тому же списку, по которому они строились."""
    if title_label is not None:
        title_text = tr_fn(QUICK_ACTIONS_TITLE_KEY, QUICK_ACTIONS_TITLE_DEFAULT)
        title_label.setText(title_text)
        set_state_text(title_label, f"Раздел страницы: {title_text}")
    tiles = dict(tiles or {})
    for spec in quick_action_specs(text_prefix):
        tile = tiles.get(spec.key)
        if tile is None:
            continue
        tile.set_texts(
            tr_fn(*spec.title),
            tr_fn(*spec.content),
            accessible_name=tr_fn(*spec.accessible_name),
        )


__all__ = [
    "QuickActionSpec",
    "QuickActionWidgets",
    "apply_quick_actions_language",
    "build_quick_actions",
    "quick_action_specs",
]
