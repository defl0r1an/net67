"""Разбор ссылок на прокси-серверы: vless, vmess, trojan, ss.

Так подключаются к серверу в Happ и подобных клиентах: человеку выдают
строку `vless://…` или ссылку на подписку, он вставляет её — и сервер
появляется в списке. Никаких файлов конфигурации, никакого WireGuard.

Модуль только разбирает и приводит ссылки к общему виду. Ни сети, ни Qt,
ни запуска ядра здесь нет: правила разбора должны проверяться без
интернета и без окна на экране.

Важное ограничение, которое нельзя спрятать за красивым списком. Эти
протоколы обслуживает ядро Xray — отдельная программа, которой в
поставке net67 нет. Разобранная ссылка станет видимым сервером в списке,
но подключение к нему заработает только после того, как ядро появится
рядом. Поэтому у каждого профиля есть honest-признак `ready`, а
интерфейс обязан на него смотреть: показать «сервер добавлен» и не суметь
подключиться — худший вид вранья, потому что человек решит, что
пользуется защищённым каналом.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse


#: Схемы, которые понимает Xray. Список закрытый: неизвестная схема — это
#: не «наверное заработает», а «мы не знаем, что с этим делать».
SCHEME_VLESS = "vless"
SCHEME_VMESS = "vmess"
SCHEME_TROJAN = "trojan"
SCHEME_SHADOWSOCKS = "ss"

SUPPORTED_SCHEMES: tuple[str, ...] = (
    SCHEME_VLESS,
    SCHEME_VMESS,
    SCHEME_TROJAN,
    SCHEME_SHADOWSOCKS,
)

#: Человеческие названия протоколов для списка.
SCHEME_TITLES = {
    SCHEME_VLESS: "VLESS",
    SCHEME_VMESS: "VMess",
    SCHEME_TROJAN: "Trojan",
    SCHEME_SHADOWSOCKS: "Shadowsocks",
}


@dataclass(frozen=True, slots=True)
class LinkProfile:
    """Сервер, полученный из ссылки."""

    scheme: str
    title: str
    host: str
    port: int
    #: Исходная ссылка. Хранится целиком: ядру она нужна как есть, а
    #: пересобирать её из разобранных частей — верный способ потерять
    #: параметр, о котором мы не знали.
    raw: str
    #: Готов ли профиль к подключению прямо сейчас.
    ready: bool = False
    note: str = ""

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}" if self.host else ""

    @property
    def protocol_title(self) -> str:
        return SCHEME_TITLES.get(self.scheme, self.scheme.upper())


class LinkError(ValueError):
    """Ссылку не удалось разобрать. Текст показывается человеку."""


def _b64_decode(value: str) -> bytes:
    """Декодирует base64 без выравнивания.

    В ссылках подписок выравнивающие «=» почти всегда обрезаны, и
    штатный b64decode на них падает.
    """
    raw = str(value or "").strip().replace("-", "+").replace("_", "/")
    padding = (-len(raw)) % 4
    try:
        return base64.b64decode(raw + "=" * padding)
    except (binascii.Error, ValueError) as exc:
        raise LinkError(f"строка не является base64: {exc}") from exc


def _split_fragment_title(url, fallback: str) -> str:
    name = unquote(str(url.fragment or "")).strip()
    return name or fallback


def _parse_vmess(link: str) -> LinkProfile:
    """vmess://<base64 от JSON>.

    Формат отличается от остальных: у него нет привычного host:port в
    самой ссылке, всё лежит в JSON внутри base64.
    """
    payload = link[len(SCHEME_VMESS) + 3 :]
    try:
        data = json.loads(_b64_decode(payload).decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise LinkError(f"внутри vmess-ссылки не JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LinkError("внутри vmess-ссылки ожидался объект")

    host = str(data.get("add") or "").strip()
    try:
        port = int(str(data.get("port") or "0").strip())
    except ValueError:
        port = 0
    if not host or port <= 0:
        raise LinkError("в vmess-ссылке нет адреса или порта")

    title = str(data.get("ps") or "").strip() or host
    return LinkProfile(SCHEME_VMESS, title, host, port, link)


def _parse_generic(scheme: str, link: str) -> LinkProfile:
    url = urlparse(link)
    host = str(url.hostname or "").strip()
    port = int(url.port or 0)

    if scheme == SCHEME_SHADOWSOCKS and (not host or not port):
        # Старый формат ss://<base64 от method:pass@host:port>.
        payload = link[len(SCHEME_SHADOWSOCKS) + 3 :].split("#", 1)[0]
        decoded = _b64_decode(payload).decode("utf-8", errors="replace")
        url = urlparse(f"ss://{decoded}")
        host = str(url.hostname or "").strip()
        port = int(url.port or 0)

    if not host:
        raise LinkError("в ссылке нет адреса сервера")
    if port <= 0:
        raise LinkError("в ссылке нет порта")

    title = _split_fragment_title(urlparse(link), host)
    return LinkProfile(scheme, title, host, port, link)


def looks_like_link(text: str) -> bool:
    """Похоже ли содержимое поля на ссылку или подписку.

    Решаем по содержимому, а не по выбранной вкладке. Раньше разборщик
    выбирался вкладкой, и человек, вставив ссылку на подписку, получал
    ответ «поддерживаются только ключи, начинающиеся с vpn://» — ответ
    разборщика WireGuard, до которого строка вообще не должна была
    дойти. Содержимое однозначно: `[Interface]` не спутать с `vless://`,
    и такая развилка не зависит от того, в каком состоянии интерфейс.
    """
    raw = str(text or "").strip()
    if not raw:
        return False

    lowered = raw.lower()
    if lowered.startswith("[interface]") or "[peer]" in lowered:
        return False
    if lowered.startswith("vpn://"):
        return False

    schemes = tuple(f"{name}://" for name in SCHEME_TITLES)
    if lowered.startswith(schemes):
        return True

    # Подписка — обычная ссылка http(s) на список серверов.
    return lowered.startswith(("http://", "https://"))


def parse_link(text: str) -> LinkProfile:
    """Разбирает одну ссылку. Непонятная схема — ошибка, а не догадка."""
    link = str(text or "").strip()
    if not link:
        raise LinkError("пустая ссылка")

    scheme = link.split("://", 1)[0].strip().lower()
    if scheme not in SUPPORTED_SCHEMES:
        known = ", ".join(SUPPORTED_SCHEMES)
        raise LinkError(f"неизвестный протокол «{scheme}». Поддерживаются: {known}")

    if scheme == SCHEME_VMESS:
        return _parse_vmess(link)
    return _parse_generic(scheme, link)


def parse_subscription(text: str) -> tuple[list[LinkProfile], list[str]]:
    """Разбирает содержимое подписки: список ссылок или base64 от него.

    Возвращает (профили, ошибки). Ошибки не проглатываются: в подписке
    из тридцати серверов молча потерять три — значит показать человеку
    неполный список и не сказать об этом.
    """
    raw = str(text or "").strip()
    if not raw:
        return ([], ["пустая подписка"])

    if "://" not in raw:
        try:
            raw = _b64_decode(raw).decode("utf-8", errors="replace")
        except LinkError as exc:
            return ([], [str(exc)])

    profiles: list[LinkProfile] = []
    errors: list[str] = []
    for line in raw.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        try:
            profiles.append(parse_link(candidate))
        except LinkError as exc:
            errors.append(f"{candidate[:40]}…: {exc}")
    if not profiles and not errors:
        errors.append("в подписке не нашлось ни одной ссылки")
    return (profiles, errors)


def describe_readiness(profile: LinkProfile) -> str:
    """Что честно сказать человеку про такой сервер.

    Пока ядра Xray нет в поставке, подключение не заработает, и молчать
    об этом нельзя: человек решит, что сидит под защитой.
    """
    if profile.ready:
        return "Готов к подключению"
    return (
        "Сервер сохранён, но подключение пока недоступно: "
        "для этого протокола нужно ядро Xray, его нет в поставке"
    )


__all__ = [
    "looks_like_link",
    "SCHEME_SHADOWSOCKS",
    "SCHEME_TITLES",
    "SCHEME_TROJAN",
    "SCHEME_VLESS",
    "SCHEME_VMESS",
    "SUPPORTED_SCHEMES",
    "LinkError",
    "LinkProfile",
    "describe_readiness",
    "parse_link",
    "parse_subscription",
]
