"""Что проверять при запуске и куда потом класть найденную стратегию.

Замысел: после старта движка проверить несколько заметных сайтов. Если
какой-то не открывается даже с включённым обходом, значит пресет
провайдера этой сети не подошёл — надо искать стратегию перебором.

Ключевая тонкость, которую легко потерять: **проверять надо после того,
как движок поднялся**. Если проверить раньше, недоступным окажется всё,
и подбор запустится на пустом месте, съев минуты на каждой машине.

Куда применять найденное — тоже не произвольно. Профиль по имени сайта
чинит только этот сайт; чтобы починилось «вообще всё», стратегия должна
лечь ещё и в общий профиль по адресам. Поэтому у каждой цели два адреса
применения: свой профиль и общий.
"""

from __future__ import annotations

from dataclasses import dataclass, field


#: Общий профиль «поймать всё по адресам, UDP». Его чинят вместе с
#: конкретным сайтом: без него правится один домен, а не доступ вообще.
CATCH_ALL_UDP_PROFILE = "Все сайты UDP (айпи)"

#: Общий профиль по адресам для TCP.
CATCH_ALL_TCP_PROFILE = "General list TCP"


@dataclass(frozen=True, slots=True)
class Target:
    """Сайт для проверки при запуске.

    url         — что открываем при проверке (TLS до конца, с проверкой
                  имени в сертификате: TCP-коннект врёт, см. oneclick).
    scan_target — что скармливать перебору стратегий.
    profiles    — профили пресета, куда класть найденное.
    protocol    — какой перебор запускать.
    """

    key: str
    title: str
    url: str
    scan_target: str
    profiles: tuple[str, ...] = field(default_factory=tuple)
    protocol: str = "tcp_https"


#: Проверяемые сайты. Список намеренно короткий: каждая цель — это
#: отдельный перебор стратегий на минуты, и раздувать его нельзя.
TARGETS: tuple[Target, ...] = (
    Target(
        key="youtube",
        title="YouTube",
        url="https://www.youtube.com",
        scan_target="youtube.com",
        # YouTube правится отдельно: у него свои профили под интерфейс,
        # видео и QUIC, и общий профиль их не заменяет.
        profiles=(
            "youtube.com (интерфейс)",
            "googlevideo.com (CDN сервера)",
            "youtube.com (QUIC)",
            CATCH_ALL_UDP_PROFILE,
        ),
    ),
    Target(
        key="discord",
        title="Discord",
        url="https://discord.com",
        scan_target="discord.com",
        profiles=("discord.com", CATCH_ALL_TCP_PROFILE, CATCH_ALL_UDP_PROFILE),
    ),
    Target(
        key="rutracker",
        title="Rutracker",
        url="https://rutracker.org",
        scan_target="rutracker.org",
        profiles=("Мои сайты", CATCH_ALL_TCP_PROFILE),
    ),
)

_BY_KEY: dict[str, Target] = {item.key: item for item in TARGETS}


def get_target(key: object) -> Target | None:
    return _BY_KEY.get(str(key or "").strip().lower())


def all_keys() -> tuple[str, ...]:
    return tuple(item.key for item in TARGETS)


__all__ = [
    "CATCH_ALL_TCP_PROFILE",
    "CATCH_ALL_UDP_PROFILE",
    "TARGETS",
    "Target",
    "all_keys",
    "get_target",
]
