"""Имени исходного проекта не должно остаться там, где его видно.

Проверка появилась после того, как владелец приложения открыл системный
файл hosts и увидел там строку «# MAX BLOCKED BY ZAPRET GUI». Блокировка
MAX писала метку с именем проекта, из которого net67 сделан.

Одной этой строкой дело не ограничилось. Рядом нашлись: такая же метка у
блокировщика государственных СМИ, телеграм-каналы прежнего автора в
качестве источника обновлений, шаблоны обращений на GitHub и десяток
внутренних имён в коде.

## Что здесь проверяется, а что нет

Проверяется код и данные, которые видит человек: метки в системных
файлах, тексты, адреса. Такое возвращается легко — достаточно скопировать
кусок старого кода вместе с константой.

Не проверяются два места, и это осознанно.

Первое — имена, оставленные ради уборки за прежней версией: задача
автозапуска `ZapretGUI Autostart`, ярлык `ZapretGUI.lnk`, старые метки в
hosts. Их нельзя переименовать, иначе следы прежней установки останутся
у людей навсегда: искать их будет нечем. Они перечислены поимённо.

Второе — авторы стратегий обхода (Flowseal, bol-van, censorliber) в
`json/index.json` и каталогах стратегий. Это не наследие бренда, а
указание авторства чужой работы, которую приложение раздаёт вместе с
собой. Убирать его — отдельное решение, и не техническое.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Что ищем. Имя прежнего проекта в любом написании.
FORBIDDEN = re.compile(r"zapret\s*gui|zapretgui", re.IGNORECASE)

#: Где имя разрешено, и почему.
ALLOWED: dict[str, str] = {
    "src/autostart/scheduled_task_api.py": (
        "имя задачи прежней версии — нужно, чтобы её удалить из планировщика"
    ),
    "src/autostart/startup_shortcut_api.py": (
        "имя ярлыка прежней версии — нужно, чтобы удалить его из автозагрузки"
    ),
    "src/hosts/hosts.py": "старые метки блока hosts — нужны, чтобы его вычистить",
    "src/windows_features/state_media_blocker.py": (
        "старые метки блока hosts — нужны, чтобы его вычистить"
    ),
    "src/windows_features/max_blocker.py": (
        "старые метки блока hosts — нужны, чтобы его вычистить"
    ),
    "installer/clear_hosts.ps1": "старые метки блока hosts — нужны, чтобы его вычистить",
    "tests/test_no_previous_project_name.py": "сама эта проверка",
    "tests/test_state_media_blocker.py": "проверка уборки старого блока",
    "tests/test_hosts_catalog_json.py": "проверка, что старая метка больше не пишется",
    "tests/test_max_blocker_hosts_marker.py": "проверка уборки старого блока",
    "tests/test_gui_autostart_contract.py": "проверка удаления прежней задачи и ярлыка",
    "tests/test_close_dialog_accessibility.py": "рассказ о том, как имя однажды протухло",
    "tests/test_build_resource_layout.py": "проверки сборочной системы прежнего проекта",
    "tests/test_builtin_profile_catalog.py": "проверка раскладки списков",
    "tests/test_quick_actions_bar_layout.py": "проверка прежнего текста",
    "tests/test_win11_toggle_row.py": "проверка прежнего текста",
}


def _tracked_files() -> list[str]:
    output = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in output.splitlines() if line.strip()]


class PreviousProjectNameTests(unittest.TestCase):
    def test_no_stray_mentions(self) -> None:
        offenders: list[str] = []

        for relative in _tracked_files():
            if relative in ALLOWED:
                continue
            path = PROJECT_ROOT / relative
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, IsADirectoryError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if FORBIDDEN.search(line):
                    offenders.append(f"{relative}:{number}: {line.strip()[:100]}")

        self.assertEqual(
            offenders,
            [],
            "имя исходного проекта вернулось:\n" + "\n".join(offenders),
        )

    def test_allow_list_stays_honest(self) -> None:
        """Разрешение без надобности — это забытая уборка.

        Список исключений разрастается сам собой: проще дописать файл,
        чем разобраться. Проверка не даёт ему копиться из мёртвых строк.
        """
        stale: list[str] = []

        for relative in ALLOWED:
            path = PROJECT_ROOT / relative
            if not path.exists():
                stale.append(f"{relative}: файла нет")
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if not FORBIDDEN.search(text):
                stale.append(f"{relative}: имени больше нет, разрешение лишнее")

        self.assertEqual(stale, [], "\n".join(stale))


class UpdateSourceTests(unittest.TestCase):
    """Обновления не должны вести в чужой телеграм."""

    def test_no_foreign_update_channels(self) -> None:
        from updater.telegram_updater import TELEGRAM_CHANNELS

        for key, name in TELEGRAM_CHANNELS.items():
            with self.subTest(channel=key):
                self.assertNotIn("zapret", str(name).lower())

    def test_empty_channel_is_skipped_not_requested(self) -> None:
        """Пустое имя не должно превращаться в запрос на https://t.me/s/."""
        import inspect

        from updater import telegram_updater

        source = inspect.getsource(telegram_updater._parse_telegram_web)
        head = source[: source.index("https://t.me/s/")]

        self.assertIn("if not channel_name:", head)

    def test_open_channel_reports_that_it_is_not_configured(self) -> None:
        from updater.commands import open_update_channel

        result = open_update_channel("stable")

        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
