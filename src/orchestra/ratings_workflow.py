from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable


@dataclass(frozen=True)
class OrchestraRatingsState:
    no_runner: bool
    history: dict = field(default_factory=dict)
    tls: dict = field(default_factory=dict)
    http: dict = field(default_factory=dict)
    udp: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestraRatingsRenderPlan:
    stats_text: str
    history_text: str


def load_orchestra_ratings_state(runner) -> OrchestraRatingsState:
    if runner is None:
        return OrchestraRatingsState(no_runner=True)

    learned = runner.get_learned_data()
    return OrchestraRatingsState(
        no_runner=False,
        history=learned.get("history", {}) or {},
        tls=learned.get("tls", {}) or {},
        http=learned.get("http", {}) or {},
        udp=learned.get("udp", {}) or {},
    )


def build_orchestra_ratings_render_plan(
    *,
    state: OrchestraRatingsState,
    filter_text: str,
    tr_fn: Callable[..., str],
) -> OrchestraRatingsRenderPlan:
    if state.no_runner:
        return OrchestraRatingsRenderPlan(
            stats_text=tr_fn(
                "page.orchestra.ratings.status.not_initialized",
                "Оркестратор не инициализирован",
            ),
            history_text="",
        )

    history_data = state.history
    if not history_data:
        return OrchestraRatingsRenderPlan(
            stats_text=tr_fn("page.orchestra.ratings.status.no_history", "Нет данных истории"),
            history_text="",
        )

    prepared_filter = str(filter_text or "").strip().lower()
    lines: list[str] = []
    total_strategies = 0
    shown_domains = 0

    sorted_domains = sorted(
        history_data.keys(),
        key=lambda domain: len(history_data[domain]),
        reverse=True,
    )

    for domain in sorted_domains:
        if prepared_filter and prepared_filter not in domain.lower():
            continue

        strategies = history_data[domain]
        if not strategies:
            continue

        shown_domains += 1
        status = _domain_status_label(domain=domain, state=state, tr_fn=tr_fn)
        sorted_strategies = sorted(
            strategies.items(),
            key=lambda item: item[1]["rate"],
            reverse=True,
        )

        lines.append(f"═══ {domain}{status} ═══")
        for strat_num, history_entry in sorted_strategies:
            successes = history_entry["successes"]
            failures = history_entry["failures"]
            rate = history_entry["rate"]
            indicator, bar = _rating_indicator(int(rate))
            lines.append(f"  {indicator} #{strat_num:3d}: {bar} {rate:3d}% ({successes}✓/{failures}✗)")
            total_strategies += 1
        lines.append("")

    total_domains = len(history_data)
    if prepared_filter:
        stats_text = tr_fn(
            "page.orchestra.ratings.stats.filtered",
            "Показано: {shown} из {total} доменов, {records} записей",
            shown=shown_domains,
            total=total_domains,
            records=total_strategies,
        )
    else:
        stats_text = tr_fn(
            "page.orchestra.ratings.stats.total",
            "Всего: {total} доменов, {records} записей",
            total=total_domains,
            records=total_strategies,
        )

    return OrchestraRatingsRenderPlan(
        stats_text=stats_text,
        history_text="\n".join(lines),
    )


def _domain_status_label(*, domain: str, state: OrchestraRatingsState, tr_fn: Callable[..., str]) -> str:
    if domain in state.tls:
        return tr_fn("page.orchestra.ratings.status.lock.tls", " [TLS LOCK]")
    if domain in state.http:
        return tr_fn("page.orchestra.ratings.status.lock.http", " [HTTP LOCK]")
    if domain in state.udp:
        return tr_fn("page.orchestra.ratings.status.lock.udp", " [UDP LOCK]")
    return ""


def _rating_indicator(rate: int) -> tuple[str, str]:
    if rate >= 80:
        return "🟢", "████████░░"
    if rate >= 60:
        return "🟡", "██████░░░░"
    if rate >= 40:
        return "🟠", "████░░░░░░"
    return "🔴", "██░░░░░░░░"
