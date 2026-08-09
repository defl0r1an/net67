"""Build-helper вкладки «О программе» для About page."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from PyQt6.QtWidgets import QLabel, QHBoxLayout, QVBoxLayout

from ui.accessibility import set_state_text
from ui.pages.about_page_accessibility import apply_about_buttons_accessibility
from ui.pages.about_page_help_accessibility import set_help_card_accessibility as set_link_card_accessibility
from ui.fluent_widgets import SettingsCard
from qfluentwidgets import (
    CaptionLabel,
    FluentIcon,
    HyperlinkCard,
    PrimaryPushButton,
    PushButton,
    SettingCardGroup,
    StrongBodyLabel,
    SubtitleLabel,
)
from ui.theme import get_cached_qta_pixmap


@dataclass(slots=True)
class AboutPageAboutWidgets:
    about_section_version_label: object
    about_app_name_label: object
    about_version_value_label: object
    update_btn: object
    # Ниже — остатки удалённых секций «Подписка» и «Обучение».
    # Всегда None; поля сохранены, потому что на них ссылается about_page.py.
    about_section_subscription_label: object = None
    sub_status_icon: QLabel | None = None
    sub_status_label: object = None
    sub_desc_label: object = None
    premium_btn: object = None
    course_group: object = None
    youtube_course_card: object = None
    youtube_playlist_card: object = None


def set_subscription_status_accessibility(label, text: object) -> None:
    value = " ".join(str(text or "").strip().split())
    if not value:
        return
    set_state_text(label, f"Статус подписки: {value}")


def set_subscription_description_accessibility(label, text: object) -> None:
    value = " ".join(str(text or "").strip().split())
    if not value:
        return
    set_state_text(label, f"Описание подписки: {value}")


def set_about_version_accessibility(app_name_label, version_label, *, app_name: object, app_version: object) -> None:
    app_name_value = " ".join(str(app_name or "").strip().split())
    app_version_value = " ".join(str(app_version or "").strip().split())
    if app_name_value:
        set_state_text(app_name_label, f"Название программы: {app_name_value}")
    if app_version_value:
        set_state_text(version_label, f"Версия программы: {app_version_value}")


def build_about_page_about_content(
    layout: QVBoxLayout,
    *,
    tr_fn: Callable[[str, str], str],
    tokens,
    content_parent,
    app_version: str,
    make_section_label: Callable[[str], object],
    on_open_updates,
) -> AboutPageAboutWidgets:
    about_section_version_label = make_section_label(
        tr_fn("page.about.section.version", "Версия")
    )
    layout.addWidget(about_section_version_label)

    version_card = SettingsCard()
    version_layout = QHBoxLayout()
    version_layout.setSpacing(16)

    icon_label = QLabel()
    icon_label.setPixmap(get_cached_qta_pixmap('fa5s.shield-alt', color=tokens.accent_hex, size=40))
    icon_label.setFixedSize(48, 48)
    version_layout.addWidget(icon_label)

    text_layout = QVBoxLayout()
    text_layout.setSpacing(2)
    app_name_text = tr_fn("page.about.app_name", "net67 v2 GUI")
    about_app_name_label = SubtitleLabel(app_name_text)
    about_version_value_label = CaptionLabel(
        tr_fn("page.about.version.value_template", "Версия {version}").format(version=app_version)
    )
    set_about_version_accessibility(
        about_app_name_label,
        about_version_value_label,
        app_name=app_name_text,
        app_version=app_version,
    )
    text_layout.addWidget(about_app_name_label)
    text_layout.addWidget(about_version_value_label)
    version_layout.addLayout(text_layout, 1)

    update_btn = PushButton(
        tr_fn("page.about.button.update_settings", "Настройка обновлений"),
        icon=FluentIcon.SYNC,
    )
    apply_about_buttons_accessibility(tr_fn=tr_fn, update_btn=update_btn)
    update_btn.clicked.connect(on_open_updates)
    version_layout.addWidget(update_btn)

    version_card.add_layout(version_layout)
    layout.addWidget(version_card)
    layout.addSpacing(16)

    # Удалены две секции:
    #
    #   «Подписка» — статус Free/Premium, кнопка «Premium и VPN» и кнопка
    #   «net67 KVN». Подписок в продукте больше нет.
    #
    #   «Обучение» — две карточки на YouTube-канал и плейлист автора
    #   исходного проекта.
    #
    # Поля виджетов остаются в AboutPageAboutWidgets со значением None:
    # about_page.py к ним обращается и уже проверяет на None.
    layout.addStretch()

    return AboutPageAboutWidgets(
        about_section_version_label=about_section_version_label,
        about_app_name_label=about_app_name_label,
        about_version_value_label=about_version_value_label,
        update_btn=update_btn,
    )
