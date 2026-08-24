"""Внутренние файлы не должны попадать в публичный репозиторий.

Репозиторий `defl0r1an/net67` открыт: его видно всем. Часть файлов в
рабочей папке предназначена только для работы — записка о переносе
проекта на другой компьютер, конфигурация помощника, сгенерированные
номера сборки.

HANDOVER.md убирали из публикации один раз, отдельным коммитом. Он
вернулся со следующим `git add -A`: файл удалили, а правило в .gitignore
не завели, и ничто не мешало добавить его снова. Заметил это владелец
репозитория, а не проверка.

Поэтому здесь два требования сразу: файла нет среди отслеживаемых И на
него стоит правило. Первого без второго не хватает.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Файлы, которых в публичном репозитории быть не должно.
PRIVATE_FILES = (
    "HANDOVER.md",
    "CLAUDE.md",
    "AGENTS.md",
    "src/config/build_info.py",
    "src/config/_build_secrets.py",
)


def _tracked() -> set[str]:
    """Отслеживаемые файлы, с настоящими именами.

    Обязательно `-z`: без него git подменяет всё, что вне ASCII, на
    экранированные последовательности вида `"C\\357\\200\\272..."`. Проверка
    имён при этом смотрела бы на обратные слэши вместо самих символов и
    ничего бы не находила — именно на этом она у меня и промолчала.
    """
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8", errors="surrogateescape")
    return {name for name in output.split("\0") if name}


def _is_ignored(relative: str) -> bool:
    """Сработает ли на файл правило .gitignore.

    Спрашиваем сам git, а не разбираем .gitignore руками: у правил свой
    синтаксис с отрицаниями и порядком, и своя реализация тут ошиблась бы
    ровно на тех случаях, ради которых проверка и нужна.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", relative],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )
    return result.returncode == 0


class TranslatedNameTests(unittest.TestCase):
    """Имена, появившиеся из-за переноса тома между системами.

    Двоеточие и обратный слэш в именах файлов Windows запрещены. Когда
    папку видно и из Windows, и из Linux, такие символы подменяются
    знаками из области частного использования Unicode (U+E000..U+F8FF).

    В обычном имени файла им взяться неоткуда. Зато так выглядит имя,
    которое на одной стороне было путём, а на другой стало одним куском:
    `C:\\Windows\\System32\\drivers\\etc\\hosts` уехал в публичный выпуск
    ровно этим способом. Правило .gitignore, написанное с настоящим
    двоеточием, ловило его только в Linux, а добавляли файл из Windows.
    """

    PRIVATE_USE_AREA = range(0xE000, 0xF900)

    def test_no_translated_characters_in_tracked_names(self) -> None:
        offenders = [
            name
            for name in _tracked()
            if any(ord(char) in self.PRIVATE_USE_AREA for char in name)
        ]

        self.assertEqual(
            sorted(offenders),
            [],
            "в репозиторий попало имя, собранное из пути: " + ", ".join(sorted(offenders)),
        )


class PrivateFilesTests(unittest.TestCase):
    def test_none_of_them_are_tracked(self) -> None:
        tracked = _tracked()
        leaked = sorted(name for name in PRIVATE_FILES if name in tracked)

        self.assertEqual(
            leaked,
            [],
            "внутренние файлы попали в репозиторий: " + ", ".join(leaked),
        )

    def test_each_of_them_is_ignored(self) -> None:
        """Без правила файл вернётся при первом же `git add -A`."""
        unguarded = sorted(name for name in PRIVATE_FILES if not _is_ignored(name))

        self.assertEqual(
            unguarded,
            [],
            "нет правила в .gitignore для: " + ", ".join(unguarded),
        )


if __name__ == "__main__":
    unittest.main()
