"""Runtime/status helper'ы для страницы логов."""

from __future__ import annotations

from dataclasses import dataclass

from ui.accessibility import set_state_text


#: Значок панели ошибок, когда всё чисто.
ERRORS_ICON_CLEAN = "fa5s.check-circle"

#: Значок панели ошибок, когда есть о чём сказать.
ERRORS_ICON_PROBLEM = "fa5s.exclamation-triangle"


@dataclass(frozen=True)
class ErrorsPanelView:
    """Как выглядит панель ошибок при таком числе записей."""

    has_errors: bool
    icon_name: str
    icon_color: str
    show_text: bool
    show_clear_button: bool


def errors_panel_view(*, count: int, is_light: bool) -> ErrorsPanelView:
    """Вид панели ошибок по числу записей.

    Раньше панель всегда выглядела тревожно: красный треугольник и
    пустая красная рамка под ним висели и тогда, когда ошибок не было
    ни одной. Читалось это как «что-то сломано», хотя сломано ничего не
    было, а настоящую ошибку в такой панели уже никто бы не заметил —
    она ничем не отличалась бы от обычного состояния.

    Теперь чистое состояние выглядит чистым: зелёная галочка и ничего
    больше. Рамка с текстом и красный треугольник появляются вместе с
    первой записью.
    """
    has_errors = int(count or 0) > 0

    if has_errors:
        color = "#dc2626" if is_light else "#f87171"
        return ErrorsPanelView(
            has_errors=True,
            icon_name=ERRORS_ICON_PROBLEM,
            icon_color=color,
            show_text=True,
            show_clear_button=True,
        )

    # Зелёный подобран так, чтобы читаться на обеих темах: на светлой
    # тёмный (#15803d), на тёмной светлый (#4ade80).
    color = "#15803d" if is_light else "#4ade80"
    return ErrorsPanelView(
        has_errors=False,
        icon_name=ERRORS_ICON_CLEAN,
        icon_color=color,
        show_text=False,
        show_clear_button=False,
    )


def render_send_status_label(*, label, text: str, tone: str, theme_tokens) -> None:
    if label is None:
        return

    normalized_text = str(text or "")
    normalized_tone = str(tone or "neutral").strip().lower()

    label.setText(normalized_text)
    if not normalized_text:
        label.setStyleSheet("")
        return
    set_state_text(label, normalized_text)

    color = theme_tokens.accent_hex
    if normalized_tone == "error":
        color = "#f87171" if not theme_tokens.is_light else "#dc2626"
    label.setStyleSheet(f"color: {color}; font-size: 11px;")


def resolve_winws_status_style(
    *,
    current_text: str,
    neutral_color: str,
    running_color: str,
    error_color: str,
) -> tuple[str, str]:
    text = str(current_text or "").strip()
    if not text:
        return "neutral", ""
    if "PID:" in text:
        return "running", text
    if "ошиб" in text.lower():
        return "error", text
    return "neutral", text


def set_winws_status(label, *, kind: str, text: str, neutral_color: str, running_color: str, error_color: str) -> None:
    if kind == "running":
        color = running_color
    elif kind == "error":
        color = error_color
    else:
        color = neutral_color

    label.setText(text)
    label.setStyleSheet(f"color: {color}; font-size: 11px;")


def compute_errors_text_height(*, text_edit, min_height: int, max_height: int) -> int:
    try:
        document = text_edit.document()
        is_empty = bool(document.isEmpty())
    except Exception:
        is_empty = True

    if is_empty:
        return min_height

    try:
        document_height = int(document.size().height())
    except Exception:
        document_height = min_height

    frame_height = int(text_edit.frameWidth()) * 2
    content_padding = 16
    target_height = document_height + frame_height + content_padding
    return max(min_height, min(max_height, target_height))


def errors_count_text(tr_fn, count: int) -> str:
    """Подпись со счётчиком. Ноль называется словами, а не цифрой.

    «Ошибок: 0» рядом с зелёной галочкой — лишнее уточнение к тому, что
    и так видно.
    """
    if int(count or 0) <= 0:
        return tr_fn("page.logs.errors.none", "Ошибок нет")
    return tr_fn("page.logs.errors.count", "Ошибок: {count}").format(count=int(count))


def append_errors(*, errors_text, errors_count_label, tr_fn, current_count: int, lines) -> int:
    lines = list(lines)
    if not lines:
        return int(current_count)
    # Каждая строка добавляется отдельно, как и раньше (Qt сам решает по строке,
    # обычный это текст или разметка), а счётчик обновляется один раз на пачку:
    # журнал теперь вставляется порциями, и ошибки из порции приходят вместе.
    for line in lines:
        errors_text.append(line)
    next_count = int(current_count) + len(lines)
    count_text = errors_count_text(tr_fn, next_count)
    errors_count_label.setText(count_text)
    set_state_text(errors_count_label, count_text)
    return next_count


def clear_errors(*, errors_text, errors_count_label, tr_fn) -> int:
    errors_text.clear()
    count_text = errors_count_text(tr_fn, 0)
    errors_count_label.setText(count_text)
    set_state_text(errors_count_label, count_text)
    return 0
