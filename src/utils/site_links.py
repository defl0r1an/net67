"""Справочные ссылки открываются в фоне через общий запуск браузера net67.

Для своей вики не нужны имена зеркал другого проекта. Ошибка запуска
попадает в журнал и колокольчик, а поиск браузера не задерживает окно.
"""

from __future__ import annotations

from threading import Thread


def _open(url: str) -> None:
    from app.external_commands import open_url
    from log.log import log

    try:
        result = open_url(url)
        if not result.ok:
            log(f"Не удалось открыть справочную ссылку {url}: {result.error}", "ERROR")
    except Exception as error:
        log(f"Не удалось открыть справочную ссылку {url}: {error}", "ERROR")


def open_in_browser(url: str) -> None:
    target = str(url or "").strip()
    if target:
        Thread(target=_open, args=(target,), name="net67-help-link", daemon=True).start()


__all__ = ["open_in_browser"]
