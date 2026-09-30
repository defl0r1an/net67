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



