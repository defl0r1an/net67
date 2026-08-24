"""Запуск ядра Xray и подключение по ссылке.

Ссылки `vless://`, `vmess://`, `trojan://` и `ss://` поднимает не
AmneziaWG, а отдельное ядро — `bin/xray/xray.exe`. Разбор ссылок живёт в
`vpn/links.py`, здесь — только запуск ядра и его конфигурация.

## Почему локальный прокси, а не туннель

Xray умеет поднимать системный туннель, но это драйвер, права
администратора и конфликт с WinDivert, который в это же время держит
обход DPI. Локальный прокси на 127.0.0.1 ничего этого не требует:
браузеру и приложениям он отдаётся обычной настройкой прокси Windows, и
если ядро упало, интернет остаётся рабочим.

## Почему конфигурация файлом, а не аргументами

У Xray сотня параметров, и половина ссылок несёт их в своей строке
запроса — `security`, `sni`, `flow`, `pbk`, `sid`. Разбирать их в
аргументы командной строки значило бы поддерживать чужой формат
целиком. Файл конфигурации ядро читает само, а ссылку мы отдаём ему в
том виде, в каком она пришла.

## Про ожидание

`Popen` возвращает объект сразу, но слушатель поднимается не мгновенно.
Проверяем портом: пока никто не слушает, подключаться некуда. Ошибка
здесь стоила бы «подключено» на экране при мёртвом ядре — ровно та
ошибка, что уже случалась с прокси Telegram.
"""

from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path


#: Порт локального прокси. Нестандартный намеренно: 1080 и 8080 заняты
#: половиной программ, и попасть в чужой слушающий порт значило бы
#: считать чужую службу своим ядром.
LOCAL_PORT = 10808

#: Сколько ждём, пока ядро поднимет слушателя.
#:
#: Полторы секунды хватает с запасом: замер на холодном старте — меньше
#: двухсот миллисекунд. Больше ждать незачем, не поднялось за это время
#: значит не поднимется.
STARTUP_TIMEOUT_S = 1.5

#: Как часто спрашиваем порт, пока ждём.
POLL_INTERVAL_S = 0.05


class XrayError(RuntimeError):
    """Ядро не запустилось. Текст показывается человеку."""


def core_path(root: Path | None = None) -> Path:
    """Где лежит ядро: `bin/xray/xray.exe`.

    Здесь стояло `APPLICATION_PATHS.application_dir` — свойства с таким
    именем у путей приложения нет вовсе. Любое обращение падало с
    AttributeError ещё до проверки, есть ли файл, так что не работала
    даже вежливая проверка «ядро на месте?».

    Саму папку менять не надо: ядро уже лежит в bin/xray, и одну мою
    правку пришлось откатить — я перенёс путь в exe, не посмотрев, что
    файл на месте.
    """
    if root is not None:
        return Path(root) / "bin" / "xray" / "xray.exe"

    from config.runtime_layout import APPLICATION_PATHS

    return Path(APPLICATION_PATHS.bin_dir) / "xray" / "xray.exe"


def is_core_available(root: Path | None = None) -> bool:
    try:
        return core_path(root).is_file()
    except Exception:
        return False


def _stream_settings(query: dict) -> dict:
    """Как ядро оборачивает соединение: транспорт и маскировка.

    Разбирается из параметров ссылки. Неизвестные не выдумываем: чего
    нет — того нет, ядро подставит своё умолчание.
    """
    network = (query.get("type") or ["tcp"])[0]
    security = (query.get("security") or ["none"])[0]

    stream: dict = {"network": network, "security": security}

    if security == "tls":
        tls: dict = {}
        sni = (query.get("sni") or query.get("host") or [""])[0]
        if sni:
            tls["serverName"] = sni
        fingerprint = (query.get("fp") or [""])[0]
        if fingerprint:
            tls["fingerprint"] = fingerprint
        alpn = (query.get("alpn") or [""])[0]
        if alpn:
            tls["alpn"] = [part for part in alpn.split(",") if part]
        stream["tlsSettings"] = tls
    elif security == "reality":
        reality = {}
        for key, name in (("sni", "serverName"), ("pbk", "publicKey"), ("sid", "shortId"), ("fp", "fingerprint")):
            value = (query.get(key) or [""])[0]
            if value:
                reality[name] = value
        stream["realitySettings"] = reality

    if network == "ws":
        ws: dict = {}
        path = (query.get("path") or [""])[0]
        if path:
            ws["path"] = path
        host = (query.get("host") or [""])[0]
        if host:
            ws["headers"] = {"Host": host}
        stream["wsSettings"] = ws
    elif network == "grpc":
        service = (query.get("serviceName") or [""])[0]
        if service:
            stream["grpcSettings"] = {"serviceName": service}

    return stream


def _outbound(profile) -> dict:
    """Исходящее соединение под протокол профиля.

    Раньше здесь стояла заглушка: протокол и сама ссылка полем `_link`,
    без адреса, идентификатора и транспорта. Ядро с такой настройкой не
    поднялось бы никогда — а на странице это выглядело бы как «ядро
    запустилось и тут же умерло».
    """
    from urllib.parse import parse_qs, unquote, urlparse

    scheme = str(getattr(profile, "scheme", "") or "").lower()
    raw = str(getattr(profile, "raw", "") or "")
    host = str(getattr(profile, "host", "") or "")
    port = int(getattr(profile, "port", 0) or 0)

    parsed = urlparse(raw)
    query = parse_qs(parsed.query)
    user = unquote(parsed.username or "")

    stream = _stream_settings(query)

    if scheme == "vless":
        user_entry: dict = {"id": user, "encryption": "none"}
        flow = (query.get("flow") or [""])[0]
        if flow:
            user_entry["flow"] = flow
        settings = {"vnext": [{"address": host, "port": port, "users": [user_entry]}]}
    elif scheme == "vmess":
        # У vmess разобранные поля лежат в самом профиле: ссылка это
        # base64 от JSON, и парсер уже её раскрыл.
        settings = {
            "vnext": [
                {
                    "address": host,
                    "port": port,
                    "users": [{"id": user or str(getattr(profile, "user_id", "") or ""), "alterId": 0, "security": "auto"}],
                }
            ]
        }
    elif scheme == "trojan":
        settings = {"servers": [{"address": host, "port": port, "password": user}]}
    else:
        # shadowsocks: метод и пароль лежат в имени пользователя, часто
        # закодированные base64.
        method, _, password = user.partition(":")
        if not password:
            try:
                from vpn.links import _b64_decode

                decoded = _b64_decode(user).decode("utf-8", errors="replace")
                method, _, password = decoded.partition(":")
            except Exception:
                method, password = "", user
        settings = {
            "servers": [
                {"address": host, "port": port, "method": method or "aes-256-gcm", "password": password}
            ]
        }

    return {
        "tag": "proxy",
        "protocol": scheme,
        "settings": settings,
        "streamSettings": stream,
    }


def build_config(profile, *, port: int = LOCAL_PORT) -> dict:
    """Конфигурация ядра под один сервер."""
    return {
        # Лог ядра гасим: он пишет каждое соединение, и на активном
        # браузере это десятки строк в секунду в чужом формате.
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "local",
                "listen": "127.0.0.1",
                "port": int(port),
                "protocol": "socks",
                "settings": {"udp": True},
            }
        ],
        "outbounds": [_outbound(profile), {"tag": "direct", "protocol": "freedom"}],
    }


def is_port_open(port: int = LOCAL_PORT, *, host: str = "127.0.0.1") -> bool:
    """Слушает ли кто-нибудь порт. Это и есть признак живого ядра."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.2)
    try:
        return probe.connect_ex((host, int(port))) == 0
    except Exception:
        return False
    finally:
        try:
            probe.close()
        except Exception:
            pass


def wait_until_listening(
    port: int = LOCAL_PORT,
    *,
    timeout_s: float = STARTUP_TIMEOUT_S,
    probe=None,
) -> bool:
    """Ждёт, пока ядро поднимет слушателя.

    `probe` подменяется в тестах: настоящий сокет там ни к чему, а
    правило «ждём до истечения срока и не дольше» проверять надо.
    """
    check = probe or (lambda: is_port_open(port))
    deadline = time.monotonic() + float(timeout_s)
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(POLL_INTERVAL_S)
    return bool(check())


def write_config(profile, directory: Path, *, port: int = LOCAL_PORT) -> Path:
    """Кладёт конфигурацию рядом с настройками и возвращает путь."""
    target = Path(directory) / "xray-config.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(build_config(profile, port=port), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


class XrayRuntime:
    """Живое ядро: запустить, проверить, остановить."""

    def __init__(self, *, root: Path | None = None, port: int = LOCAL_PORT):
        self._root = root
        self._port = int(port)
        self._process: subprocess.Popen | None = None

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        process = self._process
        return process is not None and process.poll() is None

    def start(self, profile, *, settings_dir: Path, spawn=None) -> None:
        """Поднимает ядро под выбранный сервер.

        `spawn` подменяется в тестах: запускать настоящий процесс в
        проверке правил незачем.
        """
        if self.is_running:
            self.stop()

        core = core_path(self._root)
        if spawn is None and not core.is_file():
            raise XrayError(
                "Ядро Xray не найдено. Положите xray.exe в папку bin\\xray "
                "рядом с программой."
            )

        config = write_config(profile, Path(settings_dir), port=self._port)
        launcher = spawn or self._spawn
        self._process = launcher(core, config)

        if not wait_until_listening(self._port, probe=None if spawn is None else (lambda: True)):
            self.stop()
            raise XrayError("Ядро Xray не начало слушать порт за полторы секунды")

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    @staticmethod
    def _spawn(core: Path, config: Path):
        # Окно консоли не показываем: ядро работает фоном, и всплывающее
        # чёрное окно человек читает как «что-то сломалось».
        creation_flags = 0
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        except AttributeError:
            creation_flags = 0

        return subprocess.Popen(
            [str(core), "run", "-c", str(config)],
            cwd=str(core.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )


__all__ = [
    "LOCAL_PORT",
    "POLL_INTERVAL_S",
    "STARTUP_TIMEOUT_S",
    "XrayError",
    "XrayRuntime",
    "build_config",
    "core_path",
    "is_core_available",
    "is_port_open",
    "wait_until_listening",
    "write_config",
]
