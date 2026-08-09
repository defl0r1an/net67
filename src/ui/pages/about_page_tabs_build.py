"""Build-helper shell вкладок для About page."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget
from qfluentwidgets import SegmentedWidget
from ui.accessibility import set_control_accessibility, set_state_text
from ui.segmented_accessibility import set_segmented_items_accessibility


_TAB_ACCESSIBLE_LABELS = {
    "about": "О программе",
    "help": "Справка",
}


def _join_labels(labels: list[str]) -> str:
    clean_labels = [str(label or "").strip() for label in labels if str(label or "").strip()]
    if not clean_labels:
        return ""
    if len(clean_labels) == 1:
        return clean_labels[0]
    return f"{', '.join(clean_labels[:-1])} или {clean_labels[-1]}"


def update_about_tabs_accessibility(tabs_pivot: SegmentedWidget, *, current: object | None = None) -> None:
    key = str(current or "").strip()
    if not key:
        try:
            key = str(tabs_pivot.currentRouteKey() or "").strip()
        except Exception:
            key = ""
    label = _TAB_ACCESSIBLE_LABELS.get(key) or _TAB_ACCESSIBLE_LABELS["about"]
    state = f"Вкладки страницы о программе, выбрано: {label}"
    description = f"Выберите раздел страницы о программе: {_join_labels(list(_TAB_ACCESSIBLE_LABELS.values()))}."
    set_state_text(tabs_pivot, state)
    set_control_accessibility(
        tabs_pivot,
        name=state,
        description=description,
    )
    set_segmented_items_accessibility(
        tabs_pivot,
        name="Вкладки страницы о программе",
        labels=_TAB_ACCESSIBLE_LABELS,
    )


@dataclass(slots=True)
class AboutPageTabsWidgets:
    tabs_pivot: SegmentedWidget
    stacked_widget: QStackedWidget
    about_tab: QWidget
    about_layout: QVBoxLayout
    help_tab: QWidget
    help_layout: QVBoxLayout
    kvn_tab: QWidget
    kvn_layout: QVBoxLayout


def _make_tab_widget() -> tuple[QWidget, QVBoxLayout]:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)
    return tab, layout


def build_about_page_tabs(*, tr_fn, on_switch_tab) -> AboutPageTabsWidgets:
    tabs_pivot = SegmentedWidget()
    tabs_pivot.addItem(
        routeKey="about",
        text=" " + tr_fn("page.about.tab.about", "О ПРОГРАММЕ"),
        onClick=lambda: on_switch_tab(0),
    )
    tabs_pivot.addItem(
        routeKey="help",
        text=" " + tr_fn("page.about.tab.help", "СПРАВКА"),
        onClick=lambda: on_switch_tab(1),
    )
    # Вкладка «net67 KVN» удалена: это был раздел о стороннем проекте
    # автора исходников. Виджет вкладки ниже всё же создаётся — на
    # kvn_tab/kvn_layout ещё ссылается about_page.py, — но в переключатель
    # и в стек не добавляется, поэтому в интерфейс не попадает.
    tabs_pivot.setCurrentItem("about")
    tabs_pivot.setItemFontSize(13)
    update_about_tabs_accessibility(tabs_pivot, current="about")
    tabs_pivot.currentItemChanged.connect(lambda current: update_about_tabs_accessibility(tabs_pivot, current=current))

    stacked_widget = QStackedWidget()

    about_tab, about_layout = _make_tab_widget()
    help_tab, help_layout = _make_tab_widget()
    kvn_tab, kvn_layout = _make_tab_widget()

    stacked_widget.addWidget(about_tab)
    stacked_widget.addWidget(help_tab)

    return AboutPageTabsWidgets(
        tabs_pivot=tabs_pivot,
        stacked_widget=stacked_widget,
        about_tab=about_tab,
        about_layout=about_layout,
        help_tab=help_tab,
        help_layout=help_layout,
        kvn_tab=kvn_tab,
        kvn_layout=kvn_layout,
    )
