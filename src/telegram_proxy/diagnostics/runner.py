from __future__ import annotations

import concurrent.futures
import socket
import ssl
import time
from base64 import b64encode
from collections.abc import Callable
from os import urandom

from log.log import log
from settings.mode import ENGINE_WINWS2
import telegram_proxy.config.settings as telegram_proxy_settings
from utils.windows_process_probe import iter_process_records_winapi

DC_TARGETS = [
    ("149.154.167.220", "WSS relay", "—"),
    ("149.154.167.50", "DC2", "kws2"),
    ("149.154.167.41", "DC2", "kws2"),
    ("149.154.167.91", "DC4", "kws4"),
    ("149.154.175.53", "DC1", "—"),
    ("149.154.175.55", "DC1", "—"),
    ("149.154.175.100", "DC3 (→DC1)", "—"),
    ("91.108.56.134", "DC5", "—"),
    ("91.108.56.149", "DC5", "—"),
    ("91.105.192.100", "DC203 CDN", "—"),
    ("149.154.167.151", "DC2 media", "—"),
    ("149.154.167.222", "DC2 media", "—"),
    ("149.154.175.52", "DC1 media", "—"),
    ("91.108.56.102", "DC5 media", "—"),
    ("149.154.175.102", "DC3 media", "—"),
    ("149.154.164.250", "DC4 media", "—"),
]

WSS_PROBE_TARGETS = [
    ("149.154.167.220", "kws1.web.telegram.org", 1),
    ("149.154.167.220", "kws2.web.telegram.org", 2),
    ("149.154.167.220", "kws3.web.telegram.org", 3),
    ("149.154.167.220", "kws4.web.telegram.org", 4),
    ("149.154.167.220", "kws5.web.telegram.org", 5),
    ("149.154.167.220", "zws2.web.telegram.org", 2),
    ("149.154.167.220", "zws4.web.telegram.org", 4),
]

def run_all(
    proxy_port: int,
    *,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    from telegram_proxy.wss_proxy import check_relay_reachable

    t0 = time.time()
    results: list[str] = []

    def publish() -> None:
        if progress_callback is not None:
            try:
                progress_callback("\n".join(results))
            except Exception:
                pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        dc_futures = {
            executor.submit(_test_single_ip, ip, dc, wss): (ip, dc)
            for ip, dc, wss in DC_TARGETS
        }
        wss_futures = [
            executor.submit(_test_wss_relay, ip, domain, dc)
            for ip, domain, dc in WSS_PROBE_TARGETS
        ]

        relay_future = executor.submit(check_relay_reachable, timeout=5.0)
        dns_relay_future = executor.submit(
            check_relay_reachable,
            relay_ip="149.154.167.99",
            timeout=5.0,
        )

        sni_future = executor.submit(_test_sni_vs_ip)
        http_future = executor.submit(_test_http_port80)
        proxy_future = executor.submit(_test_proxy_liveness, "127.0.0.1", proxy_port)
        winws_future = executor.submit(_check_winws2_running)

        upstream_state = _load_upstream_state()

        upstream_future = None
        upstream_target = telegram_proxy_settings.load_upstream_test_target()
        if upstream_target is not None:
            upstream_future = executor.submit(_test_upstream_proxy, *upstream_target)

        relay_result = relay_future.result()
        results.extend(
            [
                "=" * 76,
                "  ДОСТУПНОСТЬ WSS RELAY",
                "=" * 76,
                "  149.154.167.220:443 (web.telegram.org)",
            ]
        )
        if relay_result["reachable"]:
            results.append(f"  TCP+TLS: OK ({relay_result['ms']:.0f}ms)")
        else:
            results.append(f"  TCP+TLS: TIMEOUT ({relay_result['ms']:.0f}ms) <- ЗАБЛОКИРОВАН")
            results.append("  ! WSS relay недоступен — прокси не сможет проксировать через WSS.")
            try:
                zapret_running = winws_future.result(timeout=0.1)
            except Exception:
                zapret_running = None
            if zapret_running is not None:
                results.append(f"  net67 запущен: {'ДА' if zapret_running else 'НЕТ'}")
            if relay_result["error"]:
                results.append(f"  Ошибка: {relay_result['error']}")
        publish()

        dns_relay_result = dns_relay_future.result()
        if dns_relay_result["reachable"]:
            results.append(f"  DNS relay (149.154.167.99): OK ({dns_relay_result['ms']:.0f}ms)")
        else:
            results.append(f"  DNS relay (149.154.167.99): TIMEOUT ({dns_relay_result['ms']:.0f}ms)")
        results.append("  (не используется — .220 стабильнее для медиа)")
        results.append("")

        results.extend(
            [
                "=" * 76,
                "  ПРЯМЫЕ ПОДКЛЮЧЕНИЯ К TELEGRAM DC",
                "=" * 76,
                f"{'IP':<20} {'DC':<12} {'TCP':>8}  {'TLS':>8}  {'Статус'}",
                "-" * 76,
            ]
        )

        dc_lines: list[str] = []
        dc_probes: list[dict] = []
        for future in concurrent.futures.as_completed(dc_futures):
            probe = future.result()
            dc_probes.append(probe)
            dc_lines.append(probe["line"])
            if progress_callback is not None:
                try:
                    progress_callback("\n".join(results + dc_lines))
                except Exception:
                    pass

        results.extend(dc_lines)
        results.append("")
        results.append("  Определение типа блокировки:")
        sni_result = sni_future.result()
        http_result = http_future.result()
        results.append(f"  {sni_result['line']}")
        results.append(f"  {http_result['line']}")
        publish()

        wss_results = [future.result() for future in wss_futures]
        results.extend(
            [
                "",
                "=" * 76,
                "  WSS RELAY — ДОСТУПНОСТЬ ЭНДПОИНТОВ (149.154.167.220)",
                "=" * 76,
                f"{'DC':<6} {'Endpoint':<32} {'TCP':>6}  {'TLS':>6}  {'WS':>6}  {'Результат'}",
                "-" * 76,
            ]
        )

        for result in sorted(wss_results, key=lambda item: item["dc"]):
            tcp = f"{result['tcp_ms']:.0f}ms" if result["tcp_ms"] is not None else "—"
            tls = f"{result['tls_ms']:.0f}ms" if result["tls_ms"] is not None else "—"
            ws = f"{result['ws_ms']:.0f}ms" if result["ws_ms"] is not None else "—"
            if result["status"] == "OK":
                status = "OK (101)"
            elif result["status"] == "WS_REDIRECT":
                status = f"{result['http_code']} (редирект)"
            elif result["status"] == "TLS_FAIL":
                status = "TLS FAIL"
            elif result["status"] == "TCP_FAIL":
                status = "TCP FAIL"
            elif result["status"] == "TIMEOUT":
                status = "TIMEOUT"
            else:
                status = result.get("error", result["status"])[:30]
            results.append(
                f"DC{result['dc']:<4} {result['domain']:<32} {tcp:>6}  {tls:>6}  {ws:>6}  {status}"
            )
        publish()

        proxy_result = proxy_future.result()
        winws2_running = winws_future.result()

        results.extend(
            [
                "",
                "=" * 76,
                f"  ПРОКСИ (127.0.0.1:{proxy_port})",
                "=" * 76,
            ]
        )
        if proxy_result["status"] == "OK":
            results.append(
                f"  SOCKS5: OK (tcp {proxy_result['tcp_ms']:.0f}ms, "
                f"socks {proxy_result['socks_ms']:.0f}ms)"
            )
        elif proxy_result["status"] == "NOT_RUNNING":
            results.append("  SOCKS5: НЕ ЗАПУЩЕН (порт закрыт)")
        else:
            results.append(f"  SOCKS5: {proxy_result['status']} — {proxy_result.get('error', '')}")

        if upstream_future is None and upstream_state == UPSTREAM_EMPTY:
            # Раньше в этом случае раздела не было вовсе. Внешний прокси
            # включён, проверять нечего — и отчёт молчал, хотя это ровно
            # то место, куда прокси уходит, когда прямые пути закрыты.
            results.extend(
                [
                    "",
                    "=" * 76,
                    "  ВНЕШНИЙ ПРОКСИ",
                    "=" * 76,
                    "  Включён, но не задан: адреса нет, встроенных в эту сборку нет.",
                    "  Запасной путь на случай блокировки ведёт в никуда.",
                ]
            )

        if upstream_future is not None:
            upstream_result = upstream_future.result()
            up_host = upstream_result.get("host", "?")
            up_port = upstream_result.get("port", 0)
            results.extend(
                [
                    "",
                    "=" * 76,
                    f"  UPSTREAM PROXY ({up_host}:{up_port})",
                    "=" * 76,
                ]
            )
            if upstream_result["status"] == "OK":
                results.append(
                    f"  SOCKS5: OK (tcp {upstream_result['tcp_ms']:.0f}ms, "
                    f"handshake {upstream_result['handshake_ms']:.0f}ms)"
                )
            elif upstream_result["status"] == "NOT_RUNNING":
                results.append("  SOCKS5: НЕ ЗАПУЩЕН (порт закрыт)")
            elif upstream_result["status"] == "TIMEOUT":
                results.append("  SOCKS5: TIMEOUT (не удалось подключиться)")
            else:
                results.append(
                    f"  SOCKS5: {upstream_result['status']} — "
                    f"{upstream_result.get('error', '')}"
                )

    elapsed = time.time() - t0
    results.extend(
        [
            "",
            "=" * 76,
            "  ИТОГ",
            "=" * 76,
            _build_summary(
                dc_lines,
                wss_results,
                proxy_result,
                winws2_running,
                dc_probes=dc_probes,
                foreign_sni=sni_result,
                http80=http_result,
                upstream=upstream_state,
            ),
            f"\nВремя тестирования: {elapsed:.1f}s",
        ]
    )
    publish()
    return "\n".join(results)

def _test_wss_relay(ip: str, domain: str, dc: int) -> dict:
    result = {
        "ip": ip,
        "domain": domain,
        "dc": dc,
        "tcp_ms": None,
        "tls_ms": None,
        "ws_ms": None,
        "status": "UNKNOWN",
        "http_code": None,
        "redirect_to": None,
        "error": None,
    }

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(4)
    t0 = time.time()
    try:
        sock.connect((ip, 443))
        result["tcp_ms"] = (time.time() - t0) * 1000
    except Exception as exc:
        sock.close()
        result["status"] = "TCP_FAIL"
        result["error"] = str(exc)
        return result

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    t1 = time.time()
    try:
        secure_sock = context.wrap_socket(sock, server_hostname=domain)
        result["tls_ms"] = (time.time() - t1) * 1000
    except Exception as exc:
        sock.close()
        result["status"] = "TLS_FAIL"
        result["error"] = str(exc)
        return result

    ws_key = b64encode(urandom(16)).decode()
    request = (
        "GET /apiws HTTP/1.1\r\n"
        f"Host: {domain}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {ws_key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "Sec-WebSocket-Protocol: binary\r\n"
        "Origin: https://web.telegram.org\r\n"
        "\r\n"
    )
    secure_sock.settimeout(5)
    t2 = time.time()
    try:
        secure_sock.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = secure_sock.recv(512)
            if not chunk:
                break
            response += chunk
            if len(response) > 4096:
                break
        result["ws_ms"] = (time.time() - t2) * 1000
        secure_sock.close()

        lines = response.split(b"\r\n")
        status_line = lines[0].decode("utf-8", errors="replace")
        parts = status_line.split(" ", 2)
        http_code = int(parts[1]) if len(parts) >= 2 else 0
        result["http_code"] = http_code

        for line in lines[1:]:
            decoded = line.decode("utf-8", errors="replace")
            if decoded.lower().startswith("location:"):
                result["redirect_to"] = decoded.split(":", 1)[1].strip()
                break

        if http_code == 101:
            result["status"] = "OK"
        elif http_code in (301, 302, 303, 307, 308):
            result["status"] = "WS_REDIRECT"
            result["error"] = status_line
        else:
            result["status"] = "WS_FAIL"
            result["error"] = status_line
        return result
    except socket.timeout:
        secure_sock.close()
        result["status"] = "TIMEOUT"
        result["error"] = "WS upgrade timeout"
        return result
    except Exception as exc:
        try:
            secure_sock.close()
        except Exception:
            pass
        result["status"] = "WS_FAIL"
        result["error"] = str(exc)
        return result

def _test_proxy_liveness(host: str, port: int) -> dict:
    result = {"status": "UNKNOWN", "tcp_ms": None, "socks_ms": None, "error": None}
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    t0 = time.time()
    try:
        sock.connect((host, port))
        result["tcp_ms"] = (time.time() - t0) * 1000
    except ConnectionRefusedError:
        sock.close()
        result["status"] = "NOT_RUNNING"
        result["error"] = "порт закрыт (прокси не запущен)"
        return result
    except socket.timeout:
        sock.close()
        result["status"] = "TIMEOUT"
        result["error"] = "TCP timeout"
        return result
    except Exception as exc:
        sock.close()
        result["status"] = "REFUSED"
        result["error"] = str(exc)
        return result

    t1 = time.time()
    try:
        sock.sendall(b"\x05\x01\x00")
        reply = sock.recv(2)
        if len(reply) < 2 or reply[0] != 5 or reply[1] != 0:
            sock.close()
            result["status"] = "SOCKS_ERROR"
            result["error"] = f"unexpected greeting: {reply.hex()}"
            return result

        ip_bytes = bytes([149, 154, 167, 220])
        sock.sendall(b"\x05\x01\x00\x01" + ip_bytes + b"\x01\xbb")
        reply = sock.recv(10)
        result["socks_ms"] = (time.time() - t1) * 1000
        sock.close()

        if len(reply) >= 2 and reply[0] == 5 and reply[1] == 0:
            result["status"] = "OK"
        else:
            code = reply[1] if len(reply) >= 2 else -1
            errors = {
                1: "general failure",
                2: "not allowed",
                3: "network unreachable",
                4: "host unreachable",
                5: "connection refused (relay unreachable)",
            }
            result["status"] = "SOCKS_ERROR"
            result["error"] = errors.get(code, f"code={code}")
        return result
    except socket.timeout:
        sock.close()
        result["status"] = "TIMEOUT"
        result["error"] = "SOCKS5 timeout"
        return result
    except Exception as exc:
        sock.close()
        result["status"] = "SOCKS_ERROR"
        result["error"] = str(exc)
        return result

def _test_upstream_proxy(
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    tls: bool = False,
    tls_server_name: str = "",
    tls_verify: bool = False,
) -> dict:
    result = {
        "host": host,
        "port": port,
        "status": "NOT_RUNNING",
        "tcp_ms": 0,
        "handshake_ms": 0,
    }
    try:
        t0 = time.monotonic()
        sock = socket.create_connection((host, port), timeout=5.0)
        if tls:
            context = ssl.create_default_context()
            if not tls_verify:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(sock, server_hostname=tls_server_name or host)
        result["tcp_ms"] = (time.monotonic() - t0) * 1000

        t1 = time.monotonic()
        if username:
            sock.sendall(b"\x05\x02\x00\x02")
        else:
            sock.sendall(b"\x05\x01\x00")
        reply = sock.recv(2)
        if len(reply) == 2 and reply[0] == 5 and reply[1] == 2 and username:
            user_bytes = username.encode("utf-8")
            pass_bytes = password.encode("utf-8")
            sock.sendall(b"\x01" + bytes([len(user_bytes)]) + user_bytes + bytes([len(pass_bytes)]) + pass_bytes)
            auth_reply = sock.recv(2)
            if len(auth_reply) == 2 and auth_reply[0] == 1 and auth_reply[1] == 0:
                result["handshake_ms"] = (time.monotonic() - t1) * 1000
                result["status"] = "OK"
            else:
                result["status"] = "SOCKS_ERROR"
                result["error"] = f"Bad auth reply: {auth_reply.hex()}"
        elif len(reply) == 2 and reply[0] == 5 and reply[1] == 0:
            result["handshake_ms"] = (time.monotonic() - t1) * 1000
            result["status"] = "OK"
        else:
            result["status"] = "SOCKS_ERROR"
            result["error"] = f"Bad reply: {reply.hex()}"
        sock.close()
    except socket.timeout:
        result["status"] = "TIMEOUT"
        result["error"] = "Connection timeout"
    except ConnectionRefusedError:
        result["status"] = "NOT_RUNNING"
        result["error"] = "Connection refused"
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = str(exc)
    return result

def _test_single_ip(ip: str, dc: str, wss: str) -> dict:
    """Прямая проба адреса: TCP, затем TLS.

    Возвращает строку для экрана и разобранный исход. Раньше отдавалась
    одна строка, и итог отчёта вычитывал из неё исход поиском подстрок —
    а вердикт о типе блокировки не читал его вовсе.
    """
    result = {"ip": ip, "dc": dc, "tcp": False, "tls": None, "line": ""}
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    t0 = time.time()
    try:
        sock.connect((ip, 443))
        tcp_ms = (time.time() - t0) * 1000
    except Exception:
        sock.close()
        result["line"] = f"{ip:<20} {dc:<12} {'FAIL':>8}  {'—':>8}  TCP не подключается"
        return result

    result["tcp"] = True
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    t1 = time.time()
    try:
        secure_sock = context.wrap_socket(sock, server_hostname="telegram.org")
        tls_ms = (time.time() - t1) * 1000
        secure_sock.close()
        result["tls"] = "ok"
        result["line"] = f"{ip:<20} {dc:<12} {tcp_ms:>6.0f}ms  {tls_ms:>6.0f}ms  OK"
    except ssl.SSLError as exc:
        tls_ms = (time.time() - t1) * 1000
        sock.close()
        result["tls"] = "blocked"
        result["line"] = f"{ip:<20} {dc:<12} {tcp_ms:>6.0f}ms  {tls_ms:>6.0f}ms  BLOCKED ({exc.reason})"
    except socket.timeout:
        sock.close()
        result["tls"] = "timeout"
        result["line"] = f"{ip:<20} {dc:<12} {tcp_ms:>6.0f}ms  {'5000':>6}ms  TIMEOUT"
    except Exception as exc:
        sock.close()
        result["tls"] = "error"
        result["line"] = f"{ip:<20} {dc:<12} {tcp_ms:>6.0f}ms  {'—':>8}  {type(exc).__name__}"
    return result

def _test_sni_vs_ip() -> dict:
    """TLS с чужим SNI на адрес Telegram.

    Отделяет «режут по имени» от «режут по адресу». Раньше TCP и TLS
    здесь не различались: таймаут соединения и таймаут рукопожатия
    попадали в одну ветку и подписывались одинаково, хотя значат разное.
    Не установилось соединение — до имени дело не дошло вовсе, и вывод о
    SNI из такой пробы делать нельзя.
    """
    ip = "149.154.167.50"
    result = {"tcp": False, "tls": None, "line": ""}
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((ip, 443))
    except Exception:
        sock.close()
        result["line"] = (
            f"TLS с чужим SNI (example.com → {ip}): TCP не устанавливается "
            "→ до имени дело не доходит, режут по адресу"
        )
        return result

    result["tcp"] = True
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    t0 = time.time()
    try:
        secure_sock = context.wrap_socket(sock, server_hostname="example.com")
        ms = (time.time() - t0) * 1000
        secure_sock.close()
        result["tls"] = "ok"
        result["line"] = f"TLS с чужим SNI (example.com → {ip}): OK ({ms:.0f}ms) → блокировка по SNI"
    except ssl.SSLError:
        sock.close()
        result["tls"] = "blocked"
        result["line"] = f"TLS с чужим SNI (example.com → {ip}): BLOCKED → TLS рвётся независимо от имени"
    except socket.timeout:
        sock.close()
        result["tls"] = "timeout"
        result["line"] = f"TLS с чужим SNI (example.com → {ip}): TIMEOUT → TLS рвётся независимо от имени"
    except Exception as exc:
        sock.close()
        result["tls"] = "error"
        result["line"] = f"TLS с чужим SNI: {type(exc).__name__}"
    return result

def _test_http_port80() -> dict:
    """Открытый HTTP на тот же адрес.

    Если закрыт и он, дело не в TLS вообще: адрес недоступен целиком.
    """
    ip = "149.154.167.50"
    result = {"tcp": False, "ok": False, "line": ""}
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        t0 = time.time()
        sock.connect((ip, 80))
        result["tcp"] = True
        sock.send(b"GET / HTTP/1.0\r\nHost: test\r\n\r\n")
        sock.settimeout(3)
        data = sock.recv(1024)
        ms = (time.time() - t0) * 1000
        sock.close()
        result["ok"] = True
        result["line"] = f"HTTP {ip}:80 → {len(data)} байт ({ms:.0f}ms) — НЕ блокируется"
    except socket.timeout:
        sock.close()
        result["line"] = f"HTTP {ip}:80 → TIMEOUT — блокируется"
    except Exception as exc:
        sock.close()
        result["line"] = f"HTTP {ip}:80 → {type(exc).__name__}"
    return result

def _check_winws2_running() -> bool:
    try:
        from settings.mode import ALL_WINWS_EXE_NAME_SET

        for _pid, process_name in iter_process_records_winapi():
            if str(process_name or "").strip().lower() in ALL_WINWS_EXE_NAME_SET:
                return True
        return False
    except Exception:
        return False

#: Виды блокировки. Строки, а не перечисление: они уходят в проверки и
#: в журнал, и читать их там должен человек.
BLOCK_NONE = "none"
BLOCK_IP = "ip"
BLOCK_PARTIAL_IP = "partial_ip"
BLOCK_SNI = "sni"
BLOCK_TLS = "tls"
BLOCK_UNKNOWN = "unknown"

#: Состояние внешнего прокси.
UPSTREAM_OFF = "off"
UPSTREAM_READY = "ready"
UPSTREAM_EMPTY = "empty"


def classify_blocking(dc_probes, *, foreign_sni=None, http80=None) -> dict:
    """Какая блокировка перед нами — по собранным пробам.

    Раньше итог писал «блокировка TLS к IP Telegram (DPI)» при любом
    числе заблокированных адресов, одной строкой, и собственных проб не
    смотрел вообще. В отчёте, где TCP не устанавливался ни к одному из
    шестнадцати адресов, это была прямая неправда: SYN без ответа — это
    не DPI, инспектировать там нечего. И неправда с последствием: вывод
    «DPI» тянет за собой совет запустить обход, а обход против такой
    блокировки бессилен.

    Порядок проверок и есть смысл функции:

    * соединение не устанавливается ни к одному адресу — режут по IP;
    * к части не устанавливается — по IP, но частично;
    * устанавливается, но TLS рвётся — это DPI, и дальше решает проба с
      чужим именем: прошла — режут по SNI, не прошла — по адресу.

    ``dpi_can_help`` — есть ли хоть одно установленное и порванное
    соединение. Только с такими и работает обход: winws2 меняет пакеты
    уже установленного соединения, а к несуществующему ему прикладывать
    нечего.
    """
    probes = [p for p in (dc_probes or ()) if isinstance(p, dict)]
    dead = [p for p in probes if not p.get("tcp")]
    broken = [p for p in probes if p.get("tcp") and p.get("tls") != "ok"]
    fine = [p for p in probes if p.get("tcp") and p.get("tls") == "ok"]

    def _verdict(kind: str, title: str, detail: str = "") -> dict:
        return {
            "kind": kind,
            "title": title,
            "detail": detail,
            "dpi_can_help": bool(broken),
            "dead": len(dead),
            "broken": len(broken),
            "fine": len(fine),
            "total": len(probes),
        }

    if not probes:
        return _verdict(BLOCK_UNKNOWN, "Тип: не определён — пробы не дали результата")

    if not dead and not broken:
        return _verdict(BLOCK_NONE, "Блокировки не обнаружено")

    if dead and not broken and not fine:
        also = []
        if isinstance(http80, dict) and not http80.get("tcp"):
            also.append("порт 80 тоже")
        if isinstance(foreign_sni, dict) and not foreign_sni.get("tcp"):
            also.append("с чужим SNI тоже")
        tail = f" ({', '.join(also)})" if also else ""
        return _verdict(
            BLOCK_IP,
            "Тип: блокировка по IP — соединение не устанавливается",
            f"TCP не открылся ни к одному из {len(probes)} адресов Telegram{tail}. "
            "Это не DPI: инспектировать нечего, до TLS дело не доходит.",
        )

    if dead:
        return _verdict(
            BLOCK_PARTIAL_IP,
            "Тип: частичная блокировка по IP",
            f"К {len(dead)} из {len(probes)} адресов соединение не устанавливается вовсе"
            + (f", ещё у {len(broken)} рвётся TLS." if broken else "."),
        )

    # Соединения есть, рвётся TLS: это DPI.
    if isinstance(foreign_sni, dict) and foreign_sni.get("tls") == "ok":
        return _verdict(
            BLOCK_SNI,
            "Тип: блокировка по SNI (DPI)",
            "С чужим именем TLS проходит, с именем Telegram — рвётся.",
        )
    return _verdict(
        BLOCK_TLS,
        "Тип: блокировка TLS к адресам Telegram (DPI)",
        "TCP устанавливается, TLS рвётся независимо от имени.",
    )


def classify_upstream(*, effective: bool, host: str, preset_id: str, has_bundled: bool) -> str:
    """Есть ли внешнему прокси куда вести.

    ``effective`` — включён ли он на деле. В режиме MTProxy он включён
    всегда, тумблер там не решает ничего, и это стоит держать в голове:
    выключенный на экране внешний прокси в этом режиме всё равно в деле.

    Пустой адрес ещё не значит «некуда»: есть встроенные в сборку
    адреса, и без своего берётся первый из них. «Некуда» — это когда нет
    ни своего, ни выбранного, ни встроенных.
    """
    if not effective:
        return UPSTREAM_OFF
    if str(host or "").strip() or str(preset_id or "").strip() or has_bundled:
        return UPSTREAM_READY
    return UPSTREAM_EMPTY


def _load_upstream_state() -> str:
    """Состояние внешнего прокси по настройкам. Сбой — считаем выключенным.

    Выключенным, а не пустым: пустое состояние в отчёте тянет за собой
    предупреждение, и выдать его по ошибке чтения значит соврать.
    """
    try:
        from settings.store import (
            get_tg_proxy_mode,
            get_tg_proxy_upstream_enabled,
            get_tg_proxy_upstream_host,
            get_tg_proxy_upstream_preset_id,
        )
        from telegram_proxy.config.upstream_catalog import UpstreamPresetResolver

        effective = telegram_proxy_settings.effective_upstream_enabled(
            get_tg_proxy_mode(), get_tg_proxy_upstream_enabled()
        )
        has_bundled = UpstreamPresetResolver.load_from_runtime().first_socks5() is not None
        return classify_upstream(
            effective=bool(effective),
            host=str(get_tg_proxy_upstream_host() or ""),
            preset_id=str(get_tg_proxy_upstream_preset_id() or ""),
            has_bundled=bool(has_bundled),
        )
    except Exception as exc:
        log(f"[TG_DIAG] состояние внешнего прокси не прочитано: {exc}", "DEBUG")
        return UPSTREAM_OFF


def _probes_from_lines(dc_lines) -> list[dict]:
    """Разбирает старые строки проб в исходы.

    Только для совместимости: так _build_summary зовут проверки, у
    которых на руках одни строки. Основной путь передаёт исходы сразу.
    """
    probes: list[dict] = []
    for line in dc_lines or ():
        text = str(line or "")
        if "TCP не подключается" in text:
            probes.append({"tcp": False, "tls": None, "line": text})
        elif text.strip().endswith("OK"):
            probes.append({"tcp": True, "tls": "ok", "line": text})
        elif "BLOCKED" in text:
            probes.append({"tcp": True, "tls": "blocked", "line": text})
        elif "TIMEOUT" in text:
            probes.append({"tcp": True, "tls": "timeout", "line": text})
        elif text.strip():
            probes.append({"tcp": True, "tls": "error", "line": text})
    return probes


def _build_summary(
    dc_lines: list[str],
    wss_results: list[dict],
    proxy_result: dict,
    winws2_running: bool,
    *,
    dc_probes: list[dict] | None = None,
    foreign_sni: dict | None = None,
    http80: dict | None = None,
    upstream: str = UPSTREAM_OFF,
) -> str:
    def _dc_num(name: str):
        if not name.startswith("DC"):
            return None
        digits = ""
        for char in name[2:]:
            if char.isdigit():
                digits += char
            else:
                break
        return int(digits) if digits and len(digits) <= 2 else None

    dc_status: dict[str, str] = {}
    dc_names_ordered = (
        "DC203 CDN",
        "DC5 media",
        "DC5",
        "DC4 media",
        "DC4",
        "DC3 media",
        "DC3 (→DC1)",
        "DC2 media",
        "DC2",
        "DC1 media",
        "DC1",
    )
    for line in dc_lines:
        for dc_name in dc_names_ordered:
            if dc_name in line:
                if line.strip().endswith("OK"):
                    dc_status.setdefault(dc_name, "OK")
                elif "BLOCKED" in line or "TIMEOUT" in line or "FAIL" in line:
                    dc_status[dc_name] = "BLOCKED"
                break

    blocked = sum(1 for value in dc_status.values() if value == "BLOCKED")
    ok_count = sum(1 for value in dc_status.values() if value == "OK")
    wss_ok_dcs = {result["dc"] for result in wss_results if result["status"] == "OK"}
    wss_redirect_dcs = {result["dc"] for result in wss_results if result["status"] == "WS_REDIRECT"}
    relay_ok = bool(wss_ok_dcs)
    proxy_running = proxy_result["status"] == "OK"
    proxy_not_running = proxy_result["status"] == "NOT_RUNNING"

    verdict = classify_blocking(
        dc_probes if dc_probes is not None else _probes_from_lines(dc_lines),
        foreign_sni=foreign_sni,
        http80=http80,
    )
    dpi_can_help = bool(verdict["dpi_can_help"])

    # Единица счёта названа явно. Рядом стоит вердикт, который считает
    # адреса, а их больше, чем дата-центров: «заблокировано 11» и «ни к
    # одному из 16» без подписи читались как противоречие.
    summary: list[str] = [
        "── Тип блокировки ──",
        f"  Дата-центров доступно: {ok_count}  |  заблокировано: {blocked}",
    ]
    if blocked == 0 and ok_count > 0:
        summary.append("  Блокировки не обнаружено")
    elif blocked > 0:
        summary.append(f"  {verdict['title']}")
        if verdict["detail"]:
            summary.append(f"  {verdict['detail']}")
        summary.append("  (подробности в секции 'Определение типа блокировки' выше)")

    summary.extend(["", "── Статус дата-центров ──"])
    for dc_name in (
        "DC1",
        "DC1 media",
        "DC2",
        "DC2 media",
        "DC3 (→DC1)",
        "DC3 media",
        "DC4",
        "DC4 media",
        "DC5",
        "DC5 media",
        "DC203 CDN",
    ):
        direct = dc_status.get(dc_name, "—")
        dc_num = _dc_num(dc_name)
        if dc_num and dc_num in wss_ok_dcs:
            wss_info = "WSS relay"
        elif dc_num and dc_num in wss_redirect_dcs:
            wss_info = "нет relay"
        elif dc_name == "DC203 CDN":
            wss_info = "TCP (CDN)"
        else:
            wss_info = "—"

        if direct == "OK":
            icon = "+"
        elif direct == "BLOCKED" and dc_num in wss_ok_dcs:
            icon = "~"
        else:
            icon = "x"
        summary.append(f"  [{icon}] {dc_name:<10} напрямую: {direct:<10} прокси: {wss_info}")

    summary.extend(["", "── WSS relay (149.154.167.220) ──"])
    if relay_ok:
        summary.append(f"  Доступен: {', '.join(f'kws{dc}' for dc in sorted(wss_ok_dcs))}")
    else:
        summary.append("  Недоступен")
    if wss_redirect_dcs:
        summary.append(f"  Редирект (нет relay): {', '.join(f'kws{dc}' for dc in sorted(wss_redirect_dcs))}")

    summary.extend(["", "── Сервисы ──"])
    if proxy_running:
        summary.append("  Прокси: запущен")
    elif proxy_not_running:
        summary.append("  Прокси: не запущен")
    else:
        summary.append(f"  Прокси: ошибка ({proxy_result.get('error', '?')})")
    summary.append(f"  {ENGINE_WINWS2}: {'запущен' if winws2_running else 'не запущен'}")
    if upstream == UPSTREAM_EMPTY:
        summary.append("  Внешний прокси: включён, но не задан")
    elif upstream == UPSTREAM_READY:
        summary.append("  Внешний прокси: задан")

    if (
        proxy_result.get("status") == "TIMEOUT"
        and not relay_ok
        and blocked > 0
        and verdict["fine"] == 0
    ):
        # Таймаут вместо «порт закрыт» значит, что прокси жив и принял
        # соединение. Висит он потому, что идти некуда, — а без этой
        # строки таймаут читается как «прокси сломался».
        route_tail = ", внешний прокси не задан" if upstream == UPSTREAM_EMPTY else ""
        summary.append(
            "  (прокси принял соединение, но идти ему некуда: relay недоступен, "
            f"прямой путь закрыт{route_tail})"
        )

    summary.extend(["", "── Рекомендации ──"])
    if blocked == 0 and ok_count > 0:
        summary.append("  Telegram доступен напрямую, прокси не требуется.")
        return "\n".join(summary)

    bypassed_dcs = set()
    for dc_name, status in dc_status.items():
        if status == "BLOCKED":
            num = _dc_num(dc_name)
            if num is not None and num in wss_ok_dcs:
                bypassed_dcs.add(dc_name)
    blocked_no_wss = {
        dc_name
        for dc_name, status in dc_status.items()
        if status == "BLOCKED" and dc_name not in bypassed_dcs
    }

    if bypassed_dcs and relay_ok:
        names = ", ".join(sorted(bypassed_dcs))
        if proxy_running:
            summary.append(f"  [+] {names}: заблокированы напрямую, обходятся через WSS прокси")
        else:
            summary.append(f"  [~] {names}: WSS relay доступен, но прокси не запущен")

    if blocked_no_wss and not dpi_can_help and verdict["fine"] == 0:
        # Закрыто всё. Перечислять одиннадцать имён дважды подряд и
        # писать «часть контента может не загружаться» — значит
        # преуменьшить: не загружается ничего.
        summary.append(
            "  [x] Не открывается ни один дата-центр, relay тоже — соединение не "
            f"устанавливается вовсе. Обход DPI тут бессилен: {ENGINE_WINWS2} работает "
            "только с установленными соединениями"
        )
    elif blocked_no_wss:
        names = ", ".join(sorted(blocked_no_wss))
        summary.append(
            f"  [!] {names}: заблокированы, WSS relay нет — часть контента (эмодзи, стикеры) может не загружаться"
        )
        if not dpi_can_help:
            # Совет «запустите обход» здесь был бы вредным: человек
            # запускает, ничего не меняется, и он ищет поломку в обходе.
            summary.append(
                f"  [x] {names}: соединение не устанавливается вовсе — обход DPI тут "
                f"бессилен, {ENGINE_WINWS2} работает только с установленными соединениями"
            )
        elif winws2_running:
            summary.append(f"  [~] {ENGINE_WINWS2} запущен — {names} могут работать через zapret")
        else:
            summary.append(f"  [!] Для {names} запустите {ENGINE_WINWS2}/zapret на главной странице")

    if proxy_not_running:
        summary.append("  [!] Прокси не запущен — запустите его на этой странице")

    if not relay_ok and blocked > 0:
        summary.append("  [x] прямой WSS relay сейчас недоступен — проверьте Telegram на практике")
        if not dpi_can_help:
            if upstream == UPSTREAM_EMPTY:
                summary.append(
                    "  [!] Внешний прокси включён, но не задан. При блокировке по IP это "
                    "единственный путь — укажите SOCKS5 в настройках прокси или используйте VPN"
                )
            elif upstream == UPSTREAM_READY:
                summary.append(
                    "  [~] Трафик пойдёт через внешний прокси — если Telegram не работает, "
                    "проверьте его раздел выше"
                )
            else:
                summary.append("  [!] Нужен внешний SOCKS5 или VPN: прямые пути закрыты")
        elif not winws2_running:
            summary.append(f"  [!] Запустите {ENGINE_WINWS2}/zapret или используйте VPN")

    return "\n".join(summary)
