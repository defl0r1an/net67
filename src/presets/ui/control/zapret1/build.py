"""Build-helper верхних секций для Zapret1ModeControlPage."""

from __future__ import annotations

from dataclasses import dataclass

from settings.mode import EXE_NAME_WINWS1
from presets.ui.control.shared_builders import (
    build_mode_management_section_common,
    build_mode_status_section_common,
)


@dataclass(slots=True)
class Zapret1StatusWidgets:
    card: object
    status_dot: object
    status_title: object
    status_desc: object


@dataclass(slots=True)
class Zapret1ManagementWidgets:
    card: object
    start_btn: object
    stop_winws_btn: object
    stop_and_exit_btn: object
    progress_bar: object
    loading_label: object


def build_winws1_pages_status_section(
    *,
    tr_fn,
    strong_body_label_cls,
    caption_label_cls,
) -> Zapret1StatusWidgets:
    status_card, status_dot, status_title, status_desc = build_mode_status_section_common(
        tr_fn=tr_fn,
        strong_body_label_cls=strong_body_label_cls,
        caption_label_cls=caption_label_cls,
        checking_key="page.winws1_control.status.checking",
        checking_default="Проверка...",
        detecting_key="page.winws1_control.status.detecting",
        detecting_default="Определение состояния процесса",
    )

    return Zapret1StatusWidgets(
        card=status_card,
        status_dot=status_dot,
        status_title=status_title,
        status_desc=status_desc,
    )


def build_winws1_pages_management_section(
    *,
    tr_fn,
    caption_label_cls,
    indeterminate_progress_bar_cls,
    big_action_button_cls,
    stop_button_cls,
    on_start,
    on_stop,
    on_stop_and_exit,
    parent,
) -> Zapret1ManagementWidgets:
    control_card, start_btn, stop_winws_btn, stop_and_exit_btn, progress_bar, loading_label = (
        build_mode_management_section_common(
            tr_fn=tr_fn,
            caption_label_cls=caption_label_cls,
            indeterminate_progress_bar_cls=indeterminate_progress_bar_cls,
            big_action_button_cls=big_action_button_cls,
            stop_button_cls=stop_button_cls,
            start_key="page.winws1_control.button.start",
            start_default="Запустить net67",
            stop_key="page.winws1_control.button.stop_winws",
            stop_default=f"Остановить {EXE_NAME_WINWS1}",
            stop_exit_key="page.winws1_control.button.stop_and_exit",
            stop_exit_default="Остановить и закрыть",
            on_start=on_start,
            on_stop=on_stop,
            on_stop_and_exit=on_stop_and_exit,
            parent=parent,
        )
    )

    return Zapret1ManagementWidgets(
        card=control_card,
        start_btn=start_btn,
        stop_winws_btn=stop_winws_btn,
        stop_and_exit_btn=stop_and_exit_btn,
        progress_bar=progress_bar,
        loading_label=loading_label,
    )
