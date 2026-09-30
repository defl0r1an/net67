"""Build-helper основных секций для Zapret2ModeControlPage."""

from __future__ import annotations

from dataclasses import dataclass

from presets.ui.control.shared_builders import (
    build_deferred_themed_push_setting_card_common,
    build_docs_card,
    build_bypass_tour_card_common,
    build_onboarding_tour_card_common,
    build_updates_card,
)
from ui.build_timing import BuildStepTimer
from presets.ui.control.windows_features.build import build_state_media_block_toggle, build_windows_feature_toggles
from ui.fluent_widgets import build_additional_settings_section, enable_setting_card_group_auto_height


@dataclass(slots=True)
class Zapret2SettingsBuildWidgets:
    program_settings_section_label: object | None
    program_settings_card: object
    gui_autostart_toggle: object
    auto_dpi_toggle: object
    tray_close_mode_combo: object
    defender_toggle: object
    max_block_toggle: object
    additional_settings_card: object
    additional_settings_notice: object
    discord_restart_toggle: object | None
    telegram_proxy_toggle: object | None
    wssize_toggle: object | None
    debug_log_toggle: object | None
    extra_section_label: object | None
    extra_card: object
    test_card: object
    internet_cleanup_card: object
    folder_card: object
    state_media_block_toggle: object
    tour_card: object | None = None
    bypass_tour_card: object | None = None


def build_winws2_pages_settings_sections(
    *,
    add_section_title,
    tr_fn,
    content_parent,
    setting_card_group_cls,
    push_setting_card_cls,
    win11_toggle_row_cls,
    win11_combo_row_cls,
    on_gui_autostart_toggled,
    on_auto_dpi_toggled,
    on_tray_close_mode_changed,
    on_defender_toggled,
    on_max_blocker_toggled,
    on_state_media_block_toggled,
    on_discord_restart_changed,
    on_telegram_proxy_with_bypass_toggled,
    on_wssize_toggled,
    on_debug_log_toggled,
    on_open_connection_test,
    on_open_internet_cleanup,
    on_open_folder,
    on_open_onboarding_tour=None,
    on_open_bypass_tour=None,
) -> Zapret2SettingsBuildWidgets:
    # Пошаговый замер: на машине пользователя эта сборка идёт 9,4 с, а на
    # машине разработчика — 91 мс. Угадывать виноватый виджет нельзя,
    # поэтому шаги мерятся там, где медленно. Молчит, пока всё быстро.
    timer = BuildStepTimer("winws2 settings sections")

    program_settings_title = tr_fn("page.winws2_control.section.program_settings", "Настройки программы")
    program_settings_section_label = None
    program_settings_card = setting_card_group_cls(program_settings_title, content_parent)

    with timer.step("gui_autostart_toggle"):
        gui_autostart_toggle = win11_toggle_row_cls(
            "fa5s.power-off",
            tr_fn("page.control.setting.gui_autostart.title", "Автозапуск net67"),
            tr_fn("page.control.setting.gui_autostart.desc", "Запускать программу в трее при входе в Windows"),
        )
    gui_autostart_toggle.toggled.connect(on_gui_autostart_toggled)

    with timer.step("auto_dpi_toggle"):
        auto_dpi_toggle = win11_toggle_row_cls(
            "fa5s.bolt",
            tr_fn("page.winws2_control.setting.autostart.title", "Автозапуск обхода после старта программы"),
            tr_fn("page.winws2_control.setting.autostart.desc", "После запуска net67 сразу включать обход с текущим пресетом"),
        )
    auto_dpi_toggle.toggled.connect(on_auto_dpi_toggled)

    with timer.step("tray_close_mode_combo"):
        tray_close_mode_combo = win11_combo_row_cls(
            "fa5s.window-minimize",
            tr_fn("page.control.setting.tray_close_mode.title", "Поведение окна и трея"),
            tr_fn("page.control.setting.tray_close_mode.desc", "Выберите, когда net67 будет скрывать окно в системный трей"),
            items=[
                ("Свернуть и крестик скрывают в трей", "minimize_and_close"),
                ("Только свернуть скрывает в трей", "minimize_only"),
                ("Не скрывать в трей", "normal"),
            ],
        )
    tray_close_mode_combo.combo.setFixedWidth(270)
    tray_close_mode_combo.combo.currentIndexChanged.connect(
        lambda _index: on_tray_close_mode_changed(tray_close_mode_combo.currentData())
    )

    with timer.step("telegram_proxy_toggle"):
        # Место — «Настройки программы», рядом с автозапуском.
        #
        # Раньше тумблер лежал в дополнительных настройках, под красной
        # надписью «изменяйте только если знаете что делаете». Но это не
        # параметр движка, а поведение программы: поднимать ли прокси
        # Telegram вместе с обходом. Прятать такое за предупреждением —
        # значит прятать от тех, кому оно и нужно.
        telegram_proxy_toggle = (
            win11_toggle_row_cls(
                "fa5b.telegram-plane",
                "Прокси Telegram вместе с обходом",
                "Поднимать локальный прокси Telegram при включении обхода",
                "#2aabee",
            )
            if win11_toggle_row_cls
            else None
        )
    if telegram_proxy_toggle:
        telegram_proxy_toggle.toggled.connect(on_telegram_proxy_with_bypass_toggled)

    with timer.step("windows_feature_toggles"):
        windows_feature_toggles = build_windows_feature_toggles(
            tr_fn=tr_fn,
            win11_toggle_row_cls=win11_toggle_row_cls,
            on_defender_toggled=on_defender_toggled,
            on_max_blocker_toggled=on_max_blocker_toggled,
        )

    program_settings_card.addSettingCard(gui_autostart_toggle)
    program_settings_card.addSettingCard(auto_dpi_toggle)
    if telegram_proxy_toggle:
        program_settings_card.addSettingCard(telegram_proxy_toggle)
    program_settings_card.addSettingCard(tray_close_mode_combo)
    program_settings_card.addSettingCard(windows_feature_toggles.defender_toggle)
    program_settings_card.addSettingCard(windows_feature_toggles.max_block_toggle)
    # Повтор тура — в «Настройках программы», а не среди прочего внизу:
    # эта группа остаётся и в простом виде, где тур нужнее всего.
    tour_card = None
    if on_open_onboarding_tour is not None:
        with timer.step("onboarding_tour_card"):
            tour_card = build_onboarding_tour_card_common(
                push_setting_card_cls=push_setting_card_cls,
                tr_fn=tr_fn,
                on_click=on_open_onboarding_tour,
                parent=content_parent,
            )
        program_settings_card.addSettingCard(tour_card)
    bypass_tour_card = None
    if on_open_bypass_tour is not None:
        with timer.step("bypass_tour_card"):
            bypass_tour_card = build_bypass_tour_card_common(
                push_setting_card_cls=push_setting_card_cls,
                tr_fn=tr_fn,
                on_click=on_open_bypass_tour,
                parent=content_parent,
            )
        program_settings_card.addSettingCard(bypass_tour_card)

    with timer.step("program_settings_card_auto_height"):
        enable_setting_card_group_auto_height(program_settings_card)

    with timer.step("discord_restart_toggle"):
        discord_restart_toggle = (
            win11_toggle_row_cls(
                "fa5b.discord",
                "Перезапуск Discord",
                "Автоперезапуск при смене стратегии",
                "#7289da",
            )
            if win11_toggle_row_cls
            else None
        )
    if discord_restart_toggle:
        discord_restart_toggle.toggled.connect(on_discord_restart_changed)

    with timer.step("wssize_toggle"):
        wssize_toggle = (
            win11_toggle_row_cls(
                "fa5s.ruler-horizontal",
                "Включить --wssize",
                "Добавляет параметр размера окна TCP",
            )
            if win11_toggle_row_cls
            else None
        )
    if wssize_toggle:
        wssize_toggle.toggled.connect(on_wssize_toggled)

    with timer.step("debug_log_toggle"):
        debug_log_toggle = (
            win11_toggle_row_cls(
                "fa5s.file-alt",
                "Включить лог-файл (--debug)",
                "Записывает логи winws в папку logs",
            )
            if win11_toggle_row_cls
            else None
        )
    if debug_log_toggle:
        debug_log_toggle.toggled.connect(on_debug_log_toggled)

    with timer.step("additional_settings_section"):
        additional_settings_card, additional_settings_notice = build_additional_settings_section(
            title=tr_fn("page.winws2_control.card.advanced", "Дополнительные настройки"),
            warning_text=tr_fn("page.winws2_control.advanced.warning", "Изменяйте только если знаете что делаете"),
            parent=content_parent,
            toggle_rows=[discord_restart_toggle, wssize_toggle, debug_log_toggle],
            action_rows=[],
        )

    extra_section_label = None
    extra_card = setting_card_group_cls(
        tr_fn("page.winws2_control.section.additional", "Дополнительные действия"),
        content_parent,
    )
    with timer.step("test_card"):
        test_card = build_deferred_themed_push_setting_card_common(
        push_setting_card_cls=push_setting_card_cls,
        button_text=tr_fn("page.winws2_control.button.open", "Открыть"),
        icon_name="fa5s.wifi",
        icon_color="#60cdff",
        title_text=tr_fn("page.winws2_control.button.connection_test", "Тест соединения"),
        content_text=tr_fn("page.winws2_control.button.connection_test.desc", "Проверить доступность сети и состояние обхода"),
        on_click=on_open_connection_test,
        button_accessible_name=tr_fn("page.winws2_control.button.connection_test.accessible_name", "Открыть тест соединения"),
        parent=content_parent,
    )
    with timer.step("internet_cleanup_card"):
        internet_cleanup_card = build_deferred_themed_push_setting_card_common(
        push_setting_card_cls=push_setting_card_cls,
        button_text=tr_fn("page.control.internet_cleanup.button", "Сбросить"),
        icon_name="fa5s.network-wired",
        icon_color="#4cc38a",
        title_text=tr_fn("page.control.internet_cleanup.title", "Сбросить сеть Windows"),
        content_text=tr_fn(
            "page.control.internet_cleanup.desc",
            "Очистить DNS, proxy, Winsock и сетевые параметры. Может понадобиться перезагрузка",
        ),
        on_click=on_open_internet_cleanup,
        button_accessible_name=tr_fn("page.control.internet_cleanup.accessible_name", "Сбросить сеть Windows"),
        parent=content_parent,
    )
    with timer.step("folder_card"):
        folder_card = build_deferred_themed_push_setting_card_common(
        push_setting_card_cls=push_setting_card_cls,
        button_text=tr_fn("page.winws2_control.button.open", "Открыть"),
        icon_name="fa5s.folder-open",
        icon_color="#f5c04d",
        title_text=tr_fn("page.winws2_control.button.open_folder", "Открыть папку"),
        content_text=tr_fn("page.winws2_control.button.open_folder.desc", "Перейти в папку программы и служебных файлов"),
        on_click=on_open_folder,
        button_accessible_name=tr_fn("page.winws2_control.button.open_folder.accessible_name", "Открыть папку программы"),
        parent=content_parent,
    )
    with timer.step("updates_card"):
        updates_card = build_updates_card(
            push_setting_card_cls=push_setting_card_cls,
            tr_fn=tr_fn,
            parent=content_parent,
        )
    with timer.step("wiki_card"):
        wiki_card = build_docs_card(
            push_setting_card_cls=push_setting_card_cls,
            tr_fn=tr_fn,
            parent=content_parent,
        )
    with timer.step("state_media_block_toggle"):
        state_media_block_toggle = build_state_media_block_toggle(
            tr_fn=tr_fn,
            win11_toggle_row_cls=win11_toggle_row_cls,
            on_state_media_block_toggled=on_state_media_block_toggled,
        )
    extra_card.addSettingCard(test_card)
    extra_card.addSettingCard(internet_cleanup_card)
    extra_card.addSettingCard(folder_card)
    extra_card.addSettingCard(updates_card)
    extra_card.addSettingCard(wiki_card)
    extra_card.addSettingCard(state_media_block_toggle)
    with timer.step("extra_card_auto_height"):
        enable_setting_card_group_auto_height(extra_card)

    timer.finish()

    return Zapret2SettingsBuildWidgets(
        program_settings_section_label=program_settings_section_label,
        program_settings_card=program_settings_card,
        gui_autostart_toggle=gui_autostart_toggle,
        auto_dpi_toggle=auto_dpi_toggle,
        tray_close_mode_combo=tray_close_mode_combo,
        defender_toggle=windows_feature_toggles.defender_toggle,
        max_block_toggle=windows_feature_toggles.max_block_toggle,
        additional_settings_card=additional_settings_card,
        additional_settings_notice=additional_settings_notice,
        discord_restart_toggle=discord_restart_toggle,
        telegram_proxy_toggle=telegram_proxy_toggle,
        wssize_toggle=wssize_toggle,
        debug_log_toggle=debug_log_toggle,
        extra_section_label=extra_section_label,
        extra_card=extra_card,
        test_card=test_card,
        internet_cleanup_card=internet_cleanup_card,
        folder_card=folder_card,
        state_media_block_toggle=state_media_block_toggle,
        tour_card=tour_card,
        bypass_tour_card=bypass_tour_card,
    )
