"""Флаг страны в списке серверов.

Вместо флага стояли двухбуквенные коды — «GB», «NL», «PT». Они пришли
из имён в подписке и читаются хуже: «GB» надо вспомнить, флаг узнаётся
сразу.

## Откуда берётся страна

Из кода, который подписка сама и пишет. Это надёжнее перевода названия:
код один на весь мир, а название каждый сервис пишет по-своему и на
разном языке.

Сначала порядок был обратный — сперва искали русское название, — и
работали только те тридцать шесть стран, для которых у нас лежал
перевод. Сервер «SG Node 3» флага не получал, хотя код был прямо в
имени.

## Почему нужен список ISO

Чтобы отличить код страны от любых других двух букв. «N1» и «V2» тоже
двухбуквенные, и без списка они притворялись бы странами: 🇳🇮 вместо
номера узла.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class CountryCodesTests(unittest.TestCase):
    def test_every_country_in_the_world(self) -> None:
        """Двести сорок девять — весь ISO 3166-1, а не выборка."""
        from vpn.flags import ISO_COUNTRY_CODES

        self.assertEqual(len(ISO_COUNTRY_CODES), 249)

    def test_codes_are_upper_case_pairs(self) -> None:
        from vpn.flags import ISO_COUNTRY_CODES

        for code in ISO_COUNTRY_CODES:
            with self.subTest(code=code):
                self.assertEqual(len(code), 2)
                self.assertTrue(code.isupper() and code.isalpha() and code.isascii())


class RecognitionTests(unittest.TestCase):
    def test_code_from_the_subscription_wins(self) -> None:
        """Страна берётся из имени, которое прислала подписка."""
        from vpn.flags import country_code

        self.assertEqual(country_code("GB Великобритания N1"), "GB")
        self.assertEqual(country_code("NL Нидерланды N1"), "NL")

    def test_country_without_a_translation_still_works(self) -> None:
        """Тот самый случай, который раньше не работал."""
        from vpn.flags import COUNTRY_NAMES, country_code

        self.assertNotIn("ZW", COUNTRY_NAMES)
        self.assertEqual(country_code("ZW Harare"), "ZW")
        self.assertEqual(country_code("SG Node 3"), "SG")

    def test_code_is_found_not_only_at_the_start(self) -> None:
        """Подписки пишут код и в скобках, и через дефис."""
        from vpn.flags import country_code

        self.assertEqual(country_code("[NL]-Amsterdam-2"), "NL")
        self.assertEqual(country_code("Fast (DE) node"), "DE")

    def test_name_is_the_fallback(self) -> None:
        """Кода в имени может не быть вовсе."""
        from vpn.flags import country_code

        self.assertEqual(country_code("Германия N2"), "DE")

    def test_node_numbers_are_not_countries(self) -> None:
        """«N1» это номер узла, а не Никарагуа."""
        from vpn.flags import country_code

        for title in ("N1 Сервер", "V2 Быстрый", "Мой сервер", ""):
            with self.subTest(title=title):
                self.assertEqual(country_code(title), "")


class DisplayTests(unittest.TestCase):
    def test_flag_replaces_the_code(self) -> None:
        """Оставить оба — значит написать страну дважды."""
        from vpn.flags import decorate

        self.assertEqual(decorate("NL Нидерланды N1"), "🇳🇱  Нидерланды N1")

    def test_unknown_name_is_left_alone(self) -> None:
        from vpn.flags import decorate

        self.assertEqual(decorate("Мой сервер"), "Мой сервер")

    def test_flag_symbols_are_built_from_the_code(self) -> None:
        from vpn.flags import flag_for_code

        self.assertEqual(flag_for_code("NL"), "🇳🇱")
        self.assertEqual(flag_for_code("ZW"), "🇿🇼")
        self.assertEqual(flag_for_code("N1"), "")


class PictureTests(unittest.TestCase):
    """Картинка предпочтительнее символов: Windows пары не рисует."""

    def test_pictures_are_looked_up_by_code(self) -> None:
        from vpn.flags import FLAGS_DIR_NAME, flags_dir

        self.assertEqual(flags_dir().name, FLAGS_DIR_NAME)

    def test_missing_picture_is_not_an_error(self) -> None:
        """Папки может не быть вовсе — тогда работают символы."""
        from vpn.flags import flag_image_path

        self.assertIsNone(flag_image_path("ZZ"))
        self.assertIsNone(flag_image_path("N1"))


if __name__ == "__main__":
    unittest.main()
