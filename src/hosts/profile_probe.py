"""Проверка DNS-профилей сервиса: через какой из них сайт открывается на деле.

У сервиса в каталоге до семи профилей, и какой из них рабочий именно у
этого человека, по каталогу не понять: замер 30.09.2026 шёл из двух
сетей, а у третьей картина своя. Человек перебирал значки вслепую.

Проверка та же, что в том замере. Для пары «адрес профиля — домен
сервиса»: соединение с адресом, TLS с именем домена и настоящей
проверкой сертификата, запрос страницы и поиск слов «недоступно в вашей
стране» в ответе. В hosts при этом ничего не пишется: адрес берётся
напрямую, поэтому проверить можно и не выбранный профиль.

Модуль без Qt и без каталога: сеть и строки каталога приходят снаружи,
чтобы ранжирование проверялось без сети.
"""

from __future__ import annotations

import math
import socket
import ssl
import statistics
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

#: Сколько доменов сервиса проверяется через каждый профиль.
#:
#: Всё подряд проверять нельзя: у ChatGPT в каталоге 445 пар «адрес —
#: домен», у JetBrains больше тысячи. Шесть главных доменов дают ответ
#: за секунды, а профили сравниваются честно — на одних и тех же доменах.
SAMPLE_DOMAINS = 6

#: Сервис с таким числом доменов и меньше проверяется целиком.
#:
#: В hosts пишутся все домены сервиса, а проверялись шесть самых коротких:
#: у Claude из двадцати не попадали ни консоль, ни вход, и профиль с
#: молнией мог не открыть то, ради чего человек пришёл. Двадцать доменов
#: через семь профилей — меньше полуминуты.
FULL_CHECK_MAX_DOMAINS = 20

#: Сколько доменов у большого сервиса (ChatGPT — 445 пар, JetBrains —
#: больше тысячи): главные и домены входа и API, без которых сайт
#: открывается, а войти или работать в нём нельзя.
LARGE_SAMPLE_DOMAINS = 14

#: Первое имя домена, по которому видно вход и API.
_KEY_LABELS = frozenset(
    {"api", "auth", "login", "accounts", "account", "oauth", "sso", "id", "signin", "app", "chat", "web", "www"}
)

CONNECT_TIMEOUT = 4.0
IO_TIMEOUT = 5.0
#: После первых байт ответа ждём продолжение недолго: сервер, который не
#: закрыл соединение сам, иначе держал бы проверку до таймаута.
READ_TAIL_TIMEOUT = 1.2
READ_LIMIT = 65536
MAX_WORKERS = 24
#: Не больше стольких соединений на один адрес сразу: это чужой сервер.
#:
#: У прокси профиля на один адрес приходятся все проверяемые домены
#: сервиса. С четырьмя за раз 14 доменов шли в четыре захода, и проверка
#: Claude тянулась 25 с; с шестью — 20 с (замер 04.10.2026).
PER_IP_PARALLEL = 6

VERDICT_OK = "ok"
VERDICT_REGION = "region"
VERDICT_DEAD = "dead"
VERDICT_RESET = "reset"
VERDICT_BADCERT = "badcert"
VERDICT_NOHTTP = "nohttp"

#: Слова, которыми сервис сам сообщает, что закрыт для страны. Адрес при
#: этом отвечает и сертификат настоящий — но профиль задачу не решает.
REGION_MARKERS = (
    "unsupported_country",
    "unsupported_region",
    "not available in your country",
    "isn't available in your country",
    "not available in your region",
    "is not available in your region",
    "unavailable in your region",
    "not supported in your region",
    "not available in your location",
    "app-unavailable-in-region",
    "unavailable_region",
    "restricted in your region",
    "access denied from your location",
    "sanctioned",
    "your country is not supported",
    "country, region, or territory not supported",
)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class ProfileProbe:
    """Итог одного профиля: сколько доменов открылось и как быстро."""

    profile_id: str
    ok: int
    total: int
    latency_ms: int | None
    #: Почему не открылось (самая частая причина); пусто, если открылось всё.
    reason: str = ""

    @property
    def works(self) -> bool:
        # Половины хватает: среди доменов каталога попадаются служебные,
        # которые и у рабочего профиля отвечают через раз.
        return self.ok > 0 and self.ok * 2 >= self.total


@dataclass(frozen=True, slots=True)
class ServiceProbe:
    """Итог проверки сервиса: профили в порядке каталога и лучший из них."""

    service: str
    profiles: tuple[ProfileProbe, ...]
    best: str | None
    domains: tuple[str, ...] = ()
    #: Сколько всего доменов у сервиса в каталоге: проверено len(domains) из стольких.
    domain_total: int = 0

    @property
    def checked_all(self) -> bool:
        return len(self.domains) >= self.domain_total

    def result_for(self, profile_id: str) -> ProfileProbe | None:
        for item in self.profiles:
            if item.profile_id == profile_id:
                return item
        return None


def pick_sample_domains(domains: Iterable[str], limit: int = SAMPLE_DOMAINS) -> list[str]:
    """Главные домены сервиса — те, что короче: x.ai раньше accounts.x.ai."""
    unique = list(dict.fromkeys(str(domain or "").strip().lower() for domain in domains))
    unique = [domain for domain in unique if domain]
    unique.sort(key=lambda domain: (domain.count("."), len(domain), domain))
    return unique[: max(1, int(limit))]


def pick_probe_domains(domains: Iterable[str]) -> list[str]:
    """Какие домены сервиса проверять: все у небольшого, у большого — выборку.

    Выборка — главные домены (самые короткие), за ними домены входа и API
    (api., auth., login., accounts.…), остаток добирается короткими.
    """
    ordered = pick_sample_domains(domains, limit=1_000_000)
    if len(ordered) <= FULL_CHECK_MAX_DOMAINS:
        return ordered
    main = ordered[:SAMPLE_DOMAINS]
    key = [domain for domain in ordered[SAMPLE_DOMAINS:] if domain.split(".", 1)[0] in _KEY_LABELS]
    rest = [domain for domain in ordered[SAMPLE_DOMAINS:] if domain not in key]
    return (main + key + rest)[:LARGE_SAMPLE_DOMAINS]


def reach_ip(ip: str, *, timeout: float = CONNECT_TIMEOUT) -> bool:
    """Отвечает ли сам адрес на 443 — одно соединение на адрес, а не на пару."""
    try:
        with socket.create_connection((ip, 443), timeout=timeout):
            return True
    except OSError:
        return False


def _read_response(tls) -> bytes:
    data = b""
    deadline = time.monotonic() + IO_TIMEOUT
    while len(data) < READ_LIMIT and time.monotonic() < deadline:
        try:
            chunk = tls.recv(16384)
        except (TimeoutError, OSError):
            break
        if not chunk:
            break
        data += chunk
        tls.settimeout(READ_TAIL_TIMEOUT)
    return data


def probe_pair(ip: str, host: str, *, context: ssl.SSLContext | None = None) -> tuple[str, int | None]:
    """Открывается ли host через адрес ip: (вердикт, время рукопожатия в мс)."""
    context = context or _default_context()
    started = time.perf_counter()
    try:
        sock = socket.create_connection((ip, 443), timeout=CONNECT_TIMEOUT)
    except OSError:
        return VERDICT_DEAD, None
    try:
        sock.settimeout(IO_TIMEOUT)
        try:
            tls = context.wrap_socket(sock, server_hostname=host)
        except ssl.SSLCertVerificationError:
            return VERDICT_BADCERT, None
        except OSError:
            # Сброс, таймаут рукопожатия и прочие ошибки TLS: соединение
            # не доживает до сайта — так выглядит и блокировка по имени.
            return VERDICT_RESET, None
        latency = int((time.perf_counter() - started) * 1000)
        try:
            request = (
                f"GET / HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {_USER_AGENT}\r\n"
                "Accept: */*\r\nConnection: close\r\n\r\n"
            )
            tls.sendall(request.encode("ascii", "ignore"))
            data = _read_response(tls)
        except OSError:
            data = b""
        finally:
            try:
                tls.close()
            except OSError:
                pass
        if not data:
            return VERDICT_NOHTTP, latency
        text = data.decode("utf-8", "replace").lower()
        if any(marker in text for marker in REGION_MARKERS):
            return VERDICT_REGION, latency
        return VERDICT_OK, latency
    finally:
        try:
            sock.close()
        except OSError:
            pass


_context_lock = threading.Lock()
_context: ssl.SSLContext | None = None


def _default_context() -> ssl.SSLContext:
    global _context
    with _context_lock:
        if _context is None:
            context = ssl.create_default_context()
            context.set_alpn_protocols(["http/1.1"])
            _context = context
        return _context


def rank_profiles(results: Iterable[ProfileProbe]) -> str | None:
    """Лучший профиль: больше открывшихся доменов, при равенстве — быстрее."""
    working = [item for item in results if item.works]
    if not working:
        return None
    working.sort(key=lambda item: (-item.ok, item.latency_ms if item.latency_ms is not None else math.inf))
    return working[0].profile_id


def _summarize(profile_id: str, verdicts: dict[str, list[tuple[str, int | None]]], live: set[str]) -> ProfileProbe:
    """Домен открылся, если открылся хоть через один его адрес в профиле."""
    ok = 0
    latencies: list[int] = []
    reasons: list[str] = []
    for domain in live:
        outcomes = verdicts.get(domain) or []
        good = [ms for verdict, ms in outcomes if verdict == VERDICT_OK]
        if good:
            ok += 1
            latencies.extend(ms for ms in good if ms is not None)
        else:
            reasons.extend(verdict for verdict, _ms in outcomes)
    reason = ""
    if ok < len(live):
        reason = statistics.mode(reasons) if reasons else VERDICT_DEAD
    latency = int(statistics.median(latencies)) if latencies else None
    return ProfileProbe(profile_id, ok, len(live), latency, reason)


def probe_service(
    service_name: str,
    profiles: Iterable[str],
    rows_for: Callable[[str], list[tuple[str, str]]],
    *,
    prober: Callable[[str, str], tuple[str, int | None]] = probe_pair,
    reacher: Callable[[str], bool] = reach_ip,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ServiceProbe:
    """Проверяет профили сервиса на одних и тех же главных доменах.

    rows_for(профиль) отдаёт пары (домен, адрес) из каталога. Домен,
    который не открылся ни через один профиль, из счёта выпадает: он
    говорит о самом домене, а не о профилях. Если не открылся ни один —
    счёт остаётся, и рабочего профиля нет.
    """
    profile_ids = [str(profile) for profile in profiles]
    rows = {profile: list(rows_for(profile) or ()) for profile in profile_ids}
    all_domains = pick_sample_domains((domain for items in rows.values() for domain, _ip in items), limit=1_000_000)
    sample = pick_probe_domains(all_domains)
    wanted = set(sample)

    # (профиль, домен, адрес). IPv6 пропускаем: без IPv6 в сети это не отказ
    # профиля, а с ним такие сервисы на плитке и так недоступны.
    tasks: list[tuple[str, str, str]] = []
    for profile in profile_ids:
        for domain, ip in rows[profile]:
            domain = str(domain or "").strip().lower()
            ip = str(ip or "").strip()
            if domain in wanted and ip and ":" not in ip:
                tasks.append((profile, domain, ip))

    def is_cancelled() -> bool:
        return bool(cancelled is not None and cancelled())

    ips = sorted({ip for _profile, _domain, ip in tasks})
    pairs = sorted({(ip, domain) for _profile, domain, ip in tasks})
    total = len(ips) + len(pairs)
    done = 0
    done_lock = threading.Lock()

    def step() -> None:
        nonlocal done
        with done_lock:
            done += 1
            current = done
        if progress is not None:
            progress(current, total)

    alive: dict[str, bool] = {}
    outcomes: dict[tuple[str, str], tuple[str, int | None]] = {}
    per_ip: dict[str, threading.Semaphore] = {ip: threading.Semaphore(PER_IP_PARALLEL) for ip in ips}

    def check_ip(ip: str) -> tuple[str, bool]:
        ok = False if is_cancelled() else bool(reacher(ip))
        step()
        return ip, ok

    def check_pair(pair: tuple[str, str]) -> tuple[tuple[str, str], tuple[str, int | None]]:
        ip, domain = pair
        if is_cancelled() or not alive.get(ip):
            result: tuple[str, int | None] = (VERDICT_DEAD, None)
        else:
            with per_ip[ip]:
                result = prober(ip, domain)
        step()
        return pair, result

    if tasks:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="hosts-probe") as pool:
            for future in as_completed([pool.submit(check_ip, ip) for ip in ips]):
                ip, ok = future.result()
                alive[ip] = ok
            for future in as_completed([pool.submit(check_pair, pair) for pair in pairs]):
                pair, result = future.result()
                outcomes[pair] = result

    by_profile: dict[str, dict[str, list[tuple[str, int | None]]]] = {profile: {} for profile in profile_ids}
    for profile, domain, ip in tasks:
        by_profile[profile].setdefault(domain, []).append(outcomes.get((ip, domain), (VERDICT_DEAD, None)))

    opened = {
        domain
        for verdicts in by_profile.values()
        for domain, items in verdicts.items()
        if any(verdict == VERDICT_OK for verdict, _ms in items)
    }
    live = opened or wanted
    results = tuple(_summarize(profile, by_profile[profile], live) for profile in profile_ids)
    return ServiceProbe(str(service_name), results, rank_profiles(results), tuple(sample), len(all_domains))


__all__ = [
    "REGION_MARKERS",
    "FULL_CHECK_MAX_DOMAINS",
    "LARGE_SAMPLE_DOMAINS",
    "SAMPLE_DOMAINS",
    "VERDICT_BADCERT",
    "VERDICT_DEAD",
    "VERDICT_NOHTTP",
    "VERDICT_OK",
    "VERDICT_REGION",
    "VERDICT_RESET",
    "ProfileProbe",
    "ServiceProbe",
    "pick_probe_domains",
    "pick_sample_domains",
    "probe_pair",
    "probe_service",
    "rank_profiles",
    "reach_ip",
]
