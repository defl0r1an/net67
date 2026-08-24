"""Build-helper верхних секций Appearance page.

Разделы «Язык интерфейса» и «Фон окна» удалены целиком. Язык —
приложение внутреннее и русскоязычное, перевод был неполный. Фон — из
трёх вариантов рабочим оставался только «Стандартный»: AMOLED делал
окно сплошь чёрным без возможности вернуться, а картинки для темы в
поставке нет. Билдеры и подписи доступности к ним удалены вместе с
разделами, чтобы мёртвые строки не попадали в сборку.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from app.ui_texts import tr as tr_catalog
from ui.accessibility import set_control_accessibility, set_state_text
from ui.segmented_accessibility import set_segmented_items_accessibility


@dataclass(slots=True)
class AppearanceDisplayModeWidgets:
    section_title: object
    card: object
    segmented: object | None
    spacer: object


def build_display_mode_section(
    *,
    page,
    tr_language: str,
    add_section_title,
    content_parent,
    settings_card_cls,
    caption_label_cls,
    segmented_widget_cls,
    on_display_mode_changed,
) -> AppearanceDisplayModeWidgets:
    section_title = add_section_title(
        text_key="page.appearance.section.display_mode",
        return_widget=True,
    )

    display_card = settings_card_cls()
    display_layout = QVBoxLayout()
    display_layout.setSpacing(12)

    display_desc = caption_label_cls(
        tr_catalog(
            "page.appearance.display_mode.description",
            language=tr_language,
            default="Выберите светлый или тёмный режим интерфейса.",
        )
    )
    display_desc.setWordWrap(True)
    display_layout.addWidget(display_desc)

    display_mode_seg = None
    try:
        display_mode_seg = segmented_widget_cls()
        display_mode_seg.addItem(
            "dark",
            tr_catalog("page.appearance.display_mode.option.dark", language=tr_language, default="🌙 Тёмный"),
            lambda: on_display_mode_changed("dark"),
        )
        display_mode_seg.addItem(
            "light",
            tr_catalog("page.appearance.display_mode.option.light", language=tr_language, default="☀️ Светлый"),
            lambda: on_display_mode_changed("light"),
        )
        display_mode_seg.addItem(
            "system",
            tr_catalog("page.appearance.display_mode.option.system", language=tr_language, default="⚙ Авто"),
            lambda: on_display_mode_changed("system"),
        )
        display_mode_seg.setCurrentItem("dark")
        update_display_mode_accessibility(display_mode_seg, mode="dark")
        display_mode_seg.currentItemChanged.connect(
            lambda mode: update_display_mode_accessibility(display_mode_seg, mode=mode)
        )
        display_layout.addWidget(display_mode_seg)
    except Exception:
        display_mode_seg = None

    display_card.add_layout(display_layout)

    spacer = QWidget(content_parent)
    spacer.setFixedHeight(16)
    spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    return AppearanceDisplayModeWidgets(
        section_title=section_title,
        card=display_card,
        segmented=display_mode_seg,
        spacer=spacer,
    )


def update_display_mode_accessibility(widget, *, mode: object | None = None) -> None:
    labels = {
        "dark": "Тёмный",
        "light": "Светлый",
        "system": "Авто",
    }
    key = str(mode or "").strip()
    if not key:
        try:
            key = str(widget.currentItem() or "").strip()
        except Exception:
            key = ""
    selected = labels.get(key, key or "Тёмный")
    state = f"Режим отображения интерфейса, выбрано: {selected}"
    set_state_text(widget, state)
    set_control_accessibility(
        widget,
        name=state,
        description="Выберите светлый, тёмный или автоматический режим интерфейса.",
    )
    set_segmented_items_accessibility(
        widget,
        name="Режим отображения интерфейса",
        labels=labels,
    )


def update_sidebar_icon_style_accessibility(widget, *, style: object | None = None) -> None:
    labels = {
        "standard": "Стандартные",
        "windows11_fluent": "Windows 11 Fluent",
    }
    key = str(style or "").strip()
    if not key:
        try:
            key = str(widget.currentItem() or "").strip()
        except Exception:
            key = ""
    selected = labels.get(key, key or "Стандартные")
    state = f"Стиль иконок бокового меню, выбрано: {selected}"
    set_state_text(widget, state)
    set_control_accessibility(
        widget,
        name=state,
        description="Выберите стиль иконок в левом боковом меню.",
    )
    set_segmented_items_accessibility(
        widget,
        name="Стиль иконок бокового меню",
        labels=labels,
    )
