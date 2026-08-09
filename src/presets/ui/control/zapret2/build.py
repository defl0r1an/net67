"""Build-helper верхних секций для Zapret2ModeControlPage."""

from __future__ import annotations

from dataclasses import dataclass

from settings.mode import EXE_NAME_WINWS1
from presets.ui.control.shared_builders import (
    build_mode_management_section_common,
    build_mode_status_section_common,
)


@dataclass(slots=True)
class Zapret2StatusWidgets:
    section_label: object
    card: object
    status_dot: object
    status_title: object
    status_desc: object


@dataclass(slots=True)
class Zapret2ManagementWidgets:
    section_label: object
    card: object
    start_btn: object
    stop_winws_btn: object
    stop_and_exit_btn: object
    progress_bar: object
    loading_label: object

def build_winws2_pages_status_section(
    *,
    add_section_title,
    tr_fn,
    strong_body_label_cls,
    caption_label_cls,
) -> Zapret2StatusWidgets:
    section_label = add_section_title(return_widget=True, text_key="page.winws2_control.section.status")
    status_card, status_dot, status_title, status_desc = build_mode_status_section_common(
        tr_fn=tr_fn,
        strong_body_label_cls=strong_body_label_cls,
        caption_label_cls=caption_label_cls,
        checking_key="page.winws2_control.status.checking",
        checking_default="Проверка...",
        detecting_key="page.winws2_control.status.detecting",
        detecting_default="Определение состояния процесса",
    )

    return Zapret2StatusWidgets(
        section_label=section_label,
        card=status_card,
        status_dot=status_dot,
        status_title=status_title,
        status_desc=status_desc,
    )


def build_winws2_pages_management_section(
    *,
    add_section_title,
    tr_fn,
    caption_label_cls,
    indeterminate_progress_bar_cls,
    big_action_button_cls,
    stop_button_cls,
    on_start,
    on_stop,
    on_stop_and_exit,
    parent,
) -> Zapret2ManagementWidgets:
    section_label = add_section_title(return_widget=True, text_key="page.winws2_control.section.management")
    control_card, start_btn, stop_winws_btn, stop_and_exit_btn, progress_bar, loading_label = (
        build_mode_management_section_common(
            tr_fn=tr_fn,
            caption_label_cls=caption_label_cls,
            indeterminate_progress_bar_cls=indeterminate_progress_bar_cls,
            big_action_button_cls=big_action_button_cls,
            stop_button_cls=stop_button_cls,
            start_key="page.winws2_control.button.start",
            start_default="Запустить net67",
            stop_key="page.winws2_control.button.stop_only_winws",
            stop_default=f"Остановить только {EXE_NAME_WINWS1}",
            stop_exit_key="page.winws2_control.button.stop_and_exit",
            stop_exit_default="Остановить и закрыть программу",
            on_start=on_start,
            on_stop=on_stop,
            on_stop_and_exit=on_stop_and_exit,
            parent=parent,
        )
    )

    # Главный экран: крупная кнопка по центру вместо строки кнопок в
    # углу. Кнопки те же — у них уже настроены обработчики, доступность
    # и переключение видимости, — меняется только их подача.
    try:
        from qfluentwidgets import SubtitleLabel

        from ui.widgets.hero_control import build_hero_control_card

        control_card = build_hero_control_card(
            start_btn=start_btn,
            stop_winws_btn=stop_winws_btn,
            stop_and_exit_btn=stop_and_exit_btn,
            progress_bar=progress_bar,
            loading_label=loading_label,
            title_label_cls=SubtitleLabel,
            caption_label_cls=caption_label_cls,
            parent=parent,
        )
    except Exception as exc:
        # Оформление не вправе оставить человека без кнопки включения:
        # не собралось — остаётся прежняя карточка, она рабочая.
        from log.log import log

        log(f"Главный экран не собран, остаётся прежний вид: {exc}", "⚠ WARNING")

    return Zapret2ManagementWidgets(
        section_label=section_label,
        card=control_card,
        start_btn=start_btn,
        stop_winws_btn=stop_winws_btn,
        stop_and_exit_btn=stop_and_exit_btn,
        progress_bar=progress_bar,
        loading_label=loading_label,
    )
