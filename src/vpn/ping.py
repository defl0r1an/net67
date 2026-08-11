"""Проверка отклика VPN-сервера.

Прежняя версия стучалась в сервер по ICMP и TCP. Для WireGuard и
AmneziaWG это проверка не того: сервер слушает UDP и по замыслу молчит в
ответ на всё, кроме корректного рукопожатия. Поэтому исправный сервер
честно получал вердикт «не ответил ни на ICMP, ни на TCP» — сообщение,
из которого нельзя сделать ни одного вывода.

Сейчас порядок другой и идёт от надёжности признака:

1. Если туннель поднят и рукопожатие состоялось — сервер отвечает, это
   доказано криптографически. Никакие внешние пробы точнее не будут.
2. Если туннель поднят, но рукопожатия нет — говорим об этом прямо и
   показываем, сколько ушло и сколько пришло. tx > 0 при rx = 0 означает,
   что наши пакеты уходят, а ответа нет.
3. Туннель не поднят — пробуем UDP-пробу по порту сервера. Она не
   подтверждает работу WireGuard, но отличает «хост недоступен» от
   «хост есть, порт молчит», а это разные проблемы.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass


#: Сколько ждать ответа на UDP-пробу. Больше нет смысла: рабочий сервер
#: всё равно не ответит, а недоступный хост даст ошибку сразу.
UDP_PROBE_TIMEOUT = 2.0


@dataclass(frozen=True, slots=True)
class PingResult:
    ok: bool
    latency_ms: float | None
    method: str
    message: str


def _icmp_ping(host: str, *, timeout: float) -> PingResult | None:
    """ICMP через Windows API. None — не ответил или проверка недоступна."""
    try:
        from utils.windows_icmp import ping_ipv4_host_winapi
    except Exception:
        return None

    try:
        result = ping_ipv4_host_winapi(host, count=3, timeout_ms=int(timeout * 1000))
    except Exception:
        return None

    if getattr(result, "ok", False) and getattr(result, "average_ms", None) is not None:
        latency = float(result.average_ms)
        return PingResult(
            ok=True,
            latency_ms=latency,
            method="icmp",
            message=f"Сервер отвечает на ping, задержка {latency:.0f} мс",
        )

    return None


def _udp_probe(host: str, port: int, *, timeout: float) -> PingResult:
    """Отправляет датаграмму в порт сервера и смотрит на реакцию.

    Три различимых исхода:

    * ConnectionResetError — Windows получила ICMP «порт недоступен».
      Хост жив и достижим, но на этом порту никто не слушает.
    * Тишина — обычное поведение работающего WireGuard: он молчит в ответ
      на мусор. Это же выглядит и как блокировка UDP файрволом, поэтому
      утверждать ничего нельзя.
    * OSError — маршрута нет, имя не разрешилось, порт закрыт локально.
    """
    started = time.monotonic()
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.connect((host, int(port)))
        # Содержимое намеренно произвольное: собрать настоящее рукопожатие
        # WireGuard без ключей нельзя, а AmneziaWG вдобавок ждёт свою
        # обфускацию. Проба отвечает на вопрос о достижимости, не о
        # работоспособности VPN.
        sock.send(b"\x00" * 32)
        sock.recv(1024)
    except ConnectionResetError:
        elapsed = (time.monotonic() - started) * 1000
        return PingResult(
            ok=False,
            latency_ms=elapsed,
            method="udp",
            message=(
                f"Хост доступен ({elapsed:.0f} мс), но UDP-порт {port} закрыт. "
                "Проверьте порт в профиле."
            ),
        )
    except socket.timeout:
        return PingResult(
            ok=True,
            latency_ms=None,
            method="udp",
            message=(
                f"Хост принял датаграмму на UDP-порт {port} и промолчал. "
                "Так и ведёт себя рабочий WireGuard — он отвечает только на "
                "настоящее рукопожатие. Подключитесь, чтобы проверить наверняка."
            ),
        )
    except OSError as exc:
        return PingResult(
            ok=False,
            latency_ms=None,
            method="udp",
            message=f"Сервер недоступен: {exc}",
        )
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    elapsed = (time.monotonic() - started) * 1000
    return PingResult(
        ok=True,
        latency_ms=elapsed,
        method="udp",
        message=f"Сервер ответил на UDP-пробу, задержка {elapsed:.0f} мс",
    )


def check_tunnel_stats(stats) -> PingResult | None:
    """Вердикт по статистике живого туннеля. None — судить не по чему."""
    if stats is None:
        return None

    from vpn.status import format_bytes, format_handshake

    rx = int(getattr(stats, "rx_bytes", 0) or 0)
    tx = int(getattr(stats, "tx_bytes", 0) or 0)
    last_handshake = int(getattr(stats, "last_handshake", 0) or 0)
    traffic = f"принято {format_bytes(rx)}, отправлено {format_bytes(tx)}"

    if last_handshake > 0:
        return PingResult(
            ok=True,
            latency_ms=None,
            method="handshake",
            message=(
                f"Сервер отвечает: рукопожатие {format_handshake(last_handshake)}, "
                f"{traffic}"
            ),
        )

    if tx > 0:
        return PingResult(
            ok=False,
            latency_ms=None,
            method="handshake",
            message=(
                f"Рукопожатия не было: {traffic}. Запросы уходят, ответа нет — "
                "порт UDP закрыт по дороге, ключ устарел или мешает обход DPI. "
                "Попробуйте остановить обход и подключиться снова."
            ),
        )

    return PingResult(
        ok=False,
        latency_ms=None,
        method="handshake",
        message=f"Туннель поднят, но обмена нет: {traffic}",
    )


def check_server(
    host: str,
    port: int = 0,
    *,
    timeout: float = 3.0,
    stats=None,
) -> PingResult:
    """Проверяет доступность сервера профиля.

    stats — статистика поднятого туннеля, если он есть. Она сильнее любой
    внешней пробы: состоявшееся рукопожатие означает, что сервер ответил.
    """
    from_tunnel = check_tunnel_stats(stats)
    if from_tunnel is not None and from_tunnel.ok:
        return from_tunnel

    host = str(host or "").strip()
    if not host:
        return from_tunnel or PingResult(False, None, "none", "Адрес сервера не указан")

    icmp = _icmp_ping(host, timeout=timeout)
    if icmp is not None:
        if from_tunnel is not None:
            return PingResult(
                ok=False,
                latency_ms=icmp.latency_ms,
                method="icmp",
                message=f"{icmp.message}, но {from_tunnel.message[0].lower()}{from_tunnel.message[1:]}",
            )
        return icmp

    if not port:
        return from_tunnel or PingResult(
            ok=False,
            latency_ms=None,
            method="none",
            message="Сервер не отвечает на ping, а порт для UDP-пробы не указан",
        )

    udp = _udp_probe(host, int(port), timeout=min(timeout, UDP_PROBE_TIMEOUT))
    if from_tunnel is not None and not from_tunnel.ok:
        return PingResult(
            ok=False,
            latency_ms=udp.latency_ms,
            method=udp.method,
            message=f"{from_tunnel.message} Проба порта: {udp.message[0].lower()}{udp.message[1:]}",
        )
    return udp


#: Сколько ждём отклика TCP-порта. Больше секунды ждать незачем: живой
#: сервер за океаном отвечает за две-три сотни миллисекунд.
TCP_PROBE_TIMEOUT = 2.0


def tcp_probe(host: str, port: int, *, timeout: float = TCP_PROBE_TIMEOUT) -> PingResult:
    """Открывает соединение и меряет время до отклика.

    Для серверов из ссылки это единственная честная проверка. ICMP на
    них обычно закрыт, а UDP-проба на порт 443 отвечала «хост принял
    датаграмму и промолчал» — верно и бесполезно: на этом порту говорят
    по TCP, датаграмму там никто и не ждал.

    Успешное соединение означает: адрес верный, порт открыт, сервер
    отвечает. Это ровно то, что человек хочет знать, нажимая «Проверить
    сервер».
    """
    import socket
    import time

    address = str(host or "").strip()
    if not address:
        return PingResult(False, None, "tcp", "Адрес сервера не указан")
    if not port:
        return PingResult(False, None, "tcp", "Порт сервера не указан")

    started = time.perf_counter()
    try:
        with socket.create_connection((address, int(port)), timeout=timeout):
            latency = (time.perf_counter() - started) * 1000.0
    except socket.timeout:
        return PingResult(False, None, "tcp", f"Сервер не ответил за {timeout:.0f} с")
    except OSError as exc:
        return PingResult(False, None, "tcp", f"Соединение не открылось: {exc}")

    return PingResult(True, latency, "tcp", "Сервер отвечает")


def format_latency(result: PingResult) -> str:
    """Короткая подпись для интерфейса."""
    if result.latency_ms is not None:
        return f"{result.latency_ms:.0f} мс"
    if result.ok:
        return "отвечает"
    return "—"


__all__ = [
    "TCP_PROBE_TIMEOUT",
    "UDP_PROBE_TIMEOUT",
    "tcp_probe",
    "PingResult",
    "check_server",
    "check_tunnel_stats",
    "format_latency",
]
