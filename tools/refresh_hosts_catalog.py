# tools/refresh_hosts_catalog.py
"""Пересчёт каталога hosts: заново спрашивает адреса у DNS-резолверов.

## Зачем

IP-адреса в `json/hosts_catalog/` — не рукописный список, а ответы
«разблокирующих» DNS-резолверов. Сайты переезжают, резолверы меняют
подставные адреса, и через полгода половина записей ведёт в никуда.
Причём молча: строка в hosts есть, домен «разрешается», а сайт не
открывается.

Скрипт спрашивает те же резолверы заново и обновляет каталог.

## Как спрашивает

Обычным DNS-запросом по UDP, безо всяких библиотек. Это осознанно:
резолверы всё равно заданы адресами, ставить `dnspython` ради двух
типов записей незачем, а свой разбор ответа занимает полсотни строк и
проверяется тестами.

## Чего не делает

Не выдумывает адреса. Источник без резолвера (таких четыре — их адреса
нигде не записаны, в каталоге лежат только ответы) пропускается, и
прежние значения остаются нетронутыми. Стереть их было бы хуже, чем
оставить устаревшими: пустая запись ломает профиль целиком, устаревшая
— только один домен.

Не пишет ничего без спроса: по умолчанию сухой прогон с отчётом.

## Как пользоваться

    python tools/refresh_hosts_catalog.py --check        проверить резолверы
    python tools/refresh_hosts_catalog.py                посмотреть, что изменится
    python tools/refresh_hosts_catalog.py --write        применить
    python tools/refresh_hosts_catalog.py --only xbox_dns --service claude
"""

from __future__ import annotations

import argparse
import json
import random
import socket
import struct
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = PROJECT_ROOT / "json" / "hosts_catalog"
RESOLVERS_FILE = Path(__file__).resolve().parent / "hosts_catalog_resolvers.json"

#: Типы записей. Больше нам не нужно: в каталоге лежат только адреса.
TYPE_A = 1
TYPE_AAAA = 28

#: Сколько ждём ответа. Разблокирующие резолверы стоят не в соседней
#: стойке, но и две секунды молчания — это уже «не отвечает».
TIMEOUT_SECONDS = 2.0

#: Сколько раз переспросить. UDP теряет пакеты, и один потерянный не
#: повод объявлять домен исчезнувшим.
ATTEMPTS = 2

#: Сколько доменов спрашиваем разом. Резолверы чужие, и устраивать им
#: сотню одновременных запросов невежливо — забанят по адресу.
PARALLEL = 8


# ──────────────────────────────────────────────────────────────────────
# DNS по UDP
# ──────────────────────────────────────────────────────────────────────


class DnsError(Exception):
    """Ответ получен, но пользоваться им нельзя."""


def encode_name(name: str) -> bytes:
    """Имя в формате DNS: длина куска, кусок, ... , ноль."""
    # Пробелы срезаем у каждого куска, а не только по краям имени:
    # «  » прошло бы дальше как годный кусок длиной три и ушло в запрос.
    parts = [part.strip() for part in str(name or "").strip().strip(".").split(".")]
    parts = [part for part in parts if part]
    if not parts:
        raise DnsError("пустое имя")

    chunks = []
    for part in parts:
        raw = part.encode("idna") if not part.isascii() else part.encode("ascii")
        if not 1 <= len(raw) <= 63:
            raise DnsError(f"кусок имени негодной длины: {part!r}")
        chunks.append(bytes([len(raw)]) + raw)
    return b"".join(chunks) + b"\x00"


def build_query(name: str, qtype: int, *, txid: int | None = None) -> tuple[int, bytes]:
    """Собирает запрос. Возвращает (номер запроса, пакет)."""
    if txid is None:
        txid = random.randint(0, 0xFFFF)
    # 0x0100 — «прошу рекурсию». Без неё резолвер вернёт отсылку к
    # корневым серверам вместо ответа.
    header = struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0)
    question = encode_name(name) + struct.pack(">HH", qtype, 1)
    return txid, header + question


def skip_name(data: bytes, offset: int) -> int:
    """Перешагивает имя, не разбирая его.

    Имена в ответе бывают сжатыми: вместо повтора ставится ссылка на
    более раннее место пакета. Ссылку узнаём по двум старшим битам —
    она занимает ровно два байта, и на этом имя кончается.
    """
    while True:
        if offset >= len(data):
            raise DnsError("ответ обрывается посреди имени")
        length = data[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            return offset + 2
        offset += 1 + length


def parse_addresses(data: bytes, *, txid: int | None = None) -> list[str]:
    """Достаёт адреса из ответа. Чужие записи пропускает."""
    if len(data) < 12:
        raise DnsError("ответ короче заголовка")

    answer_id, flags, questions, answers, _authority, _extra = struct.unpack(
        ">HHHHHH", data[:12]
    )
    if txid is not None and answer_id != txid:
        # Чужой ответ на наш порт. Принимать его нельзя: так подсовывают
        # подложные адреса.
        raise DnsError("номер ответа не совпал с запросом")

    rcode = flags & 0x0F
    if rcode == 3:
        return []  # такого имени нет — это ответ, а не сбой
    if rcode != 0:
        raise DnsError(f"резолвер ответил кодом {rcode}")

    offset = 12
    for _ in range(questions):
        offset = skip_name(data, offset) + 4

    found: list[str] = []
    for _ in range(answers):
        offset = skip_name(data, offset)
        if offset + 10 > len(data):
            raise DnsError("ответ обрывается посреди записи")
        rtype, _rclass, _ttl, rdlength = struct.unpack(">HHIH", data[offset : offset + 10])
        offset += 10
        rdata = data[offset : offset + rdlength]
        offset += rdlength

        if rtype == TYPE_A and rdlength == 4:
            found.append(socket.inet_ntop(socket.AF_INET, rdata))
        elif rtype == TYPE_AAAA and rdlength == 16:
            found.append(socket.inet_ntop(socket.AF_INET6, rdata))
        # CNAME и прочее пропускаем: нам нужен адрес, а не цепочка имён.

    return found


def resolve_over_https(name: str, qtype: int, url: str, *, timeout=TIMEOUT_SECONDS) -> list[str]:
    """Тот же запрос, но по HTTPS.

    Нужен там, где до резолвера не достучаться по UDP: пятьдесят третий
    порт режут и провайдеры, и корпоративные сети, и сам резолвер может
    держать только HTTPS. Пакет ровно тот же, меняется только дорога.

    Номер запроса ставим нулевой — так велит RFC 8484: по HTTPS запросы
    кэшируются, и случайный номер сделал бы каждый из них уникальным.
    """
    try:
        import requests
    except ImportError as exc:
        raise DnsError(f"нет библиотеки requests: {exc}") from exc

    _txid, packet = build_query(name, qtype, txid=0)
    try:
        response = requests.post(
            url,
            data=packet,
            headers={
                "content-type": "application/dns-message",
                "accept": "application/dns-message",
            },
            timeout=timeout,
        )
        response.raise_for_status()
    except Exception as exc:
        raise DnsError(str(exc)[:160]) from exc

    return parse_addresses(response.content, txid=0)


def resolve_over_udp(name: str, qtype: int, servers, *, timeout=TIMEOUT_SECONDS) -> list[str]:
    """Спрашивает резолверы по порядку до первого внятного ответа."""
    last_error = None
    for server in servers or ():
        for _ in range(ATTEMPTS):
            try:
                txid, packet = build_query(name, qtype)
                family = socket.AF_INET6 if ":" in str(server) else socket.AF_INET
                with socket.socket(family, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(timeout)
                    sock.sendto(packet, (str(server), 53))
                    data, _ = sock.recvfrom(4096)
                return parse_addresses(data, txid=txid)
            except Exception as exc:
                last_error = exc
                continue

    if last_error is not None:
        raise DnsError(str(last_error))
    raise DnsError("не задано ни одного резолвера")


def resolve(name: str, qtype: int, source, *, timeout=TIMEOUT_SECONDS) -> list[str]:
    """Спрашивает источник тем способом, который у него есть.

    `source` — либо запись из настроек, либо просто список адресов.

    HTTPS пробуется первым, когда задан. Не из любви к новизне: UDP
    молчит по таймауту, и каждый недоступный домен обходится в восемь
    секунд ожидания на пустом месте.
    """
    if isinstance(source, dict):
        servers = source.get("servers") or ()
        doh = str(source.get("doh") or "").strip()
    else:
        servers, doh = source, ""

    errors = []
    if doh:
        try:
            return resolve_over_https(name, qtype, doh, timeout=timeout)
        except DnsError as exc:
            errors.append(f"https: {exc}")

    try:
        return resolve_over_udp(name, qtype, servers, timeout=timeout)
    except DnsError as exc:
        errors.append(f"udp: {exc}")

    raise DnsError(f"{name}: " + "; ".join(errors))


# ──────────────────────────────────────────────────────────────────────
# Каталог
# ──────────────────────────────────────────────────────────────────────


@dataclass
class Change:
    file: str
    host: str
    source: str
    was: str
    now: str


@dataclass
class Report:
    changed: list[Change] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    skipped_sources: list[str] = field(default_factory=list)
    checked_hosts: int = 0

    def summary(self) -> str:
        lines = [
            f"Проверено доменов: {self.checked_hosts}",
            f"Изменилось адресов: {len(self.changed)}",
        ]
        if self.unresolved:
            lines.append(f"Не разрешилось: {len(self.unresolved)}")
        if self.skipped_sources:
            lines.append("Пропущены источники без резолвера: " + ", ".join(self.skipped_sources))
        return "\n".join(lines)


def _has_transport(source: dict) -> bool:
    """Есть ли чем спросить этот источник — хоть по UDP, хоть по HTTPS."""
    return bool(source.get("servers") or str(source.get("doh") or "").strip())


def load_resolvers() -> dict:
    return json.loads(RESOLVERS_FILE.read_text(encoding="utf-8"))


def catalog_files(kind: str) -> list[Path]:
    folder = CATALOG_ROOT / kind
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def refresh_dns_file(path: Path, sources: dict, report: Report, *, only: str = "") -> dict:
    """Пересчитывает файл из папки dns/ — тот, где адрес свой на источник."""
    data = json.loads(path.read_text(encoding="utf-8"))
    domains = data.get("domains") or []

    active = {
        key: value
        for key, value in sources.items()
        if _has_transport(value) and (not only or key == only)
    }
    if not active:
        return data

    jobs = []
    for entry in domains:
        host = str(entry.get("host") or "").strip()
        if not host:
            continue
        report.checked_hosts += 1
        for key in active:
            jobs.append((entry, host, key))

    def _one(job):
        entry, host, key = job
        try:
            addresses = resolve(host, TYPE_A, active[key])
        except DnsError as exc:
            return (entry, host, key, None, str(exc))
        return (entry, host, key, addresses[0] if addresses else None, "")

    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        for entry, host, key, address, error in pool.map(_one, jobs):
            if address is None:
                report.unresolved.append(f"{path.name}: {host} через {key} — {error or 'пусто'}")
                continue
            ips = entry.setdefault("ips", {})
            was = str(ips.get(key) or "")
            if was != address:
                report.changed.append(Change(path.name, host, key, was or "—", address))
                ips[key] = address

    return data


def refresh_hosts_file(path: Path, servers, report: Report) -> dict:
    """Пересчитывает файл из папки hosts/ — там простые адреса сайтов."""
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("hosts") or []

    # В этих файлах у одного домена бывает несколько строк — под IPv4 и
    # под несколько IPv6. Собираем домены, спрашиваем каждый один раз и
    # пересобираем список целиком, иначе лишние адреса останутся жить.
    names = []
    for entry in entries:
        host = str(entry.get("host") or "").strip()
        if host and host not in names:
            names.append(host)

    report.checked_hosts += len(names)

    def _one(host):
        found = []
        for qtype in (TYPE_A, TYPE_AAAA):
            try:
                found.extend(resolve(host, qtype, servers))
            except DnsError:
                continue
        return host, found

    resolved: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        for host, found in pool.map(_one, names):
            if found:
                resolved[host] = found
            else:
                report.unresolved.append(f"{path.name}: {host} — пусто")

    if not resolved:
        return data

    was_pairs = {(str(e.get("host") or ""), str(e.get("ip") or "")) for e in entries}
    rebuilt = []
    for host in names:
        if host not in resolved:
            # Домен не ответил — оставляем как было. Выбросить его
            # значило бы сломать профиль из-за одного таймаута.
            rebuilt.extend(e for e in entries if str(e.get("host") or "") == host)
            continue
        for address in resolved[host]:
            rebuilt.append({"ip": address, "host": host})
            if (host, address) not in was_pairs:
                report.changed.append(Change(path.name, host, "hosts", "—", address))

    data["hosts"] = rebuilt
    return data


def check_resolvers(sources: dict) -> int:
    """Спрашивает у каждого резолвера один и тот же домен."""
    probe = "example.com"
    problems = 0
    for key, value in sources.items():
        title = value.get("name") or key
        if not _has_transport(value):
            print(f"  —  {title:24} адрес резолвера не задан, источник будет пропущен")
            continue

        # Пробуем оба пути порознь: важно знать не только «отвечает или
        # нет», но и каким путём. Живой HTTPS при мёртвом UDP — рабочее
        # положение дел, и пугать им не надо.
        for label, call in (
            ("https", lambda: resolve_over_https(probe, TYPE_A, str(value.get("doh") or ""))),
            ("udp  ", lambda: resolve_over_udp(probe, TYPE_A, value.get("servers") or [])),
        ):
            if label.strip() == "https" and not str(value.get("doh") or "").strip():
                continue
            if label.strip() == "udp" and not (value.get("servers") or []):
                continue
            try:
                addresses = call()
                if addresses:
                    print(f"  ok {title:24} {label} → {addresses[0]}")
                else:
                    print(f"  !! {title:24} {label} — пустой ответ")
                    problems += 1
            except DnsError as exc:
                print(f"  !! {title:24} {label} — {exc}")
                problems += 1
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Пересчёт каталога hosts по DNS.")
    parser.add_argument("--write", action="store_true", help="записать изменения в каталог")
    parser.add_argument("--check", action="store_true", help="только проверить резолверы")
    parser.add_argument("--only", default="", help="один источник, например xbox_dns")
    parser.add_argument("--service", default="", help="подстрока в имени файла профиля")
    args = parser.parse_args(argv)

    config = load_resolvers()
    sources = config.get("sources") or {}

    if args.check:
        print("Резолверы:")
        return 1 if check_resolvers(sources) else 0

    if not CATALOG_ROOT.is_dir():
        print(f"Каталог не найден: {CATALOG_ROOT}", file=sys.stderr)
        return 2

    report = Report()
    report.skipped_sources = [
        value.get("name") or key for key, value in sources.items() if not _has_transport(value)
    ]

    updated: list[tuple[Path, dict]] = []

    for path in catalog_files("dns"):
        if args.service and args.service.lower() not in path.name.lower():
            continue
        updated.append((path, refresh_dns_file(path, sources, report, only=args.only)))

    if not args.only:
        servers = (config.get("hosts_profiles_resolver") or {}).get("servers") or []
        for path in catalog_files("hosts"):
            if args.service and args.service.lower() not in path.name.lower():
                continue
            updated.append((path, refresh_hosts_file(path, servers, report)))

    print(report.summary())

    if report.changed:
        print("\nИзменения:")
        for change in report.changed[:60]:
            print(f"  {change.file}: {change.host} [{change.source}] {change.was} → {change.now}")
        if len(report.changed) > 60:
            print(f"  ... и ещё {len(report.changed) - 60}")

    if report.unresolved:
        print("\nНе разрешилось:")
        for line in report.unresolved[:20]:
            print(f"  {line}")
        if len(report.unresolved) > 20:
            print(f"  ... и ещё {len(report.unresolved) - 20}")

    if not args.write:
        print("\nСухой прогон. Чтобы записать — запустите с --write")
        return 0

    if not report.changed:
        print("\nПисать нечего: всё совпало.")
        return 0

    for path, data in updated:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"\nЗаписано файлов: {len(updated)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
