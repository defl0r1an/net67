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

from log.log import log
from hosts.defaults import choose_profile
from oneclick.plans import OneClickRequest

#: Как называется профиль прямой записи в hosts. Совпадает с
#: hosts/defaults.py: два написания одного имени разошлись бы.
DIRECT_HOSTS_PROFILE = "hosts"


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
    #: Прописать сайты Telegram — блоком страницы Telegram Proxy.
    #:
    #: Раньше здесь стояло имя плитки Telegram из каталога. Плитку из
    #: редактора hosts убрали: у доменов Telegram должен быть один
    #: писатель, и это страница прокси.
    telegram_hosts: bool = False


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
        telegram_hosts=True,
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


@dataclass(frozen=True, slots=True)
class HostsGroup:
    """Галочка на экране «Что должно работать без VPN».

    Своих доменов не держит и по возможности не держит даже имён: список
    сервисов разрешается против живого каталога при каждом обращении.
    Захардкоженный список — это второй каталог, который расходится с
    первым молча. Так уже вышло: в мастере стояло пять нейросетей, а в
    каталоге их десять, и Grok с Windsurf в hosts не попадали никогда.
    """

    key: str
    title: str
    #: Примеры под заголовком, мелким шрифтом.
    examples: str
    default_enabled: bool = False
    #: Явные имена сервисов каталога — для групп, которых каталог не знает.
    services: tuple[str, ...] = ()
    #: Брать раздел «ИИ» целиком, той же функцией, что рисует страницу.
    from_ai_section: bool = False
    #: Забирать всё, что не досталось другим группам.
    takes_the_rest: bool = False
    #: Домены зашиты в исходниках, каталог для группы не нужен.
    source_domains: bool = False
    #: Сайты Telegram — блоком страницы Telegram Proxy, а не плиткой
    #: каталога. См. ``ServiceChoice.telegram_hosts``.
    telegram_hosts: bool = False


#: Общая приписка под всеми галочками.
#:
#: Одна на экран, а не по строке у каждой рискованной категории.
#: Повторённая дважды, она читается как ругань на конкретный пункт и
#: пугает сильнее, чем следует; сказанная один раз внизу — это условие
#: сделки, одинаковое для всего списка.
HOSTS_CAUTION_NOTE = (
    "Со временем что-то из выбранного может перестать открываться: "
    "адреса сервисов меняются, а записанные в hosts — нет. Мы следим "
    "за списками и обновляем их с новыми версиями программы."
)

#: Галочки экрана «Что должно работать без VPN».
#:
#: Шесть на весь каталог из семи десятков сервисов. Последняя группа
#: забирает остаток, поэтому потерять сервис нельзя: добавили новый в
#: каталог — он сразу попал в «Остальное», а не исчез из мастера.
HOSTS_GROUPS: tuple[HostsGroup, ...] = (
    HostsGroup(
        key="ai",
        title="Нейросети",
        examples="ChatGPT, Claude, Gemini, Grok, Copilot и остальные",
        default_enabled=True,
        from_ai_section=True,
    ),
    HostsGroup(
        key="social",
        title="Соцсети и мессенджеры",
        examples="Instagram, Telegram, Discord, WhatsApp, X, TikTok",
        default_enabled=True,
        telegram_hosts=True,
        services=(
            "Instagram",
            "WhatsApp (работает обход если есть IPv6)",
            "Discord",
            "Решение от Flowseal для стабильной работы голосовых серверов в Discord",
            "x.com / Twitter",
            "TikTok",
            "Badoo",
            "Guilded",
            "Truth Social",
            "Tuta",
            "Patreon",
        ),
    ),
    HostsGroup(
        key="work",
        title="Работа и разработка",
        examples="JetBrains, GitHub, Notion, Canva, DeepL, TeamViewer, Autodesk",
        services=(
            "JetBrains",
            "GitHub",
            "Notion",
            "Canva",
            "DeepL",
            "TeamViewer",
            "Linear.app",
            "Tableau",
            "Autodesk",
            "SketchUp",
            "Oracle",
            "Broadcom",
            "WorkOS",
            "Posthog",
            "Make",
            "Framer",
            "Parsec",
            "Tailscale",
            "Dell",
            "Intel",
            "AMD",
            "Nvidia",
            "Xerox",
            "Elgato",
            "Dyson",
            "Fitbit",
            "Naukri",
            "Square",
            "Render",
            "ntc.party (включить обход по IPv4)",
        ),
    ),
    HostsGroup(
        key="media",
        title="Музыка, видео и развлечения",
        examples="Spotify, Twitch, YouTube, Deezer, торренты, манга",
        services=(
            "Spotify",
            "Deezer",
            "Twitch",
            "YouTube (иногда может не работать с ним! Отключите тумблер если YouTube не работает с пресетами)",
            "MangaLib",
            "Rutor",
            "FMHY",
            "Chess",
            "Supercell",
            "Imgur",
            "Web Archive",
            "Strava",
        ),
    ),
    HostsGroup(
        key="rest",
        title="Остальное из каталога",
        examples="Погода, поиск, почта и всё, что не попало в группы выше",
        takes_the_rest=True,
    ),
    HostsGroup(
        key="adobe",
        title="Программы Adobe",
        examples="Блокирует серверы проверки лицензий Photoshop, Illustrator и остальных",
        source_domains=True,
    ),
)

_HOSTS_GROUP_BY_KEY = {group.key: group for group in HOSTS_GROUPS}


def catalog_services() -> tuple[str, ...]:
    """Все сервисы каталога. Пустой кортеж, если каталог недоступен."""
    try:
        from hosts.proxy_domains import get_all_services

        return tuple(str(name) for name in (get_all_services() or ()) if str(name).strip())
    except Exception:
        return ()


def _is_ai(name: str) -> bool:
    """Тот же признак «нейросеть», что и на странице «Сервисы».

    Отдельного списка здесь нет намеренно: раздел «ИИ» на странице и
    галочка «Нейросети» в мастере обязаны означать одно и то же.
    """
    try:
        from hosts.page_plans import is_ai_service

        return bool(is_ai_service(name))
    except Exception:
        return False


def group_services(group_key: str) -> tuple[str, ...]:
    """Сервисы каталога, которые включает одна галочка."""
    group = _HOSTS_GROUP_BY_KEY.get(str(group_key))
    if group is None or group.source_domains:
        return ()

    services = catalog_services()
    if group.from_ai_section:
        return tuple(name for name in services if _is_ai(name))

    if group.takes_the_rest:
        claimed = set()
        for other in HOSTS_GROUPS:
            if other.key == group.key or other.source_domains:
                continue
            claimed.update(group_services(other.key))
        return tuple(name for name in services if name not in claimed)

    known = set(services)
    return tuple(name for name in group.services if name in known)


def default_hosts_groups() -> frozenset[str]:
    """Что отмечено на экране при открытии.

    Совпадает с умолчанием hosts/defaults.py, и это не совпадение: два
    места, решающие «что включено сразу», обязаны говорить одно и то же.
    """
    return frozenset(g.key for g in HOSTS_GROUPS if g.default_enabled)


def normalize_hosts_groups(keys) -> frozenset[str]:
    """Отбрасывает незнакомые ключи групп."""
    return frozenset(str(k) for k in keys or () if str(k) in _HOSTS_GROUP_BY_KEY)


def wants_telegram_hosts(selection, hosts_groups=None) -> bool:
    """Прописывать ли сайты Telegram по ответам мастера.

    Смысл ``hosts_groups`` тот же, что в ``build_oneclick_request``:
    передали ответ экрана hosts — решает он, не передали — общий выбор.
    """
    if hosts_groups is not None:
        return any(
            _HOSTS_GROUP_BY_KEY[key].telegram_hosts
            for key in normalize_hosts_groups(hosts_groups)
        )
    return any(
        _CHOICE_BY_KEY[key].telegram_hosts for key in normalize_selection(selection)
    )


def hosts_service_profiles(group_keys) -> dict[str, str]:
    """Отображение «сервис каталога -> профиль» по ответу мастера.

    Именно в таком виде выбор хранится и показывается на странице
    «Сервисы»: переключатели и колонка «Профиль» читают его.
    """
    try:
        from hosts.proxy_domains import get_service_available_dns_profiles, prefer_measured_profiles
    except Exception:
        return {}

    out: dict[str, str] = {}
    for key in sorted(normalize_hosts_groups(group_keys)):
        for service in group_services(key):
            try:
                available = prefer_measured_profiles(service, get_service_available_dns_profiles(service) or [])
            except Exception:
                available = []
            if not available:
                continue
            if PREFERRED_DNS_PROFILE in available:
                out[service] = PREFERRED_DNS_PROFILE
                continue

            # Порядок — общий с умолчаниями (hosts/defaults.py): без XBOX
            # раньше брался первый в каталоге, XBOX DNS (old), самый слабый
            # из живых профилей по замеру.
            out[service] = choose_profile(available)
            # Сервисы с прямыми записями сюда попадают штатно: у них
            # профиль один и называется иначе. Сервис с подменой DNS без
            # xbox_dns — обычно XBOX, убранный по замеру
            # (json/hosts_catalog/net67_dead_profiles.json); в журнал —
            # какой профиль взят вместо него.
            if len(available) > 1 or available[0] != DIRECT_HOSTS_PROFILE:
                log(
                    f"{service}: нет профиля {PREFERRED_DNS_PROFILE}, взят {out[service]}",
                    "INFO",
                )
    return out


def hosts_entries_for_groups(group_keys) -> dict[str, str]:
    """Записи hosts по ответу мастера."""
    selected = normalize_hosts_groups(group_keys)
    entries: dict[str, str] = {}

    if "adobe" in selected:
        try:
            from hosts.adobe_domains import ADOBE_DOMAINS

            entries.update(ADOBE_DOMAINS)
        except Exception:
            pass

    for service in sorted(hosts_service_profiles(selected)):
        for host, ip in _catalog_rows(service):
            host = str(host or "").strip()
            ip = str(ip or "").strip()
            if host and ip:
                entries[host] = ip

    return entries


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


#: Профиль DNS для всех сервисов, выбранных в мастере.
#:
#: Не «по возможности», а всегда, когда сервис его поддерживает. Разные
#: резолверы отдают разные адреса, и набор из четырёх профилей вперемешку
#: — это четыре разных набора адресов в одном файле hosts, которые потом
#: устаревают вразнобой. Один профиль на всех делает поломку понятной:
#: перестало работать — значит устарел он.
#:
#: Сервисам с прямыми записями в hosts подмена не нужна вовсе: у них
#: подменного профиля нет, и там берётся единственный доступный.
#:
#: Константа общая с hosts/defaults.py: своя копия здесь осталась на
#: xbox_dns, когда умолчание сменилось, — мастер и страница hosts выбирали
#: бы разное.
from hosts.defaults import PREFERRED_DNS_PROFILE  # noqa: E402


def build_hosts_service_profiles(selection) -> dict[str, str]:
    """Отображение «сервис каталога -> профиль» для страницы hosts.

    Именно в таком виде выбор хранится и отображается на странице
    «Редактор hosts»: переключатели и колонка «Профиль» читают его.
    Если писать в hosts только готовые пары «домен -> адрес», записи
    появятся, а переключатели останутся выключенными — человек решит,
    что мастер ничего не сделал.
    """
    try:
        from hosts.proxy_domains import get_service_available_dns_profiles, prefer_measured_profiles
    except Exception:
        return {}

    out: dict[str, str] = {}
    for key in sorted(normalize_selection(selection)):
        for service in _CHOICE_BY_KEY[key].hosts_services:
            try:
                available = prefer_measured_profiles(service, get_service_available_dns_profiles(service) or [])
            except Exception:
                available = []
            if not available:
                continue
            if PREFERRED_DNS_PROFILE in available:
                out[service] = PREFERRED_DNS_PROFILE
                continue

            # Порядок — общий с умолчаниями (hosts/defaults.py): без XBOX
            # раньше брался первый в каталоге, XBOX DNS (old), самый слабый
            # из живых профилей по замеру.
            out[service] = choose_profile(available)
            # Сервисы с прямыми записями сюда попадают штатно: у них
            # профиль один и называется иначе. Сервис с подменой DNS без
            # xbox_dns — обычно XBOX, убранный по замеру
            # (json/hosts_catalog/net67_dead_profiles.json); в журнал —
            # какой профиль взят вместо него.
            if len(available) > 1 or available[0] != DIRECT_HOSTS_PROFILE:
                log(
                    f"{service}: нет профиля {PREFERRED_DNS_PROFILE}, "
                    f"взят {out[service]}",
                    "INFO",
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
    hosts_groups=None,
    allow_dns_fix: bool = True,
    run_selfcheck: bool = True,
) -> OneClickRequest:
    """Собирает запрос для оркестратора из ответов мастера.

    ``hosts_groups`` — ответ с экрана «Что должно работать без VPN».
    Он отвечает только за записи в hosts; подбор стратегии и прокси
    Telegram по-прежнему считаются по всему набору категорий, потому
    что обход включается целиком и выбирать там нечего.

    Не передали — работает как раньше, по общему выбору. Так старые
    вызовы и тесты остаются рабочими.
    """
    selected = normalize_selection(selection)
    entries = (
        build_hosts_entries(selected)
        if hosts_groups is None
        else hosts_entries_for_groups(hosts_groups)
    )
    return OneClickRequest(
        services=selected,
        hosts_entries=entries,
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


#: Экран «Чем вы пользуетесь?» когда-то убрали, и правильно: обходы
#: включаются все сразу, ответ ни на что не влиял.
#:
#: Вернулся он с другим вопросом и с настоящей работой. Обход и записи
#: в hosts — разные механизмы: обход лечит блокировку у провайдера,
#: hosts лечит отказ по стране на стороне самого сервиса. Первое можно
#: включить всем и сразу, второе нельзя: подмена адреса стоит денег, и
#: платит за неё тот, кому сервис и так открывался.
#:
#: Провайдер на результат влияет отдельно: оборудование фильтрации у
#: них разное, и стратегия, работающая на одном, на другом может не
#: дать ничего. Ответ выбирает пресет, с которого начать; что подойдёт
#: на самом деле, показывает следующий экран с проверкой.
WIZARD_STEPS: tuple[WizardStep, ...] = (
    WizardStep(
        key="provider",
        title="Какой у вас провайдер?",
        subtitle="От него зависит, какие настройки обхода взять за основу",
    ),
    WizardStep(
        key="hosts",
        title="Что должно работать без VPN?",
        subtitle="Эти сервисы закрывают доступ сами, по стране — обход DPI им не поможет",
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
