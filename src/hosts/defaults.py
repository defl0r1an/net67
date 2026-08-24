"""Что включено на странице «Сервисы» сразу после установки.

Включаются две вещи: вся группа «Напрямую из hosts» и вся группа «ИИ»
с профилем XBOX DNS. Остальные сервисы с подменой DNS остаются
выключенными, и такая асимметрия — не забывчивость.

Сначала включались все 72 сервиса разом. Приложение рапортовало «обход
работает», а сайты не открывались. Причина в том, что подмена DNS
прибивает 821 домен к адресам, записанным в каталог в момент его сборки.
Для обычного сайта это плохой обмен: у JetBrains в каталоге больше
шестидесяти разных адресов Akamai и AWS, у Naukri — за полсотни. Такие
адреса живут неделями, а записанный в hosts адрес не обновится никогда.
Устаревший адрес убивает домен целиком — хуже, чем блокировка, потому
что блокировку DPI-обход вылечил бы сам.

Для нейросетей обмен обратный, и поэтому они включены. ChatGPT, Claude,
Gemini и Grok закрывают доступ сами, по стране запроса, и DPI-обходу тут
чинить нечего: соединение не блокируют, его отвергает сам сервис. У этих
сервисов в каталоге под XBOX DNS стоят общие адреса вроде
87.228.47.204 — один адрес обслуживает домены сразу нескольких сервисов,
то есть это точка входа, а не сервер OpenAI. Рискуем не работающим
доступом, а неработающим — он и так неработающий.

Модуль без побочных эффектов: он только решает, что должно быть выбрано.
Запись в файл hosts делает hosts.commands.apply_service_profiles.
"""

from __future__ import annotations


#: Профиль DNS, который берём, когда сервис поддерживает несколько.
#:
#: XBOX DNS — тот же выбор, что и в мастере первого запуска. Держать два
#: разных умолчания в одном приложении было бы источником расхождений.
PREFERRED_DNS_PROFILE = "xbox_dns"

#: Профиль прямой записи в hosts: настоящий адрес сервиса, без прокси.
DIRECT_HOSTS_PROFILE = "hosts"

#: Включать ли по умолчанию сервисы с подменой DNS.
#:
#: Выключено намеренно, см. описание модуля. Человек включает нужное сам
#: на странице «Сервисы» — там видно, что именно он включает.
ENABLE_DNS_SUBSTITUTION_BY_DEFAULT = False

#: Исключение из правила выше: группа «ИИ».
#:
#: Эти сервисы отказывают по стране запроса, а не по DPI, поэтому без
#: подмены адреса они не работают вообще. Группа берётся той же
#: функцией, что рисует раздел «ИИ» на странице, — два независимых
#: списка «что такое нейросеть» неизбежно разошлись бы.
ENABLE_AI_DNS_SUBSTITUTION_BY_DEFAULT = True

#: Сервисы, которые остаются выключенными.
#:
#: Сверяем по началу имени: полные названия в каталоге содержат
#: пояснение в скобках и могут поменяться.
#:
#: YouTube сам предупреждает в своём названии, что с ним «иногда может не
#: работать» и тумблер надо отключить, если YouTube не открывается с
#: пресетами. Включать по умолчанию то, что может сломать работающий
#: сервис, — плохой обмен: DPI-обход и так справляется с YouTube.
DISABLED_BY_DEFAULT: tuple[str, ...] = ("YouTube",)


def is_disabled_by_default(service_name: str) -> bool:
    name = str(service_name or "").strip().casefold()
    return any(name.startswith(prefix.casefold()) for prefix in DISABLED_BY_DEFAULT)


def is_ai_service(service_name: str) -> bool:
    """Относится ли сервис к группе «ИИ» на странице «Сервисы»."""
    from hosts.page_plans import is_ai_service as _is_ai

    return bool(_is_ai(service_name))


def choose_profile(available_profiles) -> str:
    """Профиль для сервиса из списка доступных. Пустая строка — нечего выбрать."""
    profiles = [str(p).strip() for p in (available_profiles or ()) if str(p).strip()]
    if not profiles:
        return ""
    if PREFERRED_DNS_PROFILE in profiles:
        return PREFERRED_DNS_PROFILE
    return profiles[0]


def build_default_selection(
    service_names,
    available_profiles_by_service,
) -> dict[str, str]:
    """Выбор по умолчанию: {сервис: профиль}.

    Аргументы передаются снаружи, поэтому правило проверяется без чтения
    каталога с диска.
    """
    selection: dict[str, str] = {}
    for service_name in service_names or ():
        name = str(service_name or "").strip()
        if not name or is_disabled_by_default(name):
            continue
        available = (available_profiles_by_service or {}).get(name)

        if is_ai_service(name) and ENABLE_AI_DNS_SUBSTITUTION_BY_DEFAULT:
            # Нейросети включаем ровно на XBOX DNS. Молча подставить
            # другой резолвер, если этого нет, — значит включить не то,
            # что здесь написано, и не сказать об этом.
            if PREFERRED_DNS_PROFILE in [str(p).strip() for p in (available or ())]:
                selection[name] = PREFERRED_DNS_PROFILE
                continue

        profile = choose_profile(available)
        if not profile:
            continue
        if profile != DIRECT_HOSTS_PROFILE and not ENABLE_DNS_SUBSTITUTION_BY_DEFAULT:
            continue
        selection[name] = profile
    return selection


def load_default_selection() -> dict[str, str]:
    """Тот же выбор, но с чтением каталога сервисов."""
    from hosts.proxy_domains import get_all_services, get_service_available_dns_profiles

    services = list(get_all_services() or ())
    available = {name: list(get_service_available_dns_profiles(name) or ()) for name in services}
    return build_default_selection(services, available)


__all__ = [
    "ENABLE_AI_DNS_SUBSTITUTION_BY_DEFAULT",
    "DISABLED_BY_DEFAULT",
    "is_ai_service",
    "PREFERRED_DNS_PROFILE",
    "build_default_selection",
    "choose_profile",
    "is_disabled_by_default",
    "load_default_selection",
]
