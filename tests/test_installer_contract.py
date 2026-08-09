"""Установщик должен знать те же имена, что и приложение.

Установщик живёт отдельным файлом на другом языке, и связь с кодом у него
только по совпадению строк. Переименуют задачу автозапуска или службу —
приложение продолжит работать, а деинсталлятор молча оставит их в системе.
Через месяц у двадцати менеджеров в планировщике висит задача, которая
запускает удалённую программу.

Здесь же зафиксировано, что переживает обновление: пресеты, списки и
настройки. Один лишний путь в [InstallDelete] стирает чужую работу без
предупреждения.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

ISS_PATH = PROJECT_ROOT / "installer" / "net67.iss"
CLEAR_HOSTS_PATH = PROJECT_ROOT / "installer" / "clear_hosts.ps1"


def _iss() -> str:
    return ISS_PATH.read_text(encoding="utf-8")


def _section(name: str) -> str:
    """Тело секции .iss.

    Ищем заголовок строго с начала строки: слово «[InstallDelete]»
    встречается и в комментарии внутри [Files], и поиск подстрокой ловил
    именно его — тест «обновление стирает presets\\winws1» падал на
    списке файлов, а не на списке удаления.
    """
    source = _iss()
    header = re.search(rf"^\[{re.escape(name)}\]\s*$", source, re.M)
    if header is None:
        raise AssertionError(f"в net67.iss нет секции [{name}]")
    rest = source[header.end():]
    following = re.search(r"^\[[A-Za-z]+\]\s*$", rest, re.M)
    return rest[: following.start()] if following else rest


class InstallerExistsTests(unittest.TestCase):
    def test_files_are_in_place(self) -> None:
        self.assertTrue(ISS_PATH.is_file(), "installer\\net67.iss отсутствует")
        self.assertTrue(CLEAR_HOSTS_PATH.is_file(), "installer\\clear_hosts.ps1 отсутствует")
        self.assertTrue((PROJECT_ROOT / "scripts" / "build_installer.ps1").is_file())


class NamesMatchTheApplicationTests(unittest.TestCase):
    def test_autostart_task_name(self) -> None:
        from autostart.scheduled_task_api import AUTOSTART_TASK_NAME

        self.assertIn(AUTOSTART_TASK_NAME, _iss())

    def test_telegram_proxy_service_name(self) -> None:
        from telegram_proxy.service import TG_SERVICE_NAME

        self.assertIn(TG_SERVICE_NAME, _iss())

    def test_windivert_service_names(self) -> None:
        """Движок переименовывает драйвер, поэтому вариантов несколько."""
        source = _iss()
        for name in ("Monkey", "Monkey64", "WinDivert", "WinDivert14", "WinDivert64"):
            self.assertIn(f"delete {name}", source, f"драйвер {name} не удаляется")

    def test_hosts_markers_match_the_writer(self) -> None:
        import hosts.hosts as hosts_module

        script = CLEAR_HOSTS_PATH.read_text(encoding="utf-8")
        for marker in (
            hosts_module._MANAGED_HOSTS_BEGIN,
            hosts_module._MANAGED_HOSTS_END,
            hosts_module._LEGACY_MANAGED_HOSTS_BEGIN,
            hosts_module._LEGACY_MANAGED_HOSTS_END,
        ):
            self.assertIn(marker, script, f"маркер не знаком чистильщику: {marker}")

    def test_executable_name_matches_branding(self) -> None:
        from branding import APP_SLUG

        self.assertIn(f"{APP_SLUG}.exe", _iss())


class UserDataSurvivesUpgradeTests(unittest.TestCase):
    """Пользовательские папки не должны попадать в очистку."""

    PROTECTED = (
        r"presets\winws1",
        r"presets\winws2",
        r"lists\user",
        r"settings",
    )

    def test_protected_folders_are_not_deleted(self) -> None:
        block = _section("InstallDelete")
        for path in self.PROTECTED:
            self.assertNotIn(path, block, f"обновление стирает {path}")

    def test_internal_is_replaced_wholesale(self) -> None:
        """Старые .pyd от прежней версии рядом с новыми — источник падений."""
        self.assertIn(r"{app}\_internal", _section("InstallDelete"))

    def test_writable_dirs_are_declared(self) -> None:
        """Program Files не даёт создавать папки без прав."""
        block = _section("Dirs")
        for path in self.PROTECTED + (r"logs", r"tmp"):
            self.assertIn(path, block, f"папка {path} не создаётся установщиком")
        self.assertIn("users-modify", block)


class AdminAndLaunchTests(unittest.TestCase):
    def test_requires_admin(self) -> None:
        """WinDivert - драйвер ядра, без прав он не поставится."""
        self.assertIn("PrivilegesRequired=admin", _iss())

    def test_launches_from_internal(self) -> None:
        """resolve_application_root() пускает только из _internal."""
        source = _iss()
        self.assertIn(r"{app}\_internal\{#AppExeName}", source)
        for line in source.splitlines():
            if line.startswith("Filename:") and "AppExeName" in line:
                self.assertIn("_internal", line, f"запуск мимо _internal: {line}")

    def test_artifact_is_copied_wholesale(self) -> None:
        """Перечисление папок по одной уже подводило.

        windivert.filter — папка с наборами фильтров, а не файл, и
        компилятор встал на «Source file does not exist». Любая новая
        папка в артефакте так же молча не доехала бы до установки.
        """
        block = _section("Files")

        self.assertIn(r'Source: "{#SourceDir}\*"; DestDir: "{app}"', block)
        self.assertIn("recursesubdirs", block)
        self.assertIn("Excludes:", block)

    def test_user_folders_are_excluded_from_the_copy(self) -> None:
        """Приложение запускают прямо из артефакта и пишет туда настройки.

        Один такой запуск — и установщик разослал бы двадцати менеджерам
        чужой settings.json поверх их собственного.
        """
        block = _section("Files")
        excludes = re.search(r'Excludes:\s*"([^"]+)"', block)

        self.assertIsNotNone(excludes, "в [Files] нет списка исключений")
        listed = excludes.group(1)
        for path in UserDataSurvivesUpgradeTests.PROTECTED:
            self.assertIn(path, listed, f"{path} попадёт в установщик")


if __name__ == "__main__":
    unittest.main()
