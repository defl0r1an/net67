"""Загрузка подписки по ссылке.

Разбор содержимого уже есть в `vpn.links.parse_subscription`: он умеет и
список ссылок построчно, и base64 от него. Не хватало одного — сходить
за этим содержимым по адресу.

Именно это и упиралось в лицо человеку: он вставлял
`https://sub.example.org/XXXX`, а получал «неизвестный протокол
"https". Поддерживаются: vless, vmess, trojan, ss». Формально верно —
разборщик одной ссылки такого протокола не знает, — но по сути ответ не
на тот вопрос: это не сервер, это адрес списка серверов.

## Почему отдельный модуль

Здесь единственное место в работе с VPN, которое ходит в сеть. Держать
его отдельно от разбора значит: разбор можно проверять без сети, а сеть
— без разбора. Плюс страница не должна знать про requests.

## Про безопасность

Ходим только по http и https. Адрес приходит от человека, но подписки
раздают ссылками, и ограничиться https нельзя — часть сервисов до сих
пор отдаёт список по http.
"""

from __future__ import annotations


#: Сколько ждём ответа. Подписка — короткий текстовый файл; если сервер
#: молчит десять секунд, он недоступен, а не задумался.
TIMEOUT_S = 10

#: Потолок на размер ответа. Подписка на сотню серверов — это десятки
#: килобайт. Мегабайт означает, что по ссылке лежит не список, и читать
#: его в память целиком незачем.
MAX_BYTES = 1_000_000

#: Заголовок клиента. Часть панелей отдаёт разный формат в зависимости
#: от него и на пустой User-Agent отвечает страницей входа вместо
#: списка.
USER_AGENT = "net67"


class SubscriptionError(RuntimeError):
    """Не удалось получить содержимое подписки."""


def looks_like_subscription_url(text: str) -> bool:
    """Похоже ли на адрес подписки."""
    lowered = str(text or "").strip().lower()
    return lowered.startswith(("http://", "https://"))


def _host_of(url: str) -> str:
    """Имя узла из адреса — для сообщения человеку."""
    try:
        from urllib.parse import urlparse

        return str(urlparse(str(url or "")).hostname or "").strip()
    except Exception:
        return ""


def _explain_network_error(exc: Exception, url: str, timeout: int) -> str:
    """Человеческое объяснение вместо текста исключения requests.

    Подставлять исключение целиком нельзя: человек получал полотно вида

        HTTPSConnectionPool(host='sub.example', port=443): Max retries
        exceeded with url: /XXXX (Caused by ConnectTimeoutError(
        <HTTPSConnection object at 0x19cb18d5e50>, 'Connection to
        sub.example timed out. (connect timeout=10)'))

    Здесь три повтора одного факта, адрес объекта в памяти и ни слова о
    том, что делать. Полезного в нём ровно два слова — «timed out».

    Разбираем по типу, а не по тексту: тексты requests меняются от
    версии к версии и переводу не поддаются.
    """
    host = _host_of(url) or "сервер"

    try:
        import requests
    except Exception:
        return f"не удалось открыть ссылку: {exc}"

    # Таймаут и отказ соединения — самые частые, и у них общая причина:
    # до сервера подписки не достучаться. Обход тут помогает, поэтому о
    # нём и говорим — вместо пересказа стека вызовов.
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return (
            f"{host} не ответил за {timeout} секунд. "
            "Проверьте, что ссылка верна, а если она открывается только "
            "с обходом — включите обход и повторите."
        )
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return f"{host} принял запрос, но не прислал список за {timeout} секунд."
    if isinstance(exc, requests.exceptions.SSLError):
        return f"{host} не прошёл проверку сертификата — соединение может подменяться."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return (
            f"не удалось соединиться с {host}. "
            "Проверьте сеть и адрес подписки; если он заблокирован — включите обход."
        )
    if isinstance(exc, requests.exceptions.TooManyRedirects):
        return f"{host} перенаправляет по кругу — похоже, ссылка ведёт на страницу входа."
    if isinstance(exc, requests.exceptions.MissingSchema):
        return "ссылка на подписку должна начинаться с http:// или https://"

    return f"не удалось открыть ссылку: {exc}"


def fetch_subscription(url: str, *, timeout: int = TIMEOUT_S) -> str:
    """Скачивает содержимое подписки. Возвращает текст как есть.

    Расшифровкой base64 занимается разборщик — здесь только доставка.
    """
    import requests

    address = str(url or "").strip()
    if not looks_like_subscription_url(address):
        raise SubscriptionError("ссылка на подписку должна начинаться с http:// или https://")

    try:
        response = requests.get(
            address,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            stream=True,
            # Мимо системного прокси, всегда.
            #
            # requests по умолчанию читает настройки прокси Windows — те
            # самые, которые мы сами и выставляем при подключении. Выходил
            # круг: чтобы скачать подписку, приложение шло в наше же ядро
            # Xray. А если ядро не поднято, а настройка осталась (скажем,
            # приложение закрыли не по-людски), получалось
            #
            #     SOCKSHTTPSConnectionPool(host=..., port=443):
            #     [WinError 10061] конечный компьютер отверг запрос
            #
            # Подписка — это адрес, который должен открываться напрямую:
            # серверов у нас ещё нет, ходить через них некуда.
            proxies={"http": None, "https": None},
        )
    except Exception as exc:
        raise SubscriptionError(_explain_network_error(exc, address, timeout)) from exc

    try:
        if response.status_code != 200:
            raise SubscriptionError(f"сервер ответил {response.status_code}")

        # Читаем с потолком: до этого места размер ответа неизвестен, а
        # доверять чужому Content-Length незачем.
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(8192):
            if not chunk:
                continue
            size += len(chunk)
            if size > MAX_BYTES:
                raise SubscriptionError("по ссылке слишком много данных — это не список серверов")
            chunks.append(chunk)
    finally:
        try:
            response.close()
        except Exception:
            pass

    if not chunks:
        raise SubscriptionError("по ссылке пусто")

    return b"".join(chunks).decode("utf-8", errors="replace")


def load_subscription(url: str, *, timeout: int = TIMEOUT_S) -> tuple[list, list[str]]:
    """Скачивает и разбирает подписку. Возвращает (профили, ошибки).

    Ошибка загрузки — тоже ошибка в списке, а не исключение: страница
    показывает их одинаково, и разделять два пути ради одного и того же
    сообщения незачем.
    """
    from vpn.links import parse_subscription

    try:
        body = fetch_subscription(url, timeout=timeout)
    except SubscriptionError as exc:
        return ([], [str(exc)])

    return parse_subscription(body)


__all__ = [
    "MAX_BYTES",
    "SubscriptionError",
    "TIMEOUT_S",
    "USER_AGENT",
    "fetch_subscription",
    "load_subscription",
    "looks_like_subscription_url",
]
