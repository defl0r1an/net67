"""Build-helper нижних секций Appearance page.

Разделы «Праздничное оформление», «Эффект акрилика» и
«Производительность» удалены: гирлянда и снежинки к работе программы
отношения не имеют, ползунок прозрачности ни на что не влиял, а
переключатели производительности не давали заметной разницы. Остались
только подписи доступности — их всё ещё зовёт страница, но уже с
None-значениями, и они на это рассчитаны.
"""

from __future__ import annotations


from ui.accessibility import set_control_accessibility, set_state_text


def update_holiday_checkbox_accessibility(checkbox, *, title: str) -> None:
    if checkbox is None:
        return
    title_text = str(title or "").strip() or "Праздничный эффект"
    if checkbox.isChecked():
        state = "включено"
    else:
        state = "выключено"
    text = f"{title_text}, {state}"
    set_state_text(checkbox, text)
    set_control_accessibility(
        checkbox,
        name=text,
        description=(
            f"{title_text}. Переключатель праздничного эффекта оформления."
        ),
    )


def update_opacity_slider_accessibility(slider, value: object | None = None) -> None:
    if slider is None:
        return
    try:
        current_value = int(slider.value() if value is None else value)
    except Exception:
        current_value = 100
    title = str(slider.property("appearanceOpacityTitle") or "Прозрачность окна").strip()
    description = str(slider.property("appearanceOpacityDescription") or "").strip()
    state = f"{title}, значение: {current_value}%"
    set_state_text(slider, state)
    set_control_accessibility(
        slider,
        name=state,
        description=description or "Настройка прозрачности окна приложения.",
    )


def update_opacity_value_label_accessibility(label, value: object | None = None) -> None:
    if label is None:
        return
    try:
        current_value = int(value)
    except Exception:
        try:
            current_value = int(str(label.text() or "").strip().rstrip("%"))
        except Exception:
            current_value = 100
    set_state_text(label, f"Текущее значение прозрачности окна: {current_value}%")
