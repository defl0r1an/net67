from __future__ import annotations


def build_profile_setup_match_tab_text(
    *,
    match_summary: str,
    strategy_id: str = "",
    strategy_name: str = "",
    raw_strategy_text: str = "",
) -> str:
    visible_strategy_name = _visible_strategy_name(strategy_id, strategy_name)
    strategy_args = str(raw_strategy_text or "").strip() or "Стратегия не выбрана"
    blocks = (
        ("Когда profile применяется", str(match_summary or "без явных условий").strip()),
        ("Текущая готовая стратегия", visible_strategy_name),
        ("Аргументы готовой стратегии", strategy_args),
    )

    lines: list[str] = []
    for title, text in blocks:
        lines.append(title)
        lines.append("=" * len(title))
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip()


def _visible_strategy_name(strategy_id: str, strategy_name: str) -> str:
    clean_strategy_id = str(strategy_id or "").strip()
    clean_strategy_name = str(strategy_name or "").strip()
    if not clean_strategy_name or clean_strategy_id in {"", "none"}:
        return "Стратегия не выбрана"
    if clean_strategy_id == "custom":
        return "Своя стратегия"
    return clean_strategy_name
