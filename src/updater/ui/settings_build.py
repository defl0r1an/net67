"""Build-helper settings and Telegram sections for Servers page."""

from __future__ import annotations

from dataclasses import dataclass

from ui.accessibility import set_control_accessibility, set_state_text


@dataclass(slots=True)
class ServersSettingsWidgets:
    card: object
    auto_check_card: object | None
    auto_check_toggle: object
    toggle_label: object | None
    version_info_label: object


def _label_text(label) -> str:
    try:
        value = label.text()
    except Exception:
        value = getattr(label, "text", "")
    return " ".join(str(value or "").strip().split())


def set_auto_check_accessibility(
    widget,
    *,
    title: str,
    description: str,
    checked: bool | None = None,
) -> None:
    title_value = str(title or "").strip()
    if checked is None:
        try:
            checked = bool(widget.isChecked())
        except Exception:
            checked = None
    if checked is None:
        name = title_value
    else:
        state = "включено" if bool(checked) else "выключено"
        name = f"{title_value}, {state}".strip(", ")
    set_control_accessibility(widget, name=name, description=description)
    set_state_text(widget, name)


def build_servers_settings_section(
    *,
    content_parent,
    tr_fn,
    accent_hex: str,
    auto_check_enabled: bool,
    app_version: str,
    channel: str,
    setting_card_group_cls,
    settings_card_cls,
    win11_toggle_row_cls,
    caption_label_cls,
    qhbox_layout_cls,
    on_auto_check_toggled,
) -> ServersSettingsWidgets:
    settings_card = setting_card_group_cls(tr_fn("page.servers.settings.title", "Настройки"), content_parent)

    auto_check_title = tr_fn("page.servers.settings.auto_check", "Проверять обновления при запуске")
    auto_check_description = tr_fn(
        "page.servers.settings.auto_check.description",
        "Автоматически проверять наличие обновлений при старте приложения.",
    )
    auto_check_card = win11_toggle_row_cls(
        "fa5s.sync-alt",
        auto_check_title,
        auto_check_description,
        accent_hex,
    )
    auto_check_card.setChecked(auto_check_enabled, block_signals=True)
    set_auto_check_accessibility(
        auto_check_card,
        title=auto_check_title,
        description=auto_check_description,
        checked=auto_check_enabled,
    )
    auto_check_card.toggled.connect(on_auto_check_toggled)
    auto_check_toggle = auto_check_card
    settings_card.addSettingCard(auto_check_card)

    _ = settings_card_cls, qhbox_layout_cls
    version_info_label = caption_label_cls(
        tr_fn("page.servers.settings.version_channel_template", "v{version} · {channel}").format(
            version=app_version,
            channel=channel,
        )
    )
    set_state_text(version_info_label, f"Версия net67: {_label_text(version_info_label)}")
    toggle_label = None

    return ServersSettingsWidgets(
        card=settings_card,
        auto_check_card=auto_check_card,
        auto_check_toggle=auto_check_toggle,
        toggle_label=toggle_label,
        version_info_label=version_info_label,
    )
