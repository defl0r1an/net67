"""Провайдер выбирает, с чего начать, а не что заработает.

У разных провайдеров разное оборудование фильтрации, и стратегия,
работающая на одном, на другом может не дать ничего — отсюда и просьба
«под каждого провайдера свой конфиг».

Но таблицы «провайдер -> рабочий пресет» взять неоткуда. В поставке 106
пресетов winws2, и только у одного в имени есть провайдер —
«Ростелеком»; поля с провайдером нет ни у одного. В обсуждениях
исходного проекта категория presets — это просьбы прислать пресет и
сборки под игры и сайты, а не разбивка по операторам.

Придумать такую таблицу из головы — ровно та ошибка, что уже стоила
рабочего доступа: набор адресов «подмены DNS» тоже выглядел
авторитетно, а 44 домена в нём вели на адреса сети.

Поэтому правило простое: специальный пресет ставится только там, где он
физически есть в поставке. Остальным — стандартный и предложение
измерить. Эти тесты не дают правилу тихо смениться на выдумку.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

BUILTIN_WINWS2 = PROJECT_SRC / "presets" / "builtin" / "winws2"


class CatalogTests(unittest.TestCase):
    def test_popular_providers_are_offered(self) -> None:
        from provider.catalog import PROVIDERS

        titles = {item.title for item in PROVIDERS}

        for expected in ("Ростелеком", "МТС", "Билайн", "МегаФон", "Дом.ру"):
            self.assertIn(expected, titles)

    def test_there_is_an_escape_hatch(self) -> None:
        """Не каждый знает своего провайдера, и это нормально."""
        from provider.catalog import PROVIDERS, UNKNOWN

        keys = {item.key for item in PROVIDERS}

        self.assertIn(UNKNOWN, keys)
        self.assertIn("other", keys)

    def test_every_promised_preset_actually_exists(self) -> None:
        """Главная проверка: обещанный файл обязан лежать в поставке.

        Иначе выбор провайдера молча выберет несуществующий пресет, и
        включение упадёт с «файл не найден» — на чужой машине, не на
        машине разработчика.
        """
        from provider.catalog import PROVIDERS

        for provider in PROVIDERS:
            if not provider.preset:
                continue
            with self.subTest(provider=provider.title):
                self.assertTrue(
                    (BUILTIN_WINWS2 / provider.preset).is_file(),
                    f"пресет {provider.preset} не входит в поставку",
                )

    def test_default_preset_exists(self) -> None:
        from provider.catalog import DEFAULT_PRESET

        self.assertTrue((BUILTIN_WINWS2 / DEFAULT_PRESET).is_file())

    def test_unknown_provider_gets_the_default(self) -> None:
        from provider.catalog import DEFAULT_PRESET, preset_for_provider

        self.assertEqual(preset_for_provider("мусор"), DEFAULT_PRESET)
        self.assertEqual(preset_for_provider(None), DEFAULT_PRESET)
        self.assertEqual(preset_for_provider("mts"), DEFAULT_PRESET)

    def test_rostelecom_gets_its_own(self) -> None:
        """Единственный провайдер, под которого пресет реально есть."""
        from provider.catalog import preset_for_provider

        self.assertEqual(preset_for_provider("rostelecom"), "Ростелеком.txt")

    def test_measurement_is_always_offered(self) -> None:
        """Даже у Ростелекома фильтрация в разных регионах разная."""
        from provider.catalog import PROVIDERS, needs_measurement

        for provider in PROVIDERS:
            with self.subTest(provider=provider.key):
                self.assertTrue(needs_measurement(provider.key))

    def test_wording_promises_nothing(self) -> None:
        """Обещать «теперь заработает» мы не вправе."""
        from provider.catalog import PROVIDERS, describe_choice

        for provider in PROVIDERS:
            text = describe_choice(provider.key).lower()
            with self.subTest(provider=provider.key):
                self.assertNotIn("заработает", text)
                self.assertNotIn("гарант", text)
                # Зато про место, где можно измерить, сказано всегда.
                # Корень слова разный («подбор», «подобрать»), поэтому
                # проверяем название раздела.
                self.assertIn("диагностик", text)

    def test_no_provider_claims_a_preset_it_has_not(self) -> None:
        """Соответствие проставляется только по факту наличия файла."""
        from provider.catalog import PROVIDERS

        with_preset = [item.title for item in PROVIDERS if item.has_special_preset]

        self.assertEqual(with_preset, ["Ростелеком"], "появилось выдуманное соответствие")


class ApplyTests(unittest.TestCase):
    def test_choice_is_saved_and_preset_selected(self) -> None:
        import tempfile

        import settings.store as settings_store
        from provider.apply import apply_provider_choice

        original = settings_store.MAIN_DIRECTORY
        settings_store.MAIN_DIRECTORY = tempfile.mkdtemp()
        try:
            ok, preset = apply_provider_choice("rostelecom")

            self.assertTrue(ok, preset)
            self.assertEqual(preset, "Ростелеком.txt")
            self.assertEqual(settings_store.get_provider_key(), "rostelecom")
            self.assertEqual(
                settings_store.get_selected_source_preset_file_name("winws2"),
                "Ростелеком.txt",
            )
        finally:
            settings_store.MAIN_DIRECTORY = original

    def test_unknown_provider_still_selects_something(self) -> None:
        """Пропустил вопрос — включение всё равно должно работать."""
        import tempfile

        import settings.store as settings_store
        from provider.apply import apply_provider_choice

        original = settings_store.MAIN_DIRECTORY
        settings_store.MAIN_DIRECTORY = tempfile.mkdtemp()
        try:
            ok, preset = apply_provider_choice("unknown")

            self.assertTrue(ok, preset)
            self.assertEqual(preset, "Стандартный 1.txt")
        finally:
            settings_store.MAIN_DIRECTORY = original


class WizardWiringTests(unittest.TestCase):
    def test_provider_is_the_first_question(self) -> None:
        from wizard.plans import WIZARD_STEPS

        self.assertEqual([step.key for step in WIZARD_STEPS][0], "provider")

    def test_provider_applied_before_the_rest(self) -> None:
        """Пресет должен встать раньше, чем соберут запрос на включение."""
        import inspect

        from wizard.ui.dialog import WizardDialog

        source = inspect.getsource(WizardDialog._finish)
        provider_at = source.index("apply_provider_choice")
        wizard_at = source.index("apply_wizard(")

        self.assertLess(provider_at, wizard_at)


if __name__ == "__main__":
    unittest.main()
