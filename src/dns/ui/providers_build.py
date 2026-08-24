"""Сборка списка DNS-провайдеров для страницы Network."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProviderCardsBuildResult:
    dns_cards: dict[str, object]
    category_labels: list[object]


def build_provider_cards(
    *,
    providers_by_category: dict,
    caption_label_cls,
    dns_provider_card_cls,
    dns_cards_layout,
    show_ipv6: bool,
    on_selected,
    show_doh: bool = True,
) -> ProviderCardsBuildResult:
    dns_cards: dict[str, object] = {}
    category_labels: list[object] = []

    if hasattr(dns_cards_layout, "add_provider"):
        try:
            dns_cards_layout.provider_selected.connect(on_selected)
        except Exception:
            pass
        for category, providers in providers_by_category.items():
            try:
                dns_cards_layout.add_section(category)
            except Exception:
                pass
            for name, data in providers.items():
                dns_cards[name] = dns_cards_layout.add_provider(
                    name,
                    data,
                    show_ipv6=show_ipv6,
                    show_doh=show_doh,
                )
        return ProviderCardsBuildResult(
            dns_cards=dns_cards,
            category_labels=[],
        )

    for category, providers in providers_by_category.items():
        category_label = caption_label_cls(category)
        dns_cards_layout.addWidget(category_label)

        for name, data in providers.items():
            card = dns_provider_card_cls(name, data, False, show_ipv6=show_ipv6, show_doh=show_doh)
            card.selected.connect(on_selected)
            dns_cards[name] = card
            dns_cards_layout.addWidget(card)

    return ProviderCardsBuildResult(
        dns_cards=dns_cards,
        category_labels=category_labels,
    )
