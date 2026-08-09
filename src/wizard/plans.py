"""Чистая логика мастера первого запуска.

Без Qt и без обращений к системе — только преобразование ответов
пользователя в настройки и в запрос для оркестратора «одной кнопки».

Принцип отбора вопросов: спрашиваем лишь то, что человек про себя знает.
Каким сервисом он пользуется — знает. Какая у провайдера техника DPI и
какой пресет ей подходит — не знает и знать не должен, это определяется
автоматически через blockcheck.
"""

from __future__ import annotations

from dataclasses import dataclass

from oneclick.plans import OneClickRequest


@dataclass(frozen=True, slots=True)
class ServiceChoice:
    """Категория на первом экране мастера.

    Пользователь выбирает не механизм, а то, чем пользуется. Каким
    способом это открыть — обходом DPI, прокси или правкой hosts —
    решает приложение.
    """

    key: str
    title: str
    #: Примеры под заголовком, мелким шрифтом.
    description: str
    default_enabled: bool = False
    #: Домен для автоподбора стратегии и последующей самопроверки.
    probe_url: str = ""
    #: Нужен ли локальный прокси для Telegram.
    needs_telegram_proxy: bool = False
    #: Нужна ли правка hosts.
    needs_hosts: bool = False
    #: Имена сервисов в json/hosts_catalog, ровно как в каталоге.
    hosts_services: tuple[str, ...] = ()


#: Категории, а не отдельные сервисы: список приложений у людей разный,
#: а способов обхода всего три. Заголовок — категория, под ним примеры.
#:
#: Разделение по механизму намеренно скрыто. Соцсети и видео блокирует
#: РКН — их открывает обход DPI. Нейросети и рабочие сервисы наоборот
#: сами закрывают доступ из России, DPI там бесполезен, нужен hosts с
#: адресами из json/hosts_catalog.
SERVICE_CHOICES: tuple[ServiceChoice, ...] = (
    ServiceChoice(
        key="video",
        title="Видео и стримы",
        description="YouTube, Twitch, Rutube",
        default_enabled=True,
        probe_url="https://www.youtube.com",
        hosts_services=("Twitch",),
    ),
    ServiceChoice(
        key="messengers",
        title="Мессенджеры",
        description="Telegram, WhatsApp, Discord",
        default_enabled=True,
        probe_url="https://discord.com",
        needs_telegram_proxy=True,
        needs_hosts=True,
        hosts_services=("Telegram (работает только веб-версия)",),
    ),
    ServiceChoice(
        key="social",
        title="Соцсети",
        description="Instagram, Facebook, X, TikTok",
        default_enabled=True,
        probe_url="https://www.instagram.com",
        hosts_services=("TikTok",),
    ),
    ServiceChoice(
        key="ai",
        title="Нейросети",
        description="ChatGPT, Claude, Gemini, Copilot",
        default_enabled=True,
        needs_hosts=True,
        hosts_services=(
            "ChatGPT & Sora (OpenAI)",
            "Claude",
            "Gemini AI",
            "Microsoft (Copilot, Designer, Xbox)",
            "GitHub Copilot",
        ),
    ),
    ServiceChoice(
        key="work",
        title="Рабочие сервисы",
        description="Notion, Canva, DeepL, JetBrains, TeamViewer",
        needs_hosts=True,
        hosts_services=("Notion", "Canva", "DeepL", "JetBrains", "TeamViewer"),
    ),
    ServiceChoice(
        key="music",
        title="Музыка",
        description="Spotify",
        needs_hosts=True,
        hosts_services=("Spotify",),
    ),
    ServiceChoice(
        key="anime",
        title="Аниме и манга",
        description="Shikimori, MangaLib, AniList, MyAnimeList",
        hosts_services=("MangaLib",),
    ),
    ServiceChoice(
        key="media",
        title="Фильмы и сериалы",
        description="Кинопоиск, Rutracker, торрент-трекеры",
        probe_url="https://rutracker.org",
    ),
    ServiceChoice(
        key="dev",
        title="Разработка",
        description="GitHub, GitLab, Docker Hub, Stack Overflow",
        hosts_services=("GitHub", "GitHub Copilot"),
    ),
    ServiceChoice(
        key="games",
        title="Игры",
        description="Steam, Epic Games, игровые голосовые чаты",
    ),
    ServiceChoice(
        key="adobe",
        title="Программы Adobe",
        description="Проверка лицензий Photoshop, Illustrator и других",
        needs_hosts=True,
    ),
)

_CHOICE_BY_KEY = {choice.key: choice for choice in SERVICE_CHOICES}

#: Проверяем хотя бы один общедоступный адрес, даже если пользователь
#: не отметил ничего: иначе диагностике не с чем работать.
_FALLBACK_PROBE_URL = "https://www.youtube.com"


def default_selection() -> frozenset[str]:
    """Все категории сразу.

    Вопрос «чем вы пользуетесь?» из мастера убран: сервисы hosts всё
    равно включаются целиком при первом запуске, и выбор ни на что не
    влиял бы. Полный набор нужен, чтобы вместе со всем поднимался и
    Telegram-прокси — он привязан к категории мессенджеров.
    """
    return frozenset(c.key for c in SERVICE_CHOICES)


#: Ключи прежней версии мастера, где пунктами были отдельные сервисы.
#: Без переноса у тех, кто уже прошёл мастер, выбор молча обнулился бы:
#: мастер второй раз не открывается, а незнакомые ключи отбрасываются.
_LEGACY_KEYS: dict[str, str] = {
    "youtube": "video",
    "discord": "messengers",
    "telegram": "messengers",
    "chatgpt": "ai",
    "claude": "ai",
    "gemini": "ai",
    "copilot": "ai",
    "notion": "work",
    "spotify": "music",
}


def normalize_selection(keys) -> frozenset[str]:
    """Приводит выбор к текущим ключам, отбрасывая неизвестные."""
    out: set[str] = set()
    for raw in keys or ():
        key = str(raw)
        key = _LEGACY_KEYS.get(key, key)
        if key in _CHOICE_BY_KEY:
            out.add(key)
    return frozenset(out)


def build_probe_urls(selection) -> tuple[str, ...]:
    """Адреса для автоподбора стратегии и самопроверки."""
    selected = normalize_selection(selection)
    urls = [
        _CHOICE_BY_KEY[key].probe_url
        for key in sorted(selected)
        if _CHOICE_BY_KEY[key].probe_url
    ]
    return tuple(urls) if urls else (_FALLBACK_PROBE_URL,)


def _catalog_rows(catalog_service: str) -> list[tuple[str, str]]:
    """Пары «домен — адрес» для сервиса из json/hosts_catalog.

    Профиль спрашиваем у самого каталога, а не берём первый из общего
    списка. Сервисы бывают двух видов: одни подменяют адрес через
    публичный DNS, другие прописываются в hosts напрямую — и у вторых
    записей под профилем вроде xbox_dns попросту нет.
    """
    try:
        from hosts.proxy_domains import (
            get_service_available_dns_profiles,
            get_service_domain_ip_rows,
        )

        profiles = get_service_available_dns_profiles(catalog_service) or []
        if not profiles:
            return []
        return list(get_service_domain_ip_rows(catalog_service, profiles[0]) or [])
    except Exception:
        return []


#: Профиль DNS, который ставим по умолчанию. Пользователь просил
#: приоритет именно на него; если сервис его не поддерживает, берём
#: первый доступный из каталога.
PREFERRED_DNS_PROFILE = "xbox_dns"


def build_hosts_service_profiles(selection) -> dict[str, str]:
    """Отображение «сервис каталога -> профиль» для страницы hosts.

    Именно в таком виде выбор хранится и отображается на странице
    «Редактор hosts»: переключатели и колонка «Профиль» читают его.
    Если писать в hosts только готовые пары «домен -> адрес», записи
    появятся, а переключатели останутся выключенными — человек решит,
    что мастер ничего не сделал.
    """
    try:
        from hosts.proxy_domains import get_service_available_dns_profiles
    except Exception:
        return {}

    out: dict[str, str] = {}
    for key in sorted(normalize_selection(selection)):
        for service in _CHOICE_BY_KEY[key].hosts_services:
            try:
                available = list(get_service_available_dns_profiles(service) or [])
            except Exception:
                available = []
            if not available:
                continue
            out[service] = (
                PREFERRED_DNS_PROFILE if PREFERRED_DNS_PROFILE in available else available[0]
            )
    return out


def build_hosts_entries(selection) -> dict[str, str]:
    """Записи hosts под выбранные категории.

    Домены Adobe зашиты в исходниках и доступны без каталога, остальное
    приходит из json/hosts_catalog, который лежит рядом с движком.
    """
    selected = normalize_selection(selection)
    entries: dict[str, str] = {}

    if "adobe" in selected:
        try:
            from hosts.adobe_domains import ADOBE_DOMAINS

            entries.update(ADOBE_DOMAINS)
        except Exception:
            pass

    for key in sorted(selected):
        for catalog_service in _CHOICE_BY_KEY[key].hosts_services:
            for host, ip in _catalog_rows(catalog_service):
                host = str(host or "").strip()
                ip = str(ip or "").strip()
                if host and ip:
                    entries[host] = ip

    return entries


def build_oneclick_request(
    selection,
    *,
    allow_dns_fix: bool = True,
    run_selfcheck: bool = True,
) -> OneClickRequest:
    """Собирает запрос для оркестратора из ответов мастера."""
    selected = normalize_selection(selection)
    return OneClickRequest(
        services=selected,
        hosts_entries=build_hosts_entries(selected),
        allow_dns_fix=allow_dns_fix,
        run_selfcheck=run_selfcheck,
        needs_telegram_proxy=any(
            _CHOICE_BY_KEY[key].needs_telegram_proxy for key in selected
        ),
    )


@dataclass(frozen=True, slots=True)
class WizardSettingsPlan:
    """Что записать в настройки по итогам мастера."""

    gui_autostart_enabled: bool
    dpi_autostart: bool
    tray_close_mode: str
    #: light / dark / system. По умолчанию system — приложение
    #: подстраивается под Windows и не спорит с настройками человека.
    display_mode: str = "system"


#: Значения из settings.schema.VALID_TRAY_CLOSE_MODES.
TRAY_MODE_MINIMIZE = "minimize_and_close"
TRAY_MODE_NORMAL = "normal"


def build_settings_plan(
    *,
    autostart_with_windows: bool,
    minimize_to_tray: bool,
    display_mode: str = "system",
) -> WizardSettingsPlan:
    """Два тумблера третьего экрана превращаются в три настройки.

    Автозапуск включает и запуск приложения с Windows, и автоматический
    старт защиты: включать программу, которая ничего не делает до нажатия
    кнопки, смысла нет.
    """
    return WizardSettingsPlan(
        gui_autostart_enabled=bool(autostart_with_windows),
        dpi_autostart=bool(autostart_with_windows),
        tray_close_mode=TRAY_MODE_MINIMIZE if minimize_to_tray else TRAY_MODE_NORMAL,
        display_mode=normalize_display_mode(display_mode),
    )


#: Допустимые темы. Совпадает с settings.store.set_display_mode.
#: Подписи начинаются со слова «Всегда» не для красоты. Прежние темы
#: приложения назывались односложно, и в проекте стоит проверка,
#: запрещающая тем названиям возвращаться в исходники — включая
#: комментарии. Ослаблять её ради подписи неправильно: она ловит
#: настоящие откаты к старым названиям.
DISPLAY_MODES: tuple[tuple[str, str], ...] = (
    ("system", "Как в Windows"),
    ("light", "Всегда светлое"),
    ("dark", "Всегда тёмное"),
)


def normalize_display_mode(value) -> str:
    """Неизвестное значение приводим к «как в Windows»."""
    mode = str(value or "").strip().lower()
    return mode if mode in {key for key, _title in DISPLAY_MODES} else "system"


@dataclass(frozen=True, slots=True)
class WizardStep:
    key: str
    title: str
    subtitle: str


#: Экран «Чем вы пользуетесь?» убран: обходы включаются все сразу,
#: и отвечать на вопрос было незачем — результат не менялся.
#:
#: А вот провайдер на результат влияет: оборудование фильтрации у них
#: разное, и стратегия, работающая на одном, на другом может не дать
#: ничего. Ответ выбирает пресет, с которого начать; что подойдёт на
#: самом деле, показывает следующий экран с проверкой.
WIZARD_STEPS: tuple[WizardStep, ...] = (
    WizardStep(
        key="provider",
        title="Какой у вас провайдер?",
        subtitle="От него зависит, какие настройки обхода взять за основу",
    ),
    WizardStep(
        key="detect",
        title="Подбираем настройки",
        subtitle="Проверяем, как провайдер ограничивает доступ",
    ),
    WizardStep(
        key="startup",
        title="Запуск",
        subtitle="Как приложение должно вести себя дальше",
    ),
)


def next_step_index(current: int, *, total: int | None = None) -> int:
    total = len(WIZARD_STEPS) if total is None else int(total)
    return max(0, min(int(current) + 1, total - 1))


def prev_step_index(current: int) -> int:
    return max(0, int(current) - 1)


def wizard_progress_percent(
    current: int,
    *,
    total: int | None = None,
    checked: int = 0,
    to_check: int = 0,
) -> int:
    """Насколько пройдена первичная настройка, в процентах.

    Считаем от шагов, а не от времени: время проверки зависит от сети и
    предсказать его нельзя, а шаги известны заранее. Внутри шага
    проверки доля уточняется по числу опрошенных доменов — иначе
    надпись замирает на самом долгом месте и выглядит зависшей.

    Сотню отдаём только на последнем шаге при выполненной работе:
    «100%» на экране, где ещё нажимать «Готово», — это обман.
    """
    steps = len(WIZARD_STEPS) if total is None else int(total)
    if steps <= 0:
        return 0

    step = max(0, min(int(current), steps - 1))
    inner = 0.0
    if to_check > 0:
        inner = max(0.0, min(1.0, float(checked) / float(to_check)))

    done = (step + inner) / float(steps)
    return int(max(0, min(99, round(done * 100))))


def is_last_step(current: int, *, total: int | None = None) -> bool:
    total = len(WIZARD_STEPS) if total is None else int(total)
    return int(current) >= total - 1


__all__ = [
    "SERVICE_CHOICES",
    "TRAY_MODE_MINIMIZE",
    "TRAY_MODE_NORMAL",
    "WIZARD_STEPS",
    "ServiceChoice",
    "WizardSettingsPlan",
    "WizardStep",
    "build_hosts_entries",
    "build_oneclick_request",
    "build_probe_urls",
    "build_settings_plan",
    "default_selection",
    "is_last_step",
    "next_step_index",
    "normalize_selection",
    "prev_step_index",
    "wizard_progress_percent",
]
