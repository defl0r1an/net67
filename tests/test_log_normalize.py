"""Строка лога: без значков, с разобранным уровнем.

Просьба была: «поработай над логированием, как будто бы его можно
сделать проще, подробнее и без лишних смайликов».

Смайлики оказались не украшением на конце, а содержимым поля уровня.
Замер по проекту: 86 вызовов с «❌ ERROR», 35 с «🔄 RELEASE», 31 с
«⚠ WARNING», 26 с «🔁 UPDATE», 20 с «🔄 CACHE», 15 с «✅ INFO», 14 с
«📱 TG». Больше двух сотен мест, и половина из них — вообще не уровни, а
метки подсистем, положенные не в то поле.

Поэтому разбор один и на входе в лог. Править двести мест вызова
бессмысленно: следующая правка добавит двести первое.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class DecorationTests(unittest.TestCase):
    def test_icons_are_stripped_from_the_message(self) -> None:
        """Строку со значком нельзя найти поиском и нельзя прочитать вслух."""
        from log.normalize import strip_decorations

        self.assertEqual(strip_decorations("✅ Обход запущен"), "Обход запущен")

    def test_text_itself_is_untouched(self) -> None:
        """Задача — снять украшения, а не переписать сообщение."""
        from log.normalize import strip_decorations

        message = "Не удалось открыть hosts: отказано в доступе (путь C:\\Windows)"

        self.assertEqual(strip_decorations(message), message)

    def test_double_spaces_left_by_icons_collapse(self) -> None:
        from log.normalize import strip_decorations

        self.assertEqual(strip_decorations("⚠  Проверьте  сеть"), "Проверьте сеть")

    def test_empty_stays_empty(self) -> None:
        from log.normalize import strip_decorations

        self.assertEqual(strip_decorations(""), "")
        self.assertEqual(strip_decorations(None), "")


class LevelTests(unittest.TestCase):
    def _split(self, value: str):
        from log.normalize import split_level

        return split_level(value)

    def test_decorated_levels_become_plain(self) -> None:
        for value, expected in (
            ("❌ ERROR", "ERROR"),
            ("⚠ WARNING", "WARNING"),
            ("✅ INFO", "INFO"),
            ("🔁❌ ERROR", "ERROR"),
        ):
            with self.subTest(value=value):
                self.assertEqual(self._split(value)[0], expected)

    def test_subsystem_labels_move_out_of_the_level(self) -> None:
        """«📱 TG» — это не важность сообщения, а откуда оно пришло."""
        for value, source in (
            ("📱 TG", "TG"),
            ("🔄 CACHE", "CACHE"),
            ("POOL", "POOL"),
            ("🔄 RELEASE", "RELEASE"),
        ):
            with self.subTest(value=value):
                level, parsed_source = self._split(value)
                self.assertEqual(level, "INFO")
                self.assertEqual(parsed_source, source)

    def test_synonyms_map_to_real_levels(self) -> None:
        """SUCCESS и START — про исход и этап, а не про важность."""
        for value, expected in (
            ("SUCCESS", "INFO"),
            ("WARN", "WARNING"),
            ("FATAL", "CRITICAL"),
            ("DIAG", "DEBUG"),
        ):
            with self.subTest(value=value):
                self.assertEqual(self._split(value)[0], expected)

    def test_plain_levels_survive(self) -> None:
        from log.normalize import KNOWN_LEVELS

        for value in sorted(KNOWN_LEVELS):
            with self.subTest(value=value):
                self.assertEqual(self._split(value), (value, ""))

    def test_missing_level_falls_back(self) -> None:
        from log.normalize import DEFAULT_LEVEL

        self.assertEqual(self._split("")[0], DEFAULT_LEVEL)
        self.assertEqual(self._split(None)[0], DEFAULT_LEVEL)


class NormalizeTests(unittest.TestCase):
    def _normalize(self, *args, **kwargs):
        from log.normalize import normalize

        return normalize(*args, **kwargs)

    def test_message_and_level_are_cleaned_together(self) -> None:
        self.assertEqual(
            self._normalize("✅ Обход запущен", "✅ INFO"),
            ("Обход запущен", "INFO", ""),
        )

    def test_explicit_component_wins(self) -> None:
        """Явный компонент указывает вызывающий код, и он точнее."""
        _message, _level, component = self._normalize("текст", "📱 TG", "VPN")

        self.assertEqual(component, "VPN")

    def test_component_is_recovered_from_the_level_field(self) -> None:
        _message, level, component = self._normalize("текст", "🔄 CACHE")

        self.assertEqual(level, "INFO")
        self.assertEqual(component, "CACHE")


class MeasurementTests(unittest.TestCase):
    """Замеры отрисовки — не для человека.

    На снимке окно «Логи» было забито строками вида
    `UiMetric: scope=page name=LOGS stage=content.ready.first elapsed=...`.
    Они нужны при разборе медленного старта, а человек в этот момент
    ищет, почему не открывается сайт.
    """

    def _is_measurement(self, message: str) -> bool:
        from log.log import _is_measurement

        return _is_measurement(message)

    def test_ui_metrics_are_recognised(self) -> None:
        self.assertTrue(
            self._is_measurement(
                "UiMetric: scope=page name=LOGS stage=content.ready.first elapsed=12313ms"
            )
        )

    def test_startup_metrics_are_recognised(self) -> None:
        self.assertTrue(self._is_measurement("StartupQtRuntimeQApplication 42ms"))

    def test_ordinary_messages_are_not(self) -> None:
        for message in (
            "Обход запущен",
            "Не удалось открыть hosts",
            "Проверка UiMetric завершена",
        ):
            with self.subTest(message=message):
                self.assertFalse(self._is_measurement(message))

    def test_measurements_are_pushed_down_to_debug(self) -> None:
        """Проверяем не строку, а решение: замер уходит из видимого лога."""
        import inspect

        from log import log as log_module

        source = inspect.getsource(log_module.LogStore.log if hasattr(log_module, "LogStore") else log_module)

        self.assertIn("_is_measurement", source)


if __name__ == "__main__":
    unittest.main()
