"""Сборка панели ручных DNS-действий для страницы Network."""

from __future__ import annotations

from dataclasses import dataclass

from qfluentwidgets import FluentIcon

from ui.accessibility import set_control_accessibility, set_state_text
from ui.fluent_widgets import QuickActionsBar, set_tooltip


@dataclass(slots=True)
class ForceDnsCardWidgets:
    card: object
    force_button: object
    status_label: object
    reset_button: object
    custom_button: object


def build_force_dns_card_ui(
    *,
    parent,
    content_parent,
    add_section_title_fn,
    tr_fn,
    add_widget_fn,
    get_theme_tokens_fn,
    get_force_dns_status_fn,
    setting_card_group_cls,
    caption_label_cls,
    action_button_cls,
    win11_toggle_row_cls,
    qwidget_cls,
    qvbox_layout_cls,
    qhbox_layout_cls,
    qt_namespace,
    insert_widget_into_setting_card_group_fn,
    enable_setting_card_group_auto_height_fn,
    on_toggle,
    on_confirm_reset,
    on_custom_dns=None,
) -> tuple[bool, ForceDnsCardWidgets]:
    tokens = get_theme_tokens_fn()
    force_dns_active = False
    _ = tokens
    _ = parent
    _ = setting_card_group_cls
    _ = win11_toggle_row_cls
    _ = qwidget_cls
    _ = qvbox_layout_cls
    _ = qhbox_layout_cls
    _ = qt_namespace
    _ = insert_widget_into_setting_card_group_fn
    _ = enable_setting_card_group_auto_height_fn

    force_dns_card = QuickActionsBar(content_parent)
    _ = on_toggle

    force_dns_reset_dhcp_btn = action_button_cls(
        tr_fn("page.network.force_dns.reset.button", "Вернуть DNS автоматически"),
        icon=FluentIcon.RETURN,
    )
    force_dns_reset_dhcp_btn.clicked.connect(on_confirm_reset)
    reset_description = tr_fn(
        "page.network.force_dns.action.reset.description",
        "DNS будет снова получаться автоматически от роутера или провайдера через DHCP. Это полезно, если интернет работает нестабильно после ручной настройки DNS.",
    )
    set_tooltip(force_dns_reset_dhcp_btn, reset_description)
    reset_name = tr_fn("page.network.force_dns.reset.accessible_name", "Вернуть DNS автоматически")
    set_state_text(force_dns_reset_dhcp_btn, reset_name)
    set_control_accessibility(
        force_dns_reset_dhcp_btn,
        name=reset_name,
        description=reset_description,
    )

    custom_dns_btn = action_button_cls(
        tr_fn("page.network.custom.button", "Добавить свой DNS"),
        icon=FluentIcon.EDIT,
    )
    if callable(on_custom_dns):
        custom_dns_btn.clicked.connect(on_custom_dns)
    custom_description = tr_fn(
        "page.network.custom.button.description",
        "Открывает окно добавления нового DNS сервера.",
    )
    set_tooltip(custom_dns_btn, custom_description)
    custom_name = tr_fn("page.network.custom.button.accessible_name", "Добавить свой DNS")
    set_state_text(custom_dns_btn, custom_name)
    set_control_accessibility(
        custom_dns_btn,
        name=custom_name,
        description=custom_description,
    )

    force_dns_status_label = caption_label_cls("")
    force_dns_status_label.setWordWrap(True)
    force_dns_status_label.setVisible(False)

    force_dns_card.add_buttons((force_dns_reset_dhcp_btn, custom_dns_btn))

    add_widget_fn(force_dns_card)

    return force_dns_active, ForceDnsCardWidgets(
        card=force_dns_card,
        force_button=None,
        status_label=force_dns_status_label,
        reset_button=force_dns_reset_dhcp_btn,
        custom_button=custom_dns_btn,
    )
