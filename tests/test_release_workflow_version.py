"""Номер версии в собранном приложении.

Версия живёт в одном файле — `src/config/build_info.py`, — и он
генерируется на сборке. Значит, проверять надо не файл, а три места,
которые его пишут: заглушку для тестов, локальный сборочный скрипт и
рабочий процесс GitHub.

Разъехавшись, эти три числа превращают любой отчёт об ошибке в загадку:
человек называет версию из окна «О программе», а выпуска с таким
номером на GitHub нет.

Отдельно проверяется разбор тега. Тег пишет человек, и пишет он то
`v0.3.67`, то `0.3.67`. Первый вариант разбора срезал первый символ у
всего подходящего подряд, и тег без буквы превращался в `.2.67` —
номер, который уехал бы в выпуск незамеченным.
"""

from __future__ import annotations

import os
import pathlib
import re
import tempfile
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Ожидаемая версия. Меняя её, поменяйте и в трёх местах ниже — тест
#: для того и написан, чтобы не дать поменять в одном.
EXPECTED_VERSION = "0.3.67"

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "windows-release.yml"


def _generate_step_source() -> str:
    """Код шага, который пишет build_info.py в рабочем процессе."""
    import yaml

    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["build"]["steps"]
    for step in steps:
        if step.get("name") == "Generate build files":
            return step["run"]
    raise AssertionError("в рабочем процессе нет шага генерации файлов сборки")


def _version_for_tag(tag: str) -> str:
    """Прогоняет шаг рабочего процесса и читает, что он записал."""
    source = _generate_step_source()
    with tempfile.TemporaryDirectory() as directory:
        previous_cwd = os.getcwd()
        previous_tag = os.environ.get("GITHUB_REF_NAME")
        os.chdir(directory)
        os.environ["GITHUB_REF_NAME"] = tag
        try:
            exec(compile(source, "windows-release.yml", "exec"), {"__name__": "__main__"})
            written = (
                pathlib.Path(directory, "src", "config", "build_info.py")
                .read_text(encoding="utf-8-sig")
            )
        finally:
            os.chdir(previous_cwd)
            if previous_tag is None:
                os.environ.pop("GITHUB_REF_NAME", None)
            else:
                os.environ["GITHUB_REF_NAME"] = previous_tag

    match = re.search(r"APP_VERSION\s*=\s*'([^']*)'", written)
    assert match is not None, written
    return match.group(1)


class SourcesOfTheVersionAgreeTests(unittest.TestCase):
    def test_stub_for_tests_carries_the_current_version(self) -> None:
        text = (PROJECT_ROOT / "src" / "config" / "build_info.py").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(f'APP_VERSION = "{EXPECTED_VERSION}"', text)

    def test_local_build_script_writes_the_same_version(self) -> None:
        """Скрипт пишет build_info.py, когда файла нет.

        Там стояла заглушка 1.0.0.0, и чистая сборка молча сбрасывала
        номер на неё.
        """
        text = (PROJECT_ROOT / "scripts" / "build_local.ps1").read_text(
            encoding="utf-8", errors="replace"
        )

        self.assertIn(f'APP_VERSION = "{EXPECTED_VERSION}"', text)

    def test_workflow_fallback_is_the_same_version(self) -> None:
        """Сборка по push в main тега не имеет.

        Раньше туда шёл ноль, и в окне «О программе» стояло 0.0.0.0 —
        читается как «версия не определилась».
        """
        self.assertEqual(_version_for_tag("main"), EXPECTED_VERSION)


class TagParsingTests(unittest.TestCase):
    def test_tag_with_the_letter_v(self) -> None:
        self.assertEqual(_version_for_tag("v0.3.67"), "0.3.67")

    def test_tag_without_the_letter_v(self) -> None:
        """Тот самый случай, где номер терял первую цифру."""
        self.assertEqual(_version_for_tag("0.3.67"), "0.3.67")

    def test_four_part_number(self) -> None:
        """Прежний проект нумеровался четырьмя частями."""
        self.assertEqual(_version_for_tag("v1.4.0.2"), "1.4.0.2")

    def test_a_branch_name_is_not_a_version(self) -> None:
        for tag in ("main", "v", "release-0.3.67", ""):
            with self.subTest(tag=tag):
                self.assertEqual(_version_for_tag(tag), EXPECTED_VERSION)


class SecretsStubTests(unittest.TestCase):
    """Заглушка секретов в CI должна совпадать по составу с настоящей."""

    def _names(self, source: str) -> set[str]:
        namespace: dict = {}
        exec(source, namespace)
        return {name for name in namespace if not name.startswith("__")}

    def test_ci_stub_has_every_field_the_code_imports(self) -> None:
        """Не хватало PROXY_PRESETS и MTPROXY_LINK.

        Собранное в CI приложение падало бы при первом заходе на
        страницу Telegram-прокси — то есть у того, кто скачал выпуск, а
        не у нас.
        """
        real = (PROJECT_ROOT / "src" / "config" / "_build_secrets.py").read_text(
            encoding="utf-8-sig"
        )
        with tempfile.TemporaryDirectory() as directory:
            previous_cwd = os.getcwd()
            os.chdir(directory)
            try:
                exec(
                    compile(_generate_step_source(), "windows-release.yml", "exec"),
                    {"__name__": "__main__"},
                )
                ci = pathlib.Path(
                    directory, "src", "config", "_build_secrets.py"
                ).read_text(encoding="utf-8-sig")
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(self._names(ci), self._names(real))

    def test_no_paid_access_field_survives(self) -> None:
        """Платного доступа в net67 нет; поле было бы приглашением его вернуть."""
        for path in (
            PROJECT_ROOT / "src" / "config" / "_build_secrets.py",
            WORKFLOW,
        ):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8-sig", errors="replace")
                body = "\n".join(
                    line
                    for line in text.splitlines()
                    if not line.lstrip().startswith("#")
                )
                self.assertNotIn("PREMIUM_API_BASE_URL", body)


if __name__ == "__main__":
    unittest.main()
