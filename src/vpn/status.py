"""Разбор состояния туннеля из вывода `awg show <имя> dump`.

Формат сверен с исходниками amneziawg-tools (src/show.c, dump_print).

Строка пира — восемь полей, разделённых табуляцией, и совпадает с обычным
WireGuard::

    public-key  preshared-key  endpoint  allowed-ips
    last-handshake  rx-bytes  tx-bytes  persistent-keepalive

А вот первая строка, описывающая устройство, у AmneziaWG сильно шире
обычной: кроме ключей и порта в неё попадают параметры обфускации
(junk_packet_count, магические заголовки, i1..i5 и прочее). Поэтому
разбирать по номеру поля в строке устройства нельзя — количество полей
меняется от версии к версии. Опираемся только на строки пиров и находим
их по числу полей.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

#: Число полей в строке пира. См. dump_print в src/show.c.
PEER_FIELD_COUNT = 8


@dataclass(frozen=True, slots=True)
class TunnelStats:
    endpoint: str = ""
    last_handshake: int = 0
    rx_bytes: int = 0
    tx_bytes: int = 0
    keepalive: str = ""

    @property
    def has_handshake(self) -> bool:
        return self.last_handshake > 0


def _to_int(value: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def parse_dump(text: str) -> TunnelStats | None:
    """Возвращает статистику первого пира или None, если её нет."""
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        fields = line.rstrip("\n").split("\t")
        # Строку устройства отличаем по числу полей: у пира их ровно
        # восемь, у устройства заметно больше.
        if len(fields) != PEER_FIELD_COUNT:
            continue

        endpoint = fields[2].strip()
        return TunnelStats(
            endpoint="" if endpoint in ("(none)", "") else endpoint,
            last_handshake=_to_int(fields[4]),
            rx_bytes=_to_int(fields[5]),
            tx_bytes=_to_int(fields[6]),
            keepalive=fields[7].strip(),
        )

    return None


def format_bytes(value: int) -> str:
    size = float(max(0, int(value)))
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ГБ"


def format_handshake(last_handshake: int, *, now: float | None = None) -> str:
    """Человеческое «сколько прошло с рукопожатия».

    Рукопожатие — единственный надёжный признак живого туннеля: адаптер
    может существовать, а обмена не быть.
    """
    if last_handshake <= 0:
        return "рукопожатия ещё не было"

    current = time.time() if now is None else float(now)
    delta = int(current - last_handshake)
    if delta < 0:
        return "только что"
    if delta < 60:
        return f"{delta} сек назад"
    if delta < 3600:
        return f"{delta // 60} мин назад"
    return f"{delta // 3600} ч назад"


def describe(stats: TunnelStats | None, *, now: float | None = None) -> str:
    """Строка для интерфейса."""
    if stats is None:
        return "Нет данных о туннеле"

    parts = [f"Рукопожатие: {format_handshake(stats.last_handshake, now=now)}"]
    parts.append(f"Принято {format_bytes(stats.rx_bytes)}, отправлено {format_bytes(stats.tx_bytes)}")
    if stats.endpoint:
        parts.append(f"Сервер: {stats.endpoint}")
    return " · ".join(parts)


__all__ = [
    "PEER_FIELD_COUNT",
    "TunnelStats",
    "describe",
    "format_bytes",
    "format_handshake",
    "parse_dump",
]
