"""Показывает окно «Доступно обновление» отдельно от программы.

В самой программе окно появляется, только когда вышла версия новее
установленной, — посмотреть на него в обычный день нельзя. Скрипт
открывает его с настоящими выпусками с GitHub и притворяется старой
версией, чтобы в окне были и новые выпуски, и раздел «Ранее».

    py -3.14 tools/preview_update_dialog.py            # как будто стоит 0.11.67
    py -3.14 tools/preview_update_dialog.py 0.12.67    # как будто стоит 0.12.67
    py -3.14 tools/preview_update_dialog.py --whats-new  # окно «Что нового»

Ничего не скачивает и не устанавливает: кнопки только закрывают окно, а
выбранный ответ печатается в консоль.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

#: Запасные выпуски — если GitHub не ответил (нет сети, лимит запросов).
SAMPLE_RELEASES = [
    {"version": "0.13.67", "published_at": "2026-10-02T08:19:51Z", "release_notes": "- Кнопка проверки DNS-профилей на плитках hosts.\n- Установщик в виде net67."},
    {"version": "0.12.67", "published_at": "2026-09-30T09:52:18Z", "release_notes": "- Меньше памяти в фоне."},
    {"version": "0.11.67", "published_at": "2026-09-02T05:46:00Z", "release_notes": "- Steam убран из пресета по умолчанию."},
]


def _releases() -> list[dict]:
    try:
        from updater.github_release import get_all_releases_with_exe

        releases = [item for item in (get_all_releases_with_exe() or ()) if isinstance(item, dict)]
        if releases:
            return releases
    except Exception as exc:
        print(f"GitHub не ответил ({exc}) — показываю пример")
    return list(SAMPLE_RELEASES)


def main(argv: list[str]) -> int:
    from PyQt6.QtWidgets import QApplication, QWidget
    from qfluentwidgets import Theme, setTheme

    from updater import release_notes
    from updater.server_config import GITHUB_REPO
    from updater.ui.update_dialog import ask_update, show_whats_new

    whats_new = "--whats-new" in argv
    versions = [arg for arg in argv[1:] if not arg.startswith("-")]
    pretend = versions[0] if versions else "0.11.67"

    app = QApplication(argv)
    setTheme(Theme.DARK)
    host = QWidget()
    host.setWindowTitle("net67 — просмотр окна обновления")
    host.setStyleSheet("background: #202020;")
    host.resize(1280, 820)
    host.show()

    releases = _releases()
    target = max((str(item.get("version") or "") for item in releases), key=release_notes.version_key)
    history = release_notes.build_history(releases, current_version=pretend, target_version=target, repo=GITHUB_REPO)
    latest = next((item for item in releases if str(item.get("version") or "").lstrip("v") == target), {})

    if whats_new:
        dialog = show_whats_new(host, version=target, history=history)
        dialog.finished.connect(lambda _code: app.quit())
        return app.exec()

    action = ask_update(
        host,
        current_version=pretend,
        target_version=target,
        history=history,
        source="GitHub",
        release_url=release_notes.release_page_url(target, GITHUB_REPO),
        file_name=str(latest.get("file_name") or ""),
        file_size=latest.get("file_size") or 0,
    )
    print(f"Ответ окна: {action}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
