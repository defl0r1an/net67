"""Документация: поднимает вики на локальном адресе и открывает браузер.

Вики — это статический сайт: папка `docs` рядом с программой. Открыть её
файлом в браузере нельзя, и вот почему.

Генератор сайта рассчитан на веб-сервер. Ссылки внутри страниц ведут на
`./vpn`, а не на `./vpn.html`: расширение подставляет сервер. По
протоколу `file://` подставлять некому — щелчок по любой ссылке даёт
«файл не найден». Поиск по сайту тоже отваливается: он читает свой
указатель через fetch, а из `file://` браузер такие запросы запрещает.

Поэтому программа поднимает свой сервер. Он крохотный: отдаёт файлы из
одной папки и ничего больше.

## Что с безопасностью

Слушаем только `127.0.0.1` — адрес самого компьютера. Из сети, включая
локальную, подключиться нельзя: система такие соединения не пропустит.

Отдаём строго содержимое папки `docs`. Выход за её пределы `..` в адресе
не даёт: путь приводится к абсолютному и сверяется с корнем.

## Почему сервер живёт до выхода из программы

Человек читает вики в браузере, переключается на работу, возвращается.
Останавливать сервер после первой страницы значило бы ломать вкладку,
оставленную открытой. Он занимает один поток и несколько килобайт,
поэтому просто живёт до закрытия программы.
"""

from __future__ import annotations

import threading
from pathlib import Path

from log.log import log


#: С какого порта начинаем искать свободный.
#:
#: Число выбрано в верхней части диапазона временных портов и ни за кем
#: не закреплено. Занят — берём следующий: на машине может работать
#: другая программа, и отнимать у неё порт незачем.
PREFERRED_PORT = 8317

#: Сколько портов пробуем, прежде чем сдаться.
PORT_ATTEMPTS = 20

#: Запущенный сервер. Второй раз не поднимаем — открываем тот же адрес.
_SERVER = None
_SERVER_URL = ""
_LOCK = threading.Lock()


def docs_root() -> Path:
    """Папка с собранной вики."""
    from config.runtime_layout import APPLICATION_PATHS

    return Path(APPLICATION_PATHS.docs_dir)


def is_available() -> bool:
    """Есть ли что открывать.

    Проверяем не папку, а главную страницу в ней: пустая папка `docs`
    остаётся после неудачной сборки, и по ней раздел выглядел бы рабочим.
    """
    try:
        return (docs_root() / "index.html").is_file()
    except Exception:
        return False


def _build_handler(root: Path):
    import http.server

    class Handler(http.server.SimpleHTTPRequestHandler):
        """Отдаёт `vpn.html`, когда просят `/vpn`."""

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def translate_path(self, path: str) -> str:
            resolved = Path(super().translate_path(path))

            if resolved.is_dir() or resolved.exists():
                return str(resolved)

            # Ссылки внутри сайта расширения не содержат.
            with_html = resolved.with_name(resolved.name + ".html")
            if with_html.exists():
                return str(with_html)

            return str(resolved)

        def log_message(self, *_args) -> None:
            # Обращения браузера в журнал не пишем: их сотни на страницу,
            # и полезного в них нет ничего.
            pass

    return Handler


def _free_port(start: int) -> int | None:
    import socket

    for candidate in range(start, start + PORT_ATTEMPTS):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return candidate
    return None


def start() -> str:
    """Поднимает сервер и возвращает адрес. Пустая строка — не удалось."""
    global _SERVER, _SERVER_URL

    with _LOCK:
        if _SERVER is not None:
            return _SERVER_URL

        root = docs_root()
        if not (root / "index.html").is_file():
            log(f"Документация не найдена: {root}", "⚠ WARNING")
            return ""

        port = _free_port(PREFERRED_PORT)
        if port is None:
            log("Не нашлось свободного порта для документации", "❌ ERROR")
            return ""

        try:
            import socketserver

            socketserver.TCPServer.allow_reuse_address = True
            server = socketserver.ThreadingTCPServer(
                ("127.0.0.1", port),
                _build_handler(root),
            )
            # Поток фоновый: он не должен удерживать программу при выходе.
            thread = threading.Thread(
                target=server.serve_forever,
                name="docs-site",
                daemon=True,
            )
            thread.start()
        except Exception as exc:
            log(f"Не удалось поднять документацию: {exc}", "❌ ERROR")
            return ""

        _SERVER = server
        _SERVER_URL = f"http://127.0.0.1:{port}/"
        log(f"Документация открыта на {_SERVER_URL}", "INFO")
        return _SERVER_URL


def stop() -> None:
    """Останавливает сервер. Вызывается при выходе из программы."""
    global _SERVER, _SERVER_URL

    with _LOCK:
        server = _SERVER
        _SERVER = None
        _SERVER_URL = ""

    if server is None:
        return

    try:
        server.shutdown()
        server.server_close()
        log("Документация остановлена", "DEBUG")
    except Exception as exc:
        log(f"Не удалось остановить документацию: {exc}", "DEBUG")


def open_in_browser() -> tuple[bool, str]:
    """Поднимает сайт и открывает его в браузере.

    Возвращает (получилось, адрес или причина отказа).
    """
    if not is_available():
        return (False, "Документация не установлена вместе с программой")

    url = start()
    if not url:
        return (False, "Не удалось открыть документацию")

    try:
        import webbrowser

        webbrowser.open(url)
    except Exception as exc:
        return (False, f"Не удалось открыть браузер: {exc}")

    return (True, url)


__all__ = [
    "PORT_ATTEMPTS",
    "PREFERRED_PORT",
    "docs_root",
    "is_available",
    "open_in_browser",
    "start",
    "stop",
]
