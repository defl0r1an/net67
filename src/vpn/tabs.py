"""Разделение профилей VPN на вкладки.

Вкладок две, и делят они не протоколы, а способ подключения.

«Amnezia» — всё, что поднимается клиентом amneziawg.exe: и ключи
vpn://, и обычные файлы .conf. Раньше это были две отдельные вкладки,
AmneziaWG и WireGuard, и разделение было формально верным — обфускация
либо есть, либо нет, — но бесполезным: клиент один, порядок действий
один, и человек всё равно вставлял конфиг туда, где было место. Сведены
обратно по прямой просьбе.

«VPN» — подключение по ссылке: vless, vmess, trojan, shadowsocks. Это
другой клиент (xray) и другой порядок действий, поэтому вкладка своя.

Модуль без Qt: правила проверяются без интерфейса.
"""

from __future__ import annotations


#: Ключ вкладки Amnezia — всё семейство WireGuard: и ключи vpn:// с
#: маскировкой, и обычные файлы .conf.
TAB_AMNEZIA = "amnezia"

#: Ключ вкладки подключения по ссылке: vless, vmess, trojan, ss.
TAB_LINKS = "links"

#: Прежний ключ отдельной вкладки WireGuard. Оставлен ради сохранённых
#: настроек: у тех, кто уже пользовался программой, в файле лежит именно
#: он, и normalize_tab обязан его понять, а не сбросить выбор молча.
TAB_WIREGUARD = "wireguard"

#: Порядок вкладок. Amnezia первой: ей пользуются, ссылки — про запас.
TAB_ORDER: tuple[str, ...] = (TAB_AMNEZIA, TAB_LINKS)

TAB_TITLES: dict[str, str] = {
    TAB_AMNEZIA: "Amnezia",
    TAB_LINKS: "VPN",
}

#: Подзаголовок страницы под каждую вкладку.
#:
#: Он менялся не всегда, и на вкладке ссылок висело «Подключение через
#: AmneziaWG или WireGuard» — то есть описание соседней вкладки.
TAB_SUBTITLES: dict[str, str] = {
    TAB_AMNEZIA: "Подключение через AmneziaWG или WireGuard",
    TAB_LINKS: "Подключение по ссылке через ядро Xray",
}

#: Подпись над полем ввода.
TAB_INPUT_TITLES: dict[str, str] = {
    TAB_AMNEZIA: "Ключ или файл конфигурации",
    TAB_LINKS: "Ссылка или подписка",
}

TAB_HINTS: dict[str, str] = {
    TAB_AMNEZIA: (
        "Ключ вида vpn://... из AmneziaVPN или файл .conf с секциями "
        "[Interface] и [Peer]. Подойдёт и конфиг с маскировкой (Jc, S1, "
        "H1), и обычный WireGuard — поднимает их один и тот же клиент."
    ),
    TAB_LINKS: (
        "Ссылка вида vless://, vmess://, trojan:// или ss:// — такие "
        "выдают многие сервисы и приложения вроде Happ. Ссылка на "
        "подписку тоже подойдёт: из неё возьмутся все серверы разом."
    ),
}

TAB_PLACEHOLDERS: dict[str, str] = {
    TAB_AMNEZIA: "vpn://... или [Interface]\nPrivateKey = ...\n\n[Peer]\nEndpoint = ...",
    TAB_LINKS: "vless://... либо ссылка на подписку",
}


#: Сколько раз надо нажать на закрытую вкладку, чтобы она открылась.
#: Десять — по просьбе. Случайно столько не нажимают, а тот, кому надо,
#: знает.
LINKS_UNLOCK_CLICKS = 10

#: Что показывать, пока вкладка закрыта.
LINKS_LOCKED_MESSAGE = "Раздел в разработке"

#: Подсказка на подходе к открытию. Показывается с середины пути, иначе
#: первые нажатия выглядят как «кнопка не работает».
LINKS_ALMOST_TEMPLATE = "Раздел в разработке. Осталось нажатий: {left}"


def locked_click_feedback(clicks: int) -> tuple[bool, str]:
    """Что делать на очередное нажатие по закрытой вкладке.

    Возвращает (открылась, что сказать человеку). Счёт ведёт вызывающий:
    состояние интерфейса — не дело этого модуля, здесь только правило.
    """
    count = max(0, int(clicks))
    if count >= LINKS_UNLOCK_CLICKS:
        return (True, "Раздел открыт")

    left = LINKS_UNLOCK_CLICKS - count
    if left <= LINKS_UNLOCK_CLICKS // 2:
        return (False, LINKS_ALMOST_TEMPLATE.format(left=left))
    return (False, LINKS_LOCKED_MESSAGE)


def normalize_tab(key: object) -> str:
    """Приводит ключ вкладки к известному. Неизвестный — Amnezia.

    Прежний ключ «wireguard» отдельной вкладкой больше не является и
    переводится в Amnezia: у тех, кто уже пользовался программой, в
    настройках лежит именно он, и молча сбрасывать их выбор нельзя.
    """
    text = str(key or "").strip().lower()
    if text == TAB_WIREGUARD:
        return TAB_AMNEZIA
    return text if text in TAB_ORDER else TAB_AMNEZIA


def tab_for_profile(profile) -> str:
    """Вкладка, которой принадлежит профиль.

    Ссылочные профили узнаём по полю `link`: их поднимает другой клиент,
    и в списке Amnezia им делать нечего. Всё остальное — семейство
    WireGuard, независимо от наличия маскировки.
    """
    # Поле называется raw — в нём лежит исходная ссылка целиком.
    #
    # Здесь стояло `link`, которого у LinkProfile нет вовсе. getattr с
    # запасным значением молчал, и все двадцать пять серверов из
    # подписки оказывались на вкладке Amnezia: «Amnezia (25)», а вкладка
    # VPN пустая. Со стороны это выглядело как «переключение не
    # работает» — на деле переключение работало, просто по обе стороны
    # лежало не то.
    if str(getattr(profile, "raw", "") or "").strip():
        return TAB_LINKS
    if str(getattr(profile, "scheme", "") or "").strip():
        return TAB_LINKS
    return TAB_AMNEZIA


def profiles_for_tab(profiles, tab: str) -> list:
    """Профили выбранной вкладки, в исходном порядке."""
    key = normalize_tab(tab)
    return [item for item in (profiles or ()) if tab_for_profile(item) == key]


def tab_counts(profiles) -> dict[str, int]:
    """Сколько профилей на каждой вкладке — для подписей."""
    counts = {key: 0 for key in TAB_ORDER}
    for item in profiles or ():
        counts[tab_for_profile(item)] += 1
    return counts


def empty_text(tab: str) -> str:
    """Что показать, когда на вкладке пусто.

    Общее «Профили не добавлены» врало: профили могли быть, просто на
    соседней вкладке.
    """
    if normalize_tab(tab) == TAB_LINKS:
        return "Ссылок пока нет. Вставьте vless://, vmess://, trojan:// или ss:// выше."
    return "Профилей пока нет. Вставьте vpn://... или .conf выше."


__all__ = [
    "LINKS_ALMOST_TEMPLATE",
    "LINKS_LOCKED_MESSAGE",
    "LINKS_UNLOCK_CLICKS",
    "locked_click_feedback",
    "TAB_AMNEZIA",
    "TAB_INPUT_TITLES",
    "TAB_LINKS",
    "TAB_SUBTITLES",
    "TAB_HINTS",
    "TAB_ORDER",
    "TAB_PLACEHOLDERS",
    "TAB_TITLES",
    "TAB_WIREGUARD",
    "empty_text",
    "normalize_tab",
    "profiles_for_tab",
    "tab_counts",
    "tab_for_profile",
]
