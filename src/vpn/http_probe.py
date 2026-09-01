"""Проверка сервера настоящим запросом через него.

## Чем это отличается от прежней проверки

`vpn/ping.py` стучится в сам сервер: ICMP, TCP или UDP-проба по его
порту. Для WireGuard это единственный доступный способ, но он отвечает
не на тот вопрос. «Порт открыт» не значит «через сервер можно работать»:
узел может отвечать на TCP и при этом не пропускать трафик, упираться в
исчерпанную подписку или блокировать нужный сайт.

Серверы из подписки поднимаются ядром Xray, и с ними можно иначе:
сходить через сервер по-настоящему — обычным HTTPS-запросом к внешнему
адресу. Так делает Happ, и ответ получается о том, что человека
интересует: работает или нет, и насколько быстро.

## Что именно замеряется

Время до первого байта ответа, а не время загрузки страницы. Поэтому
цель — маленький адрес, отдающий пустой ответ с кодом 204: он не тратит
время на передачу тела и одинаково быстр во всём мире.

## Через что идёт запрос

Через локальный SOCKS ядра. Значит, проверка возможна, только когда
ядро поднято на нужном сервере — то есть при переключении сервера или
на подключённом соединении. Спрашивать «а как быстр вон тот сервер, к
которому мы не подключены» этим способом нельзя, и притворяться, что
можно, не надо.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass


#: Куда стучимся. Адрес отдаёт «204 без тела» и живёт у Cloudflare,
#: то есть близок почти к любому серверу — замер получается про канал до
#: сервера, а не про путь от сервера до далёкого сайта.
PROBE_URL = "http://cp.cloudflare.com/generate_204"

#: Запасной адрес: если первый заблокирован или лежит, проверка не
#: должна объявлять сервер мёртвым.
PROBE_URL_FALLBACK = "http://www.gstatic.com/generate_204"

#: Сколько ждём. Три секунды — с запасом для дальнего сервера; всё, что
#: дольше, человек и так посчитает неработающим.
PROBE_TIMEOUT = 3.0

#: Код, который ждём. Именно 204: тело пустое, и время ответа не зависит
#: от размера страницы.
EXPECTED_STATUS = 204


@dataclass(frozen=True, slots=True)
class HttpProbeResult:
    ok: bool
    latency_ms: float | None
    message: str
    status: int | None = None

    def describe(self) -> str:
        if self.ok and self.latency_ms is not None:
            return f"{int(self.latency_ms)} мс"
        return self.message


def _probe_once(url: str, *, proxy_address: str, timeout: float) -> HttpProbeResult:
    """Один запрос через SOCKS. Возвращает результат, не бросает."""
    try:
        import requests
    except ImportError:
        return HttpProbeResult(False, None, "Нет библиотеки requests")

    host, _, port = str(proxy_address or "").partition(":")
    if not host or not port:
        return HttpProbeResult(False, None, "Не задан адрес локального прокси")

    # socks5h, а не socks5: имя должен разрешать сервер, а не мы. Иначе
    # проверка пойдёт через наш DNS, и замер окажется про наш канал, а
    # не про канал сервера — а при подменённом DNS ещё и уведёт не туда.
    proxies = {
        "http": f"socks5h://{host}:{port}",
        "https": f"socks5h://{host}:{port}",
    }

    started = time.monotonic()
    try:
        response = requests.get(
            url,
            proxies=proxies,
            timeout=timeout,
            allow_redirects=False,
        )
    except Exception as exc:
        return HttpProbeResult(False, None, _explain(exc))

    latency_ms = (time.monotonic() - started) * 1000.0

    if response.status_code != EXPECTED_STATUS:
        # Не ошибка сети, а чужой ответ: так выглядит перехват запроса
        # порталом или страницей провайдера.
        return HttpProbeResult(
            False,
            latency_ms,
            f"Ответ {response.status_code} вместо {EXPECTED_STATUS} — запрос перехвачен",
            response.status_code,
        )

    return HttpProbeResult(True, latency_ms, "Сервер отвечает", response.status_code)


def _explain(exc: Exception) -> str:
    """Человеческая причина вместо текста библиотеки."""
    try:
        import requests
    except ImportError:
        return str(exc)

    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return "Сервер не ответил вовремя"
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return "Соединение установлено, но данных нет"
    if isinstance(exc, requests.exceptions.ProxyError):
        # Самая частая причина: ядро не поднято или поднято на другом
        # сервере. Так и говорим, вместо «SOCKSHTTPConnectionPool...».
        return "Локальный прокси не отвечает — ядро не запущено"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Соединение через сервер не установилось"
    return str(exc)[:120]


def check_through_proxy(
    *,
    proxy_address: str,
    timeout: float = PROBE_TIMEOUT,
    urls: tuple[str, ...] = (PROBE_URL, PROBE_URL_FALLBACK),
) -> HttpProbeResult:
    """Проверяет сервер настоящим запросом через него.

    Запасной адрес пробуется, только если первый не ответил по сети.
    Чужой код ответа запасным адресом не лечится: он говорит о перехвате
    запроса, а не о недоступности цели.
    """
    last = HttpProbeResult(False, None, "Проверять нечем")

    for url in urls:
        last = _probe_once(url, proxy_address=proxy_address, timeout=timeout)
        if last.ok or last.status is not None:
            return last

    return last


def is_probe_possible(*, core_running: bool) -> tuple[bool, str]:
    """Можно ли сейчас проверить сервер этим способом.

    Проверка идёт через локальный SOCKS, значит нужно поднятое ядро.
    Молча возвращать «не отвечает» при выключенном ядре нельзя: это
    сказало бы неправду о сервере.
    """
    if not core_running:
        return (False, "Подключитесь к серверу — проверка идёт через него")
    return (True, "")


__all__ = [
    "EXPECTED_STATUS",
    "PROBE_TIMEOUT",
    "PROBE_URL",
    "PROBE_URL_FALLBACK",
    "HttpProbeResult",
    "check_through_proxy",
    "is_probe_possible",
]
