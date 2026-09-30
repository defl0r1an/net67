# tests/test_intrusive_defaults_are_off.py
"""Настройки, которые лезут наружу, по умолчанию выключены.

Две таких включались сами:

Прокси Telegram поднимался при каждом запуске программы. Тумблер
«Прокси Telegram вместе с обходом» при этом стоял в «выкл.», и со
стороны это выглядело как сломанная настройка: человек её не включал, а
прокси всё равно висел на порту.

Перезапуск Discord закрывал чужое приложение и открывал заново — при
каждой смене стратегии. Человек, который про настройку не знал, видел
просто оборвавшийся звонок.

Общее правило простое: если настройка трогает что-то за пределами
нашего окна, включать её должен человек, а не мы за него. Проверяется
здесь именно оно, а не конкретные две галки: умолчание живёт в пяти
местах сразу, и вернуть его случайно легко.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


class SchemaTests(unittest.TestCase):
    def test_discord_restart_is_off_in_the_schema(self) -> None:
        from settings.schema import default_program

        self.assertFalse(default_program()["discord_auto_restart"])

    def test_telegram_proxy_is_off_in_the_schema(self) -> None:
        from settings.schema import default_telegram_proxy

        self.assertFalse(
            default_telegram_proxy()["enabled"],
            "прокси Telegram снова поднимается при каждом запуске",
        )

    def test_telegram_proxy_with_bypass_is_off(self) -> None:
        from settings.schema import default_program

        self.assertFalse(default_program()["telegram_proxy_with_bypass"])


class ReadersTests(unittest.TestCase):
    """Читатели настройки обязаны согласовываться со схемой.

    Умолчание записано не только в схеме: у каждого читателя свой
    запасной вариант на случай, когда ключа в файле ещё нет. Разойдутся
    — и настройка будет включена ровно до первого сохранения, то есть
    у всех, кто её не трогал.
    """

    def test_store_readers_default_to_off(self) -> None:
        from settings import store

        source = Path(store.__file__).read_text(encoding="utf-8")
        self.assertIn('_get_bool(("program", "discord_auto_restart"), False)', source)
        self.assertIn('_get_bool(("telegram_proxy", "enabled"), False)', source)

    def test_no_reader_still_defaults_to_true(self) -> None:
        """Сплошная проверка: ищем любой забытый `default=True`."""
        offenders = []
        for path in (REPO_ROOT / "src").rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8-sig")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if "discord_restart" not in line and "discord_auto_restart" not in line:
                    continue
                stripped = line.strip()
                if "default=True" in stripped or "), True)" in stripped:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}: {stripped}")

        self.assertEqual(offenders, [], "\n" + "\n".join(offenders))


class WizardSwitchTests(unittest.TestCase):
    """Переключатели первичной настройки подписаны по-русски.

    Вопросы бывшего мастера теперь на карточках тура, и переключатели там
    создаются напрямую, а не через Win11ToggleRow — оттуда брались
    английские «On» и «Off» посреди русского окна.
    """

    SOURCE = REPO_ROOT / "src" / "ui" / "onboarding" / "setup_choices.py"

    def test_the_dialog_exists(self) -> None:
        self.assertTrue(self.SOURCE.is_file(), f"не найден {self.SOURCE}")

    def test_switches_are_built_through_the_russian_factory(self) -> None:
        source = self.SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)

        bare = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "SwitchButton":
                continue
            # Единственный законный вызов — внутри самой фабрики.
            bare.append(node.lineno)

        factory_line = source[: source.index("def _switch()")].count("\n") + 1
        outside = [line for line in bare if not factory_line <= line <= factory_line + 30]
        self.assertEqual(outside, [], f"SwitchButton без русских подписей в строках {outside}")

    def test_the_factory_sets_both_captions(self) -> None:
        source = self.SOURCE.read_text(encoding="utf-8")
        self.assertIn("setOnText(SWITCH_ON_TEXT)", source)
        self.assertIn("setOffText(SWITCH_OFF_TEXT)", source)

    def test_captions_are_russian(self) -> None:
        # Файл читаем текстом: импорт модуля потянул бы Qt с
        # графическими библиотеками, а проверка — про две строки.
        source = self.SOURCE.read_text(encoding="utf-8")
        self.assertIn('SWITCH_ON_TEXT = "Вкл."', source)
        self.assertIn('SWITCH_OFF_TEXT = "Выкл."', source)


if __name__ == "__main__":
    unittest.main()
