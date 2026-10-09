# dns/dns_providers.py
"""
Список DNS провайдеров для UI

Значок ("icon") рисует profile.ui.profile_icon: кроме имён Font Awesome
("fa5s.*", "fa5b.*") подходят фирменные логотипы "simple:<имя>:<буквы>" и свои
SVG "own:<имя>:<буквы>". У серверов из раздела «Для ИИ» значок и цвет те же,
что у одноимённого DNS-профиля в «Редакторе hosts» (hosts/ui/profile_icons.py):
один сервер — один значок во всей программе.
"""

DNS_PROVIDERS = {
    "Популярные": {
        "Cloudflare": {
            "ipv4": ["1.1.1.1", "1.0.0.1"],
            "ipv6": ["2606:4700:4700::1111", "2606:4700:4700::1001"],
            "desc": "Быстрый и приватный",
            "icon": "simple:cloudflare:CF",
            "color": "#f48120",
            "doh": "https://cloudflare-dns.com/dns-query"
        },
        "Google DNS": {
            "ipv4": ["8.8.8.8", "8.8.4.4"],
            "ipv6": ["2001:4860:4860::8888", "2001:4860:4860::8844"],
            "desc": "Надёжный",
            "icon": "fa5b.google",
            "color": "#4285f4",
            "doh": "https://dns.google/dns-query"
        },
        "Dns.SB": {
            "ipv4": ["185.222.222.222", "45.11.45.11"],
            "ipv6": ["2a09::", "2a11::"],
            "desc": "Без цензуры",
            "icon": "fa5s.unlock-alt",
            "color": "#00bcd4",
            "doh": "https://doh.sb/dns-query"
        },
        # Серверы в России — самый короткий путь для большинства пользователей.
        # DoH у Яндекса только по HTTP/2: requests его не проверит, Windows — умеет.
        "Яндекс DNS": {
            "ipv4": ["77.88.8.8", "77.88.8.1"],
            "ipv6": ["2a02:6b8::feed:0ff", "2a02:6b8:0:1::feed:0ff"],
            "desc": "Быстрый в России",
            "icon": "fa5b.yandex",
            "color": "#fc3f1d",
            "doh": "https://common.dot.dns.yandex.net/dns-query"
        },
        "Control D": {
            "ipv4": ["76.76.2.0", "76.76.10.0"],
            "ipv6": ["2606:1a40::", "2606:1a40:1::"],
            "desc": "Без фильтров",
            "icon": "fa5s.sliders-h",
            "color": "#5a67d8",
            "doh": "https://freedns.controld.com/p0"
        },
    },
    "Безопасные": {
        "Quad9": {
            "ipv4": ["9.9.9.9", "149.112.112.112"],
            "ipv6": ["2620:fe::fe", "2620:fe::9"],
            "desc": "Антивирус",
            "icon": "simple:quad9:Q9",
            "color": "#e91e63",
            "doh": "https://dns.quad9.net/dns-query"
        },
        "AdGuard": {
            "ipv4": ["94.140.14.14", "94.140.15.15"],
            "ipv6": ["2a10:50c0::ad1:ff", "2a10:50c0::ad2:ff"],
            "desc": "Без рекламы",
            "icon": "simple:adguard:AG",
            "color": "#68bc71",
            # Прежний dns.adguard.com перестал отвечать (замер 2026-09-30).
            "doh": "https://dns.adguard-dns.com/dns-query"
        },
        "OpenDNS": {
            "ipv4": ["208.67.222.222", "208.67.220.220"],
            "ipv6": ["2620:119:35::35", "2620:119:53::53"],
            "desc": "Фильтрация",
            "icon": "own:opendns:OD",
            "color": "#fe7702",
            "doh": "https://doh.opendns.com/dns-query"
        },
        # Адрес у сервиса один. DoH переехал с порта 444 на обычный 443:
        # 444 закрыт (замер 2026-09-30).
        "dnsdoh.art": {
            "ipv4": ["194.180.189.33"],
            "ipv6": [],
            "desc": "Максимальная приватность",
            "icon": "fa5s.lock",
            "color": "#9c27b0",
            "doh": "https://dnsdoh.art/dns-query"
        },
        "Cloudflare Family": {
            "ipv4": ["1.1.1.3", "1.0.0.3"],
            "ipv6": ["2606:4700:4700::1113", "2606:4700:4700::1003"],
            "desc": "Без вирусов и сайтов 18+",
            "icon": "fa5s.child",
            "color": "#f48120",
            "doh": "https://family.cloudflare-dns.com/dns-query"
        },
        "Яндекс Безопасный": {
            "ipv4": ["77.88.8.88", "77.88.8.2"],
            "ipv6": ["2a02:6b8::feed:bad", "2a02:6b8:0:1::feed:bad"],
            "desc": "Без мошеннических сайтов",
            "icon": "fa5s.user-lock",
            "color": "#fc3f1d",
            "doh": "https://safe.dot.dns.yandex.net/dns-query"
        },
    },
    # Xbox DNS (оба) и dns.malw.link убраны 9 октября 2026. Xbox DNS с
    # 8 октября отвечает 0.0.0.0 на ChatGPT, Claude, Gemini, Grok и Copilot,
    # dns.malw.link не отвечает вовсе (замер обычным DNS по UDP). Их адреса
    # на адаптерах программа переводит на GeoHide (OUTDATED_DNS_ADDRESS_REPLACEMENTS).
    "Для ИИ": {
        "Comss DNS": {
            "ipv4": ["83.220.169.155", "212.109.195.93"],
            "ipv6": [],
            "desc": "ChatGPT",
            "icon": "fa5s.shield-alt",
            "color": "#2F80ED",
            "doh": "https://dns.comss.one/dns-query"
        },
        # Адреса — у официального имени DoH dns.astracat.network: опубликованный
        # на сайте 85.209.2.112 на обычные DNS-запросы не отвечает (проверено 2026-09-29).
        "AstraCat": {
            "ipv4": ["135.106.217.200", "135.106.197.22"],
            "ipv6": [],
            "desc": "ChatGPT, без рекламы",
            "icon": "fa5s.cat",
            "color": "#F59E0B",
            "doh": "https://dns.astracat.network/dns-query"
        },
        # Российская пара из официального geohide.ru/static/metadata/servers.json.
        # Подменяет ответы только для сайтов из своего списка (ChatGPT, Grok, Notion…).
        "GeoHide": {
            "ipv4": ["193.233.112.67", "193.233.112.68"],
            "ipv6": [],
            "desc": "ChatGPT, Grok, Notion",
            "icon": "fa5s.globe-europe",
            "color": "#8B5CF6",
            "doh": "https://geohide.ru/dns-query"
        },
    }
}

def doh_templates() -> dict[str, str]:
    """{адрес сервера: шаблон DoH} для всех серверов списка (IPv4 и IPv6).

    Windows 11 по этим шаблонам сама шифрует DNS-запросы к известным
    серверам, а при недоступности DoH откатывается на обычный DNS.
    """
    templates: dict[str, str] = {}
    for group in DNS_PROVIDERS.values():
        for data in group.values():
            template = str(data.get("doh") or "").strip()
            if not template:
                continue
            for address in (*data.get("ipv4", ()), *data.get("ipv6", ())):
                templates.setdefault(str(address).strip(), template)
    return templates


# Старые адреса DNS из списка выше и их новые замены.
# Если пользователь когда-то выбрал этот DNS и адрес остался в настройках
# сетевого адаптера, программа при запуске сама меняет его на новый.
# При каждой смене адресов провайдера добавлять сюда пару «старый → новый».
OUTDATED_DNS_ADDRESS_REPLACEMENTS = {
    # Xbox DNS закрыл сервисы ИИ (8 октября 2026: 0.0.0.0 на ChatGPT, Claude,
    # Gemini, Grok, Copilot), плитки убраны. Все его адреса — действующие,
    # прежние .50/.51, v2 и (old) — ведут на GeoHide: он открывает те же
    # сайты обычным DNS по UDP, без DoH (замер 9 октября 2026), поэтому
    # замена годится и для Windows без шифрованного DNS.
    "111.88.96.50": "193.233.112.67",
    "111.88.96.51": "193.233.112.68",
    "111.88.96.54": "193.233.112.67",
    "111.88.96.55": "193.233.112.68",
    "87.228.47.200": "193.233.112.67",
    "87.228.47.201": "193.233.112.68",
    "176.99.11.77": "193.233.112.67",
    "80.78.247.254": "193.233.112.68",
    # dns.malw.link не отвечает ни по одному адресу (9 октября 2026).
    "84.21.189.133": "193.233.112.67",
    "64.188.98.242": "193.233.112.68",
    "95.216.204.218": "193.233.112.67",
    "80.253.249.40": "193.233.112.68",
    # IPv6 у GeoHide нет, поэтому адреса IPv6 этих серверов просто убираются
    # (пустая замена). Опустевший список возвращает адаптеру автоматические
    # DNS для IPv6 — лучше, чем сервер, отвечающий 0.0.0.0 или молчащий.
    "2a00:ab00:1233:26::50": "",
    "2a00:ab00:1233:26::51": "",
    "2a01:4f9:c014:6dac::1": "",
    "2a12:bec4:1460:5b7::2": "",
    "2a12:bec4:1460:d5::2": "",
    "2a01:ecc0:2c1:2::2": "",
}
