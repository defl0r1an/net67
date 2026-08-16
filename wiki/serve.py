"""Открывает собранную вики в браузере.

Запускать не обязательно из командной строки — рядом лежит
`Открыть сайт.cmd`, он делает то же самое двойным щелчком.

## Зачем вообще сервер

Открыть `site\\index.html` файлом в браузере не получится: ссылки внутри
сайта ведут на `./vpn`, а не на `./vpn.html`. Так устроен генератор — он
рассчитан на веб-сервер, который сам подставляет расширение.

Встроенного в Python сервера тоже не хватает: он отдаёт файлы как есть и
на `/vpn` отвечает «404 не найдено». Поэтому здесь свой обработчик — он
добавляет `.html`, если файла без расширения нет.

## Ничего наружу не открывается

Сервер слушает только 127.0.0.1 — адрес самого компьютера. Из сети к
нему не подключиться, даже из локальной.
"""

from __future__ import annotations

import http.server
import socketserver
import threading
import webbrowser
from pathlib import Path


#: Порт. Занят — возьмём следующий свободный.
PORT = 8317

#: Папка с собранным сайтом.
SITE_DIR = Path(__file__).resolve().parent / "site"


class Handler(http.server.SimpleHTTPRequestHandler):
    """Отдаёт `vpn.html`, когда просят `/vpn`."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(SITE_DIR), **kwargs)

    def translate_path(self, path: str) -> str:
        result = Path(super().translate_path(path))

        if result.is_dir() or result.exists():
            return str(result)

        # Ссылки внутри сайта расширения не содержат.
        with_html = result.with_name(result.name + ".html")
        if with_html.exists():
            return str(with_html)

        return str(result)

    def log_message(self, *_args) -> None:
        # Тишина: окно нужно для того, чтобы сервер жил, а не для чтения.
        pass


def _free_port(start: int) -> int:
    import socket

    for candidate in range(start, start + 20):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return candidate
    return start


def main() -> int:
    if not SITE_DIR.is_dir():
        print(f"Нет папки с сайтом: {SITE_DIR}")
        print("Соберите сайт заново — как, написано в wiki\\README.md")
        input("Enter чтобы закрыть...")
        return 1

    port = _free_port(PORT)
    address = f"http://127.0.0.1:{port}/"

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as server:
        print(f"Вики net67 открыта: {address}")
        print("Закройте это окно, когда закончите.")
        threading.Timer(0.7, lambda: webbrowser.open(address)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
