"""Шаги обучающего тура: что подсвечиваем, на какой странице и какой текст.

Каждый шаг умеет сам найти свою цель в живом окне. Если цели нет
(другой режим программы, пункт меню скрыт или ещё не построен), шаг
тихо пропускается. Так один список шагов подходит и простому виду
(там нет боковой панели и расширенных страниц), и расширенному.

Цель — это виджет или пара (виджет, прямоугольник внутри него). Пара
нужна для строк списков: строки профилей и пресетов рисует делегат,
отдельных виджетов у них нет.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from PyQt6 import sip
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QWidget

from app.page_names import PageName
from config.urls import ONBOARDING_WIKI_URLS
from configsets import CONFIGS_READY
from ui.window_ui_session import get_window_ui_session


CONTROL_PAGE_NAMES: tuple[PageName, ...] = (PageName.ZAPRET2_MODE_CONTROL,)

# Страницы тура для каждого режима: ключ шага → страница программы.
MODE_TOUR_PAGES: dict[PageName, dict[str, PageName]] = {
    PageName.ZAPRET2_MODE_CONTROL: {
        "control": PageName.ZAPRET2_MODE_CONTROL,
        "user_presets": PageName.ZAPRET2_USER_PRESETS,
        "preset_editor": PageName.ZAPRET2_PRESET_RAW_EDITOR,
        "preset_setup": PageName.ZAPRET2_PRESET_SETUP,
        "profile_order": PageName.ZAPRET2_PROFILE_ORDER,
        "profile_setup": PageName.ZAPRET2_PROFILE_SETUP,
        # Остальные пункты меню: тур открывает каждый, чтобы показать его вкладку.
        "network": PageName.NETWORK,
        "hosts": PageName.HOSTS,
        "telegram_proxy": PageName.TELEGRAM_PROXY,
        "vpn": PageName.VPN,
        "blockcheck": PageName.BLOCKCHECK,
        "log_analyzer": PageName.WINWS_LOG_ANALYZER,
        "logs": PageName.LOGS,
        "configs": PageName.CONFIGS,
    },
}

# Страницы, которым нужен параметр (какой пресет, какой профиль). Их
# открывает страница-родитель своим обычным путём через
# onboarding_open_subpage(ключ): сама выбирает пресет или профиль.
TOUR_SUBPAGE_PARENTS: dict[str, str] = {
    "preset_editor": "user_presets",
    "profile_setup": "preset_setup",
}

TourTarget = QWidget | tuple[QWidget, QRect]


@dataclass(slots=True)
class TourContext:
    window: QWidget
    control_page_name: PageName | None = None
    # Ключ страницы тура → PageName текущего режима.
    pages: dict[str, PageName] = field(default_factory=dict)
    # Страница, открытая текущим шагом.
    current_page: QWidget | None = None
    current_page_key: str = ""
    # Расширенный вид. В простом виде боковой панели нет, а страницы
    # пресетов и профилей не открываются — их шаги тур пропускает.
    advanced: bool = True
    # Первый запуск: тур заодно задаёт вопросы бывшего мастера. См.
    # ui/onboarding/setup_choices.py.
    setup: bool = False
    # Необязательные ветки, которые человек открыл кнопкой на карточке
    # (например, подробный разбор пресета).
    branches: set[str] = field(default_factory=set)
    # Выбор пресета через фасад пресетов — для ответа о провайдере.
    # Передаётся со стартом тура: окно не держит фич (architecture_checks).
    select_preset: Callable[[str], object] | None = None


TargetResolver = Callable[[TourContext], list[TourTarget]]


@dataclass(frozen=True, slots=True)
class TourStep:
    key: str
    target: TargetResolver | None = None
    # Какую страницу тура открыть перед шагом ("control", "user_presets",
    # "preset_setup"). None — остаться там, где пользователь сейчас.
    page: str | None = None
    # Цель может появиться не сразу (список профилей грузится в фоне):
    # шаг показывается по центру и ждёт её, а не пропускается.
    target_optional: bool = False
    # Крупная карточка по центру: приветствие и объяснения без подсветки.
    hero: bool = False
    # Что страница показывает вживую на время шага: открытое меню, нужную
    # вкладку. Тур передаёт его в page.onboarding_set_state(), а при уходе
    # с шага — None, и страница возвращает всё как было.
    page_state: str | None = None
    # Статья вики по теме шага — кнопка «Подробнее в вики» на карточке.
    wiki_url: str = ""
    # Анимированная схема на карточке (ключ сцены из ui.onboarding.illustrations).
    illustration: str = ""
    # Живые значения для текста: страница отдаёт их через
    # onboarding_text_values(text_key), тур подставляет в {…} текста.
    text_key: str = ""
    # Шаг только для расширенного вида: пресеты, профили, стратегии. В
    # простом виде их не видно, и рассказ о них сбивал бы с толку.
    advanced_only: bool = False
    # Действие на карточке шага. «enable_advanced» — кнопка «Включить
    # расширенные настройки»: без неё простой вид обрывал тур на полпути,
    # и человек так и не узнавал, что за кнопкой в заголовке целая программа.
    action: str = ""
    # Вопрос первичной настройки на карточке (ключ из setup_choices).
    # Показывается только на первом запуске, в обычном туре шаг просто
    # рассказывает о разделе.
    choice: str = ""
    # Необязательная ветка: шаг показывается, только если человек сам
    # попросил подробностей. Разбор файла пресета по строкам и восемь
    # техник обхода растягивали тур до полусотни шагов, и руководитель,
    # которому нужна одна кнопка, бросал его на десятом.
    branch: str = ""


def is_alive_widget(widget) -> bool:
    return widget is not None and not sip.isdeleted(widget)


def is_widget_shown(widget) -> bool:
    if not is_alive_widget(widget):
        return False
    try:
        return bool(widget.isVisible()) and widget.width() > 0 and widget.height() > 0
    except RuntimeError:
        return False


def target_widget(target) -> QWidget | None:
    if isinstance(target, tuple):
        return target[0] if target else None
    return target


def is_target_shown(target) -> bool:
    if isinstance(target, tuple):
        if len(target) != 2 or not is_widget_shown(target[0]):
            return False
        rect = target[1]
        return isinstance(rect, QRect) and rect.isValid() and not rect.isEmpty()
    return is_widget_shown(target)


def resolve_control_page_name(window) -> PageName | None:
    """Главная страница текущего режима — та, чей пункт виден в меню."""
    session = get_window_ui_session(window)
    if session is None:
        return None
    for page_name in CONTROL_PAGE_NAMES:
        if is_widget_shown(session.nav_items.get(page_name)):
            return page_name
    # В простом виде боковая панель скрыта целиком, и пункта не видно ни
    # одного. Главная страница при этом есть — у net67 она одна.
    return PageName.ZAPRET2_MODE_CONTROL


def _advanced_view_enabled() -> bool:
    try:
        from ui.navigation.schema import is_advanced_mode_enabled

        return bool(is_advanced_mode_enabled())
    except Exception:
        return True


def build_tour_context(window) -> TourContext:
    control_page_name = resolve_control_page_name(window)
    pages = dict(MODE_TOUR_PAGES.get(control_page_name, {})) if control_page_name is not None else {}
    advanced = _advanced_view_enabled()
    if not advanced:
        # Простой вид — только главная: открыть из тура страницу пресетов
        # значило бы вывести человека туда, куда он сам попасть не может.
        pages = {key: value for key, value in pages.items() if key == "control"}
    return TourContext(window=window, control_page_name=control_page_name, pages=pages, advanced=advanced)


def _nav_item(*page_names: PageName) -> TargetResolver:
    def _resolve(ctx: TourContext) -> list[TourTarget]:
        session = get_window_ui_session(ctx.window)
        if session is None:
            return []
        for page_name in page_names:
            item = session.nav_items.get(page_name)
            if is_widget_shown(item):
                return [item]
        return []

    return _resolve


def _window_attr(name: str) -> TargetResolver:
    """Виджет самого окна — например, переключатель вида в заголовке."""

    def _resolve(ctx: TourContext) -> list[TourTarget]:
        widget = getattr(ctx.window, name, None)
        return [widget] if is_widget_shown(widget) else []

    return _resolve


def _group_tab(group: str) -> TargetResolver:
    """Вкладка раздела в заголовке окна: «Обход», «Пресеты», «Инструменты», «Диагностика»."""

    def _resolve(ctx: TourContext) -> list[TourTarget]:
        tabs = getattr(ctx.window, "groupTabs", None)
        if not is_alive_widget(tabs):
            return []
        tab = tabs.tabs.get(group)
        return [tab] if is_widget_shown(tab) else []

    return _resolve


def _page_tab(page_name: PageName) -> TargetResolver:
    """Вкладка страницы во второй строке меню.

    Боковая панель убрана с экрана, и её пункты скрыты: шаги, которые
    целились в них, молча пропускались — тур не рассказывал ни про hosts,
    ни про DNS, ни про диагностику. Меню теперь — вкладки.
    """

    def _resolve(ctx: TourContext) -> list[TourTarget]:
        tabs = getattr(ctx.window, "pageTabs", None)
        if not is_alive_widget(tabs):
            return []
        try:
            from ui.navigation.schema import get_page_route_key

            tab = tabs.tabs.get(get_page_route_key(page_name))
        except Exception:
            return []
        return [tab] if is_widget_shown(tab) else []

    return _resolve


def _nav_items(*page_names: PageName) -> TargetResolver:
    """Несколько пунктов бокового меню сразу — все, что видны."""

    def _resolve(ctx: TourContext) -> list[TourTarget]:
        session = get_window_ui_session(ctx.window)
        if session is None:
            return []
        items = [session.nav_items.get(page_name) for page_name in page_names]
        return [item for item in items if is_widget_shown(item)]

    return _resolve


def _nav_group(group_name: str) -> TargetResolver:
    """Заголовок группы бокового меню вместе со всеми её видимыми пунктами."""

    def _resolve(ctx: TourContext) -> list[TourTarget]:
        session = get_window_ui_session(ctx.window)
        if session is None:
            return []
        header = session.nav_header_by_group.get(group_name)
        widgets: list[TourTarget] = []
        if is_widget_shown(header):
            widgets.append(header)
        for entry_header, page_names, _header_key in session.nav_headers:
            if entry_header is not header:
                continue
            for page_name in page_names:
                item = session.nav_items.get(page_name)
                if is_widget_shown(item):
                    widgets.append(item)
        # Один заголовок без пунктов подсвечивать бессмысленно.
        return widgets if len(widgets) > 1 else []

    return _resolve


def _page_target(name: str) -> TargetResolver:
    def _resolve(ctx: TourContext) -> list[TourTarget]:
        page = ctx.current_page
        if not is_alive_widget(page):
            return []
        getter = getattr(page, "onboarding_target", None)
        if not callable(getter):
            return []
        target = getter(name)
        # Список — несколько виджетов, подсвечиваем их вместе.
        targets = target if isinstance(target, list) else [target]
        return [item for item in targets if is_target_shown(item)]

    return _resolve


def _preset_section(section: str) -> TourStep:
    """Шаг разбора пресета: подсветить часть в редакторе и рассказать о ней."""
    target = f"section:{section}"
    return TourStep(
        f"preset_{section}",
        _page_target(target),
        page="preset_editor",
        page_state=target,
        text_key=target,
    )


#: Ветка «Разобрать пресет подробно». Её же проверяет overlay: кто её
#: прошёл, тот уже видел все схемы техник обхода.
PRESETS_BRANCH = "presets"
_PRESETS = PRESETS_BRANCH

_TOUR_STEPS: tuple[TourStep, ...] = (
    # ── для всех ─────────────────────────────────────────────────────
    # Шагов «статус» и «кнопка запуска» нет: в net67 их карточки скрыты —
    # всё делает «одна кнопка». Шаг без цели не показывался, но считался
    # в «Шаг N из M», и счётчик врал на три шага. «О программе» нет в
    # меню вовсе — по той же причине нет и шага.
    TourStep("welcome", hero=True),
    TourStep("how_it_works", hero=True),
    TourStep("oneclick", _page_target("oneclick"), page="control"),
    TourStep("services", hero=True),
    TourStep("program_settings", _page_target("program_settings"), page="control", choice="startup"),
    TourStep("bell", _window_attr("notificationBell")),
    TourStep("view_switch", _window_attr("advancedButton"), action="enable_advanced"),
    # ── расширенный вид: раздел «Обход» ──────────────────────────────
    TourStep("building_blocks", hero=True, advanced_only=True),
    TourStep("menu_root", _group_tab("root"), page="control", advanced_only=True),
    TourStep("preset", _page_target("preset"), page="control", advanced_only=True),
    # ── «Пресеты» ────────────────────────────────────────────────────
    TourStep("menu_presets", _group_tab("settings"), page="user_presets", advanced_only=True, choice="provider"),
    TourStep("presets_list", _page_target("presets_list"), page="user_presets", target_optional=True, action="branch:presets"),
    TourStep("preset_menu", _page_target("preset_menu"), page="user_presets", page_state="preset_menu", branch=_PRESETS),
    TourStep("preset_file", _page_target("editor"), page="preset_editor", target_optional=True, branch=_PRESETS),
    *(
        replace(_preset_section(section), branch=_PRESETS)
        for section in (
            "header",
            "lua_init",
            "engine_options",
            "interception",
            "blobs",
            "profile",
            "profile_name",
            "profile_match",
            "profile_packets",
            "profile_strategy",
            "profile_new",
        )
    ),
    TourStep("presets_toolbar", _page_target("presets_toolbar"), page="user_presets", branch=_PRESETS),
    TourStep("profiles_list", _page_target("profiles_list"), page="preset_setup", target_optional=True),
    TourStep("profile_row", _page_target("first_profile"), page="preset_setup", branch=_PRESETS),
    TourStep("profile_menu", _page_target("profile_menu"), page="preset_setup", page_state="profile_menu", branch=_PRESETS),
    TourStep("profiles_toolbar", _page_target("profiles_toolbar"), page="preset_setup", branch=_PRESETS),
    TourStep("profile_order", _page_target("order_list"), page="profile_order", target_optional=True, branch=_PRESETS),
    TourStep("list_type", _page_target("list_type"), page="profile_setup", target_optional=True, branch=_PRESETS),
    TourStep("ranges", _page_target("ranges"), page="profile_setup", branch=_PRESETS),
    TourStep("profile_tabs", _page_target("tabs"), page="profile_setup", branch=_PRESETS),
    TourStep("strategy_choice", _page_target("strategies"), page="profile_setup", illustration="blocked", branch=_PRESETS),
    *(
        TourStep(f"technique_{name}", page="profile_setup", illustration=name, branch=_PRESETS)
        for name in ("fake", "multisplit", "multidisorder", "fakedsplit", "hostfakesplit", "tcpseg", "oob", "syndata")
    ),
    TourStep("list_entries", _page_target("list_entries"), page="profile_setup", page_state="editor", branch=_PRESETS),
    # ── «Инструменты» ────────────────────────────────────────────────
    TourStep("menu_tools", _group_tab("system"), page="network", advanced_only=True),
    TourStep("dns", _page_tab(PageName.NETWORK), page="network"),
    TourStep("hosts", _page_tab(PageName.HOSTS), page="hosts", choice="hosts"),
    TourStep("telegram_proxy", _page_tab(PageName.TELEGRAM_PROXY), page="telegram_proxy"),
    TourStep("vpn", _page_tab(PageName.VPN), page="vpn"),
    # ── «Диагностика» ────────────────────────────────────────────────
    TourStep("menu_diagnostics", _group_tab("diagnostics"), page="blockcheck", advanced_only=True),
    TourStep("blockcheck", _page_tab(PageName.BLOCKCHECK), page="blockcheck", choice="detect"),
    TourStep("log_analyzer", _page_tab(PageName.WINWS_LOG_ANALYZER), page="log_analyzer"),
    TourStep("logs", _page_tab(PageName.LOGS), page="logs"),
    # Пока раздел в разработке, шага нет: тур описывал бы как рабочее то,
    # на чём страница сама пишет «не работает».
    *((TourStep("configs", _page_tab(PageName.CONFIGS), page="configs"),) if CONFIGS_READY else ()),
    TourStep("finish", _page_target("tour_card"), page="control", target_optional=True, action="bypass_tour"),
)

# Ссылки на вики живут в config.urls вместе с остальными адресами.
TOUR_STEPS: tuple[TourStep, ...] = tuple(
    replace(step, wiki_url=ONBOARDING_WIKI_URLS.get(step.key, "")) for step in _TOUR_STEPS
)


#: Экскурсия «Как работает обход» — отдельно от основного тура.
#:
#: Схемы техник жили только в подробной ветке основного тура, на
#: странице профиля, куда попадает не каждый. Здесь они собраны
#: подряд, без страниц и кнопок: как провайдер узнаёт сайт и какими
#: приёмами обход ему мешает. Тексты и схемы — те же ключи, что в
#: основном туре: две версии одного объяснения разошлись бы.
_BYPASS_TOUR_STEPS: tuple[TourStep, ...] = (
    TourStep("bypass_welcome", hero=True),
    TourStep("how_it_works", hero=True),
    TourStep("strategy_choice", illustration="blocked"),
    *(
        TourStep(f"technique_{name}", illustration=name)
        for name in ("fake", "multisplit", "multidisorder", "fakedsplit", "hostfakesplit", "tcpseg", "oob", "syndata")
    ),
    TourStep("bypass_practice", hero=True),
    TourStep("bypass_finish", hero=True),
)

BYPASS_TOUR_STEPS: tuple[TourStep, ...] = tuple(
    replace(step, wiki_url=ONBOARDING_WIKI_URLS.get(step.key, "")) for step in _BYPASS_TOUR_STEPS
)


__all__ = [
    "BYPASS_TOUR_STEPS",
    "PRESETS_BRANCH",
    "CONTROL_PAGE_NAMES",
    "MODE_TOUR_PAGES",
    "TOUR_STEPS",
    "TOUR_SUBPAGE_PARENTS",
    "TourContext",
    "TourStep",
    "TourTarget",
    "build_tour_context",
    "is_alive_widget",
    "is_target_shown",
    "is_widget_shown",
    "resolve_control_page_name",
    "target_widget",
]
