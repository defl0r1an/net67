"""Build-helper вкладки «Поддержка» для About page."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from qfluentwidgets import SettingCardGroup, PrimaryPushSettingCard
from ui.accessibility import set_state_text
from ui.pages.about_page_support_accessibility import set_support_card_accessibility
from ui.theme import get_themed_qta_icon


@dataclass(slots=True)
class AboutPageSupportWidgets:
    """Виджеты страницы поддержки.

    Все поля могут быть None: карточки строятся только под заданные в
    branding.py каналы. Потребители (about_page.py) проверяют на None.
    """

    discussions_group: object = None
    discussions_card: object = None
    community_group: object = None
    telegram_card: object = None
    discord_card: object = None


def build_about_page_support_content(
    layout,
    *,
    tr_fn: Callable[[str, str], str],
    content_parent,
    tokens,
    on_open_discussions,
    on_open_telegram,
    on_open_discord,
) -> AboutPageSupportWidgets:
    # Раньше здесь было три карточки с каналами автора исходников:
    # GitHub Discussions в youtubediscord/zapret, его Telegram и Discord.
    # Удалены. Остаётся одна карточка — и только если в branding.py
    # задан SUPPORT_URL или SUPPORT_EMAIL.
    from branding import SUPPORT_EMAIL, SUPPORT_URL

    discussions_group = None
    discussions_card = None

    target = SUPPORT_URL or (f"mailto:{SUPPORT_EMAIL}" if SUPPORT_EMAIL else "")
    if not target:
        layout.addStretch()
        return AboutPageSupportWidgets()

    discussions_title = tr_fn("page.about.support.section.discussions", "Техническая поддержка")
    discussions_group = SettingCardGroup(discussions_title, content_parent)
    set_state_text(discussions_group, f"Раздел поддержки: {discussions_title}")
    discussions_card = PrimaryPushSettingCard(
        tr_fn("page.about.support.discussions.button", "Открыть"),
        get_themed_qta_icon("fa5s.life-ring", color=tokens.accent_hex),
        tr_fn("page.about.support.discussions.title", "Обращение в поддержку"),
        tr_fn(
            "page.about.support.discussions.desc",
            "Задать вопрос, описать проблему и приложить материалы.",
        ),
    )
    set_support_card_accessibility(
        discussions_card,
        action_name=tr_fn("page.about.support.discussions.accessible_name", "Открыть поддержку"),
        description=tr_fn(
            "page.about.support.discussions.desc",
            "Задать вопрос, описать проблему и приложить материалы.",
        ),
    )
    discussions_card.clicked.connect(on_open_discussions)
    discussions_group.addSettingCard(discussions_card)
    layout.addWidget(discussions_group)
    layout.addStretch()

    return AboutPageSupportWidgets(
        discussions_group=discussions_group,
        discussions_card=discussions_card,
    )
