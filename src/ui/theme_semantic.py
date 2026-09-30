"""Semantic color helpers for status-oriented UI elements."""

from __future__ import annotations

from dataclasses import dataclass

from ui.theme import get_theme_tokens


@dataclass(frozen=True)
class SemanticPalette:
    on_color: str

    success: str
    warning: str
    error: str
    info: str

    # Читаемый цвет текста/значка статуса поверх мягкого фона: в светлой теме
    # яркие success/warning/error слишком бледные, поэтому берутся тёмные
    # оттенки Windows 11.
    success_text: str
    warning_text: str
    error_text: str

    warning_soft: str
    warning_soft_bg: str
    warning_button: str
    warning_button_hover: str
    warning_button_disabled: str

    error_soft_bg: str
    error_soft_border: str

    danger_bg_soft: str
    danger_bg: str
    danger_bg_strong: str

    danger_button: str
    danger_button_hover: str
    success_button: str
    success_button_hover: str

    success_badge: str
    success_soft_bg: str
    success_soft_border: str

    # Янтарные Premium-метки и серая метка Free.
    premium_fg: str
    premium_bg: str
    premium_bg_hover: str
    neutral_badge_fg: str
    neutral_badge_bg: str
    neutral_badge_bg_hover: str


def get_semantic_palette(theme_name: str | None = None) -> SemanticPalette:
    tokens = get_theme_tokens(theme_name)
    on_color = "rgba(18, 18, 18, 0.92)" if tokens.is_light else "rgba(245, 245, 245, 0.95)"
    success = "#6ccb5f"
    warning = "#ff9800"
    error = "#ff5252"

    # Интерфейс чёрно-серо-белый, поэтому и статусы монохромные: цвет
    # больше не несёт смысла, его несут текст и значок. Светлота ступеней
    # сохранена от прежних цветных значений, чтобы «опасное» осталось
    # контрастнее «обычного», а не слилось с ним.
    #
    # Ступени берутся из branding: две независимые серые шкалы в одном
    # приложении разъехались бы при первой же правке.
    from branding import NEUTRAL_RAMP

    strong = NEUTRAL_RAMP[100] if not tokens.is_light else NEUTRAL_RAMP[900]
    mid = NEUTRAL_RAMP[300] if not tokens.is_light else NEUTRAL_RAMP[700]
    soft = NEUTRAL_RAMP[400] if not tokens.is_light else NEUTRAL_RAMP[600]
    wash = "255, 255, 255" if not tokens.is_light else "0, 0, 0"

    return SemanticPalette(
        on_color=on_color,
        success=mid,
        warning=mid,
        error=strong,
        info=tokens.accent_hex,
        success_text=mid,
        warning_text=mid,
        error_text=strong,
        warning_soft=f"rgba({wash}, 0.72)",
        warning_soft_bg=f"rgba({wash}, 0.10)",
        warning_button=soft,
        warning_button_hover=mid,
        warning_button_disabled=f"rgba({wash}, 0.28)",
        error_soft_bg=f"rgba({wash}, 0.12)",
        error_soft_border=f"rgba({wash}, 0.34)",
        danger_bg_soft=f"rgba({wash}, 0.16)",
        danger_bg=f"rgba({wash}, 0.24)",
        danger_bg_strong=f"rgba({wash}, 0.34)",
        danger_button=NEUTRAL_RAMP[800] if tokens.is_light else NEUTRAL_RAMP[200],
        danger_button_hover=NEUTRAL_RAMP[900] if tokens.is_light else NEUTRAL_RAMP[100],
        success_button=soft,
        success_button_hover=mid,
        success_badge=mid,
        success_soft_bg=f"rgba({wash}, 0.10)",
        success_soft_border=f"rgba({wash}, 0.30)",
        # Премиум-меток в net67 нет, но поле объявлено в палитре исходного
        # проекта, и его читает общий стиль меток в fluent_widgets.
        premium_fg=mid,
        premium_bg=f"rgba({wash}, 0.16)",
        premium_bg_hover=f"rgba({wash}, 0.28)",
        neutral_badge_fg=tokens.fg_muted,
        neutral_badge_bg=f"rgba({wash}, 0.16)",
        neutral_badge_bg_hover=f"rgba({wash}, 0.28)",
    )
