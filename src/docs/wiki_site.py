"""Документация net67 — сайт в интернете.

Вики ехала вместе с программой: папка `docs` рядом с исполняемым файлом
и маленький сервер на 127.0.0.1, который её отдавал. Так она открывалась
без интернета и всегда совпадала с установленной версией.

С 1 октября 2026 вики опубликована на GitHub Pages, и владелец решил
держать её в одном месте: кнопка «Документация» и «Подробнее в вики» в
экскурсии ведут на сайт, встроенной копии и сервера больше нет. Статью,
поправленную сегодня, человек видит сегодня же, а не после обновления
программы; сборка легче на сотню файлов.

Цена — без интернета документация не откроется. Для программы, которая
чинит доступ в интернет, это честная оговорка: браузер покажет свою
страницу «нет подключения», программа при этом ни при чём.

Адрес сайта — `DOCS_URL` в branding.py. Пусто — кнопок нет вовсе.
"""

from __future__ import annotations

from urllib.parse import quote

from log.log import log


def base_url() -> str:
    """Адрес сайта с косой чертой на конце; пустая строка — сайта нет."""
    from branding import DOCS_URL

    url = str(DOCS_URL or "").strip()
    if not url:
        return ""
    return url if url.endswith("/") else url + "/"


def page_url(page: str) -> str:
    """Адрес статьи вики; пустая строка — сайта нет.

    ``page`` — как в ссылках самой вики: ``presets`` или ``presets#фейки``.
    Страницу ``index`` отдаёт корень сайта.

    Есть ли такая статья и заголовок, здесь не проверяется: сайта под
    рукой нет. Это делает tests/test_onboarding_wiki_links.py — по
    исходникам статей в wiki/content.
    """
    base = base_url()
    if not base:
        return ""
    path, _, anchor = str(page or "").strip().lstrip("/").partition("#")
    url = base if path in ("", "index") else base + quote(path, safe="/")
    if anchor:
        url += "#" + quote(anchor, safe="-")
    return url


def open_in_browser(page: str = "") -> tuple[bool, str]:
    """Открывает документацию в браузере. Возвращает (получилось, адрес или причина)."""
    url = page_url(page)
    if not url:
        return (False, "Адрес документации не задан")
    try:
        import webbrowser

        webbrowser.open(url)
    except Exception as exc:
        return (False, f"Не удалось открыть браузер: {exc}")
    log(f"Открыта документация: {url}", "INFO")
    return (True, url)


__all__ = ["base_url", "open_in_browser", "page_url"]
