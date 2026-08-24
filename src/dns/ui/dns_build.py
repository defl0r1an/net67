"""Сборка auto/custom DNS UI-блоков для страницы Network."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from dns.ui.selection import (
    ACCESSIBLE_BASE_PROPERTY,
    ACCESSIBLE_DESCRIPTION_PROPERTY,
    sync_selectable_dns_card_accessibility,
)
from dns.ui.cards import DNSChoiceCard
from ui.theme import get_cached_qta_pixmap


@dataclass(slots=True)
class AutoDnsWidgets:
    card: object
    indicator: object
    icon_label: object
    title_label: object


@dataclass(slots=True)
class CustomDnsWidgets:
    card: object
    indicator: object
    title_label: object
    primary_input: object
    secondary_input: object
    apply_button: object


class _TextValue:
    def __init__(self, value: str = ""):
        self._value = str(value or "")

    def text(self) -> str:
        return self._value

    def setText(self, value: str) -> None:  # noqa: N802
        self._value = str(value or "")


def _trigger_auto_dns_selection(on_select) -> None:
    try:
        on_select(None)
    except TypeError:
        on_select()


def _make_auto_dns_key_press_handler(on_select, fallback_key_press_event):
    def _on_key_press(event) -> None:
        try:
            key = event.key()
        except Exception:
            key = None
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            _trigger_auto_dns_selection(on_select)
            try:
                event.accept()
            except Exception:
                pass
            return
        if callable(fallback_key_press_event):
            fallback_key_press_event(event)

    return _on_key_press


def build_custom_dns_ui(
    *,
    tr_fn,
    settings_card_cls,
    qhbox_layout_cls,
    qframe_cls,
    body_label_cls,
    line_edit_cls,
    action_button_cls,
    on_apply,
    indicator_off_qss: str,
) -> CustomDnsWidgets:
    _ = settings_card_cls, qframe_cls, line_edit_cls, action_button_cls, on_apply, indicator_off_qss
    custom_card = DNSChoiceCard()
    custom_layout = qhbox_layout_cls(custom_card)
    custom_layout.setContentsMargins(18, 3, 12, 3)
    custom_layout.setSpacing(10)

    custom_icon = QLabel()
    custom_icon.setPixmap(get_cached_qta_pixmap("fa5s.edit", color="#8a929d", size=16))
    custom_layout.addWidget(custom_icon)

    custom_label = body_label_cls(tr_fn("page.network.custom.label", "Свой DNS"))
    custom_layout.addWidget(custom_label)

    custom_layout.addStretch()
    custom_primary = _TextValue()
    custom_secondary = _TextValue()

    custom_accessible_name = tr_fn("page.network.custom.accessible_name", "Свой DNS")
    custom_card.setProperty(ACCESSIBLE_BASE_PROPERTY, custom_accessible_name)
    custom_card.setProperty(
        ACCESSIBLE_DESCRIPTION_PROPERTY,
        tr_fn(
            "page.network.custom.accessible_description",
            "Для ручного DNS нажмите кнопку Свой DNS в верхней панели страницы.",
        ),
    )
    sync_selectable_dns_card_accessibility(custom_card)
    custom_card.hide()

    return CustomDnsWidgets(
        card=custom_card,
        indicator=None,
        title_label=custom_label,
        primary_input=custom_primary,
        secondary_input=custom_secondary,
        apply_button=None,
    )


def build_auto_dns_ui(
    *,
    tr_fn,
    settings_card_cls,
    qhbox_layout_cls,
    qframe_cls,
    strong_body_label_cls,
    qlabel_cls,
    qta_module,
    icon_color: str,
    indicator_off_qss: str,
    on_select,
) -> AutoDnsWidgets:
    _ = settings_card_cls, qframe_cls, indicator_off_qss
    auto_card = DNSChoiceCard()
    auto_layout = qhbox_layout_cls(auto_card)
    auto_layout.setContentsMargins(8, 3, 12, 3)
    auto_layout.setSpacing(10)

    auto_icon = qlabel_cls()
    auto_icon.setPixmap(get_cached_qta_pixmap("fa5s.sync", color=icon_color, size=16))
    auto_layout.addWidget(auto_icon)

    auto_label = strong_body_label_cls(tr_fn("page.network.dns.auto", "Автоматически (DHCP)"))
    auto_layout.addWidget(auto_label)

    auto_layout.addStretch()
    auto_card.mousePressEvent = on_select
    auto_accessible_name = tr_fn("page.network.dns.auto.accessible_name", "DNS автоматически (DHCP)")
    auto_card.setProperty(ACCESSIBLE_BASE_PROPERTY, auto_accessible_name)
    auto_card.setProperty(
        ACCESSIBLE_DESCRIPTION_PROPERTY,
        tr_fn(
            "page.network.dns.auto.accessible_description",
            "Нажмите Enter или пробел, чтобы вернуть получение DNS через DHCP.",
        ),
    )
    sync_selectable_dns_card_accessibility(auto_card)
    auto_card.keyPressEvent = _make_auto_dns_key_press_handler(
        on_select,
        getattr(auto_card, "keyPressEvent", None),
    )

    return AutoDnsWidgets(
        card=auto_card,
        indicator=None,
        icon_label=auto_icon,
        title_label=auto_label,
    )
