"""Выкладывает собранную вики на сайт: https://defl0r1an.github.io/net67/

    py wiki\\publish.py

Сначала сайт надо собрать — `Пересобрать сайт.cmd` рядом.

## Что делает

Сайт живёт в ветке `gh-pages` репозитория: GitHub Pages отдаёт её как
есть. В ветке только готовые страницы — содержимое папки `site` — и
пустой файл `.nojekyll`. Кода программы в ней нет.

Ветка каждый раз собирается заново: один коммит поверх пустоты, с
принудительной отправкой. История собранных страниц никому не нужна —
она есть у статей в `wiki/content`, из которых сайт собирается.

Собирается ветка во временной папке, отдельным репозиторием. Рабочий
клон при этом не трогается: ни ветки в нём, ни индекс, ни файлы.

## Чего не делает

Не собирает сайт сам и не проверяет статьи — только отправляет то, что
лежит в `site`. Недособранный сайт (css есть, страниц нет) не отправит:
после неудачной сборки Quartz в папке остаются стили и одинокий 404.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SITE = Path(__file__).resolve().parent / "site"
REMOTE = "https://github.com/defl0r1an/net67"
BRANCH = "gh-pages"

#: Автор коммита — как у всех коммитов проекта.
AUTHOR = ("defl0r1an", "defl0r1an@users.noreply.github.com")

#: Меньше страниц — сборка оборвалась.
MIN_PAGES = 10


def _git(folder: Path, *args: str) -> None:
    command = [
        "git",
        "-c", f"user.name={AUTHOR[0]}",
        "-c", f"user.email={AUTHOR[1]}",
        # Страницы уходят байт в байт: перевод строк им ни к чему.
        "-c", "core.autocrlf=false",
        *args,
    ]
    subprocess.run(command, cwd=folder, check=True)


def main() -> int:
    pages = sorted(SITE.glob("*.html")) if SITE.is_dir() else []
    if not (SITE / "index.html").is_file() or len(pages) < MIN_PAGES:
        print(f"Сайт не собран: в {SITE} страниц {len(pages)}. Запустите «Пересобрать сайт.cmd».", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="net67-wiki-") as tmp:
        folder = Path(tmp) / "site"
        shutil.copytree(SITE, folder)
        # Без него GitHub прогоняет страницы через Jekyll и теряет файлы,
        # чьи имена начинаются с подчёркивания.
        (folder / ".nojekyll").write_text("", encoding="utf-8")
        _git(folder, "init", "-q", "-b", BRANCH)
        _git(folder, "add", "-A")
        _git(
            folder,
            "commit", "-q",
            "-m", "Вики net67: собранный сайт для GitHub Pages",
            "-m", "Собрано из wiki/content движком Quartz. Источник статей — ветка main; "
                  "эта ветка только публикует готовые страницы.",
        )
        _git(folder, "push", "--force", REMOTE, f"{BRANCH}:{BRANCH}")

    print(f"Отправлено страниц: {len(pages)}. Через минуту сайт обновится: https://defl0r1an.github.io/net67/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
