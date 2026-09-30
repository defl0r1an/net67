"""Прямой DNS-запрос по UDP к серверам системы — в обход DNS-клиента Windows.

Зачем
-----
DNS-клиент Windows опрашивает серверы в своём порядке и привязывает запрос
к адаптеру, которому сервер принадлежит. Если первыми в списке стоят серверы
неработающего VPN-адаптера (на машине владельца — Radmin VPN с 1.1.1.1 и
9.9.9.9), каждое имя, которого нет в кэше, резолвится двенадцать секунд:
столько клиент ждёт ответа через мёртвый туннель, прежде чем спросить роутер.
Роутер при этом отвечает за 7 мс, тот же 1.1.1.1 по обычному маршруту — за
20 мс. Браузер почти не замечает беды: популярные имена лежат в кэше. А
подбор стратегии с дедлайном 4 с писал «Нет интернета» — и человек искал
поломку не там.

Здесь запрос уходит без привязки к адаптеру, по таблице маршрутов, — так
работает собственный резолвер Chrome. Файл hosts не читается: к этому пути
обращаются, только когда getaddrinfo не уложился в срок, а имя из hosts он
отдаёт мгновенно.
"""

from __future__ import annotations

import random
import select
import socket
import struct
import time
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["DirectAnswer", "build_a_query", "parse_a_answers", "query_a"]

_TYPE_A = 1
_CLASS_IN = 1


@dataclass(frozen=True, slots=True)
class DirectAnswer:
    ips: tuple[str, ...] = ()
    server: str = ""
    elapsed_ms: float = 0.0


def build_a_query(name: str, txid: int) -> bytes:
    """Запрос A-записи с рекурсией, как у любого резолвера."""
    header = struct.pack(">HHHHHH", txid & 0xFFFF, 0x0100, 1, 0, 0, 0)
    labels = [part for part in str(name).strip().rstrip(".").split(".") if part]
    qname = b"".join(bytes([len(label)]) + label.encode("idna") for label in labels) + b"\0"
    return header + qname + struct.pack(">HH", _TYPE_A, _CLASS_IN)


def _skip_name(data: bytes, offset: int) -> int:
    """Смещение сразу за именем (с учётом сжатия ссылками)."""
    while True:
        if offset >= len(data):
            raise ValueError("имя обрывается")
        length = data[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            return offset + 2
        offset += 1 + length


def parse_a_answers(data: bytes, txid: int) -> tuple[str, ...]:
    """IPv4 из ответа. Пусто — чужой ответ, ошибка сервера или нет записей."""
    if len(data) < 12:
        return ()
    rid, flags, qdcount, ancount, _ns, _ar = struct.unpack(">HHHHHH", data[:12])
    if rid != (txid & 0xFFFF) or not flags & 0x8000 or flags & 0x000F:
        return ()
    offset = 12
    try:
        for _ in range(qdcount):
            offset = _skip_name(data, offset) + 4
        ips: list[str] = []
        for _ in range(ancount):
            offset = _skip_name(data, offset)
            rtype, rclass, _ttl, rdlength = struct.unpack(">HHIH", data[offset : offset + 10])
            offset += 10
            rdata = data[offset : offset + rdlength]
            offset += rdlength
            # CNAME в цепочке пропускаем: рекурсивный сервер сам кладёт за
            # ним A-записи конечного имени.
            if rtype == _TYPE_A and rclass == _CLASS_IN and rdlength == 4:
                ip = socket.inet_ntoa(rdata)
                if ip not in ips:
                    ips.append(ip)
    except (ValueError, struct.error, OSError):
        return ()
    return tuple(ips)


def query_a(name: str, servers: Sequence[str], *, timeout: float = 2.0, port: int = 53) -> DirectAnswer:
    """Спрашивает A-запись у всех серверов сразу, берёт первый ответ с адресами.

    Никогда не бросает исключений: пустой ответ значит «не вышло».
    """
    targets = [str(server).strip() for server in servers if str(server).strip()]
    if not targets or not str(name or "").strip():
        return DirectAnswer()
    started = time.perf_counter()
    txid = random.randint(0, 0xFFFF)
    try:
        packet = build_a_query(name, txid)
    except (UnicodeError, ValueError):
        return DirectAnswer()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setblocking(False)
        sent = 0
        for server in targets:
            try:
                sock.sendto(packet, (server, int(port)))
                sent += 1
            except OSError:
                continue
        if not sent:
            return DirectAnswer()
        deadline = started + max(0.05, float(timeout))
        while True:
            left = deadline - time.perf_counter()
            if left <= 0:
                return DirectAnswer(elapsed_ms=(time.perf_counter() - started) * 1000)
            readable, _w, _x = select.select([sock], [], [], left)
            if not readable:
                continue
            try:
                data, peer = sock.recvfrom(4096)
            except OSError:
                continue
            if peer[0] not in targets:
                continue
            ips = parse_a_answers(data, txid)
            if ips:
                return DirectAnswer(ips=ips, server=peer[0], elapsed_ms=(time.perf_counter() - started) * 1000)
    finally:
        sock.close()
