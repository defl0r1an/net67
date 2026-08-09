"""Build-helper вкладки «Справка» для About page."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy

from branding import APP_NAME, APP_ORG, APP_TAGLINE
from ui.pages.about_page_help_accessibility import set_help_card_accessibility
from ui.accessibility import set_state_text


@dataclass(slots=True)
class AboutPageHelpWidgets:
    """Виджеты вкладки «Справка».

    Все поля кроме motto_wrap могут быть None: карточки строятся только под
    те ссылки, которые заданы в branding.py. Если ссылок нет — секция не
    создаётся вообще. Потребители (about_page.py) уже проверяют на None.
    """

    motto_wrap: object
    docs_group: object = None
    forum_card: object = None
    info_card: object = None
    android_card: object = None
    github_card: object = None
    news_group: object = None
    telegram_card: object = None
    mastodon_card: object = None
    bastyon_card: object = None


def build_about_page_motto_block(*, tr_fn: Callable[[str, str], str], tokens):
    motto_wrap = QFrame()
    motto_wrap.setStyleSheet("QFrame { background: transparent; border: none; }")

    motto_row = QHBoxLayout(motto_wrap)
    motto_row.setContentsMargins(0, 0, 0, 0)
    motto_row.setSpacing(0)

    motto_text_wrap = QFrame()
    motto_text_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    motto_text_wrap.setStyleSheet("QFrame { background: transparent; border: none; }")

    motto_text_layout = QVBoxLayout(motto_text_wrap)
    motto_text_layout.setContentsMargins(0, 0, 0, 0)
    motto_text_layout.setSpacing(2)

    # Раньше здесь стоял авторский слоган проекта. Заменён на название
    # продукта из branding.py — правится в одном месте.
    motto_title = QLabel(APP_NAME)
    motto_title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
    motto_title.setWordWrap(True)
    motto_title.setStyleSheet(
        f"QLabel {{ color: {tokens.fg}; font-size: 25px; font-weight: 700; "
        f"letter-spacing: 0.8px; "
        f"font-family: 'Segoe UI Variable Display', 'Segoe UI', sans-serif; }}"
    )

    motto_translate = QLabel(APP_TAGLINE)
    motto_translate.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
    motto_translate.setWordWrap(True)
    motto_translate.setStyleSheet(
        f"QLabel {{ color: {tokens.fg_muted}; font-size: 17px; font-style: italic; "
        f"font-weight: 600; letter-spacing: 0.5px; "
        f"font-family: 'Palatino Linotype', 'Book Antiqua', 'Georgia', serif; "
        f"padding-top: 2px; }}"
    )

    motto_cta = QLabel(APP_ORG)
    motto_cta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
    motto_cta.setWordWrap(True)
    motto_cta.setStyleSheet(
        f"QLabel {{ color: {tokens.fg_faint}; font-size: 12px; letter-spacing: 1.1px; "
        f"font-family: 'Segoe UI', sans-serif; text-transform: uppercase; "
        f"padding-top: 6px; }}"
    )

    # Пустые строки брендинга не должны оставлять дыры в вёрстке.
    motto_translate.setVisible(bool(APP_TAGLINE))
    motto_cta.setVisible(bool(APP_ORG))

    motto_text_layout.addWidget(motto_title)
    motto_text_layout.addWidget(motto_translate)
    motto_text_layout.addWidget(motto_cta)
    motto_row.addWidget(motto_text_wrap, 1)
    return motto_wrap


def build_about_page_help_content(
    layout: QVBoxLayout,
    *,
    tr_fn: Callable[[str, str], str],
    tokens,
    content_parent,
    make_section_label: Callable[[str], object],
    hyperlink_card_cls,
    push_setting_card_cls,
    setting_card_group_cls,
    fluent_icon,
    on_open_forum,
    on_open_telegram_news,
) -> AboutPageHelpWidgets:
    # Раньше здесь было восемь карточек с внешними ссылками автора проекта:
    # вики, руководство, инструкция для Android, GitHub, Telegram, Mastodon,
    # Bastyon. Все они удалены вместе с остальными упоминаниями автора.
    #
    # Секция «Ссылки» теперь строится только из branding.py. Пока
    # DOCS_URL и SUPPORT_URL пустые, вкладка показывает один блок с
    # названием продукта — лишних разделов не появляется.
    from branding import DOCS_URL, SUPPORT_URL

    motto_wrap = build_about_page_motto_block(tr_fn=tr_fn, tokens=tokens)
    layout.addWidget(motto_wrap)

    docs_group = None
    forum_card = None
    info_card = None

    if DOCS_URL or SUPPORT_URL:
        layout.addSpacing(6)
        layout.addWidget(make_section_label(tr_fn("page.about.help.section.links", "Ссылки")))

        docs_title = tr_fn("page.about.help.group.docs", "Документация")
        docs_group = setting_card_group_cls(docs_title, content_parent)
        set_state_text(docs_group, f"Раздел справки: {docs_title}")

        cards = []

        if DOCS_URL:
            info_card = hyperlink_card_cls(
                DOCS_URL,
                tr_fn("page.about.help.button.open", "Открыть"),
                fluent_icon.INFO,
                tr_fn("page.about.help.docs.info.title", "Документация"),
                tr_fn("page.about.help.docs.info.desc", "Руководство и ответы на вопросы"),
            )
            set_help_card_accessibility(
                info_card,
                action_name=tr_fn(
                    "page.about.help.docs.info.accessible_name",
                    "Открыть руководство и ответы",
                ),
                description=tr_fn(
                    "page.about.help.docs.info.desc",
                    "Руководство и ответы на вопросы",
                ),
            )
            cards.append(info_card)

        if SUPPORT_URL:
            forum_card = hyperlink_card_cls(
                SUPPORT_URL,
                tr_fn("page.about.help.button.open", "Открыть"),
                fluent_icon.SEND,
                tr_fn("page.about.help.docs.forum.title", "Техническая поддержка"),
                tr_fn("page.about.help.docs.forum.desc", "Обращение в службу поддержки"),
            )
            set_help_card_accessibility(
                forum_card,
                action_name=tr_fn(
                    "page.about.help.docs.forum.accessible_name",
                    "Открыть техническую поддержку",
                ),
                description=tr_fn(
                    "page.about.help.docs.forum.desc",
                    "Обращение в службу поддержки",
                ),
            )
            cards.append(forum_card)

        docs_group.addSettingCards(cards)
        layout.addWidget(docs_group)

    layout.addStretch()

    return AboutPageHelpWidgets(
        motto_wrap=motto_wrap,
        docs_group=docs_group,
        forum_card=forum_card,
        info_card=info_card,
    )
