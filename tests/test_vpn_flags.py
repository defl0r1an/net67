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


class CyrillicCountryCodeTests(unittest.TestCase):
    """Код страны, набранный русской раскладкой, тоже опознаётся.

    Подписки пишут названия по-русски, и двухбуквенный код в них нередко
    набран тем же кириллическим раскладом: «АL Албания» вместо
    «AL Албания». На экране разницы нет — «А» и «A» рисуются одинаково.

    Разбор считал разделителем всё, кроме латиницы: кириллическая «А»
    съедалась вместе с пробелом, от кода оставалась одна буква «L», и
    страна не опознавалась. Флага не было у одной Албании — у соседей по
    списку код был набран латиницей, и со стороны это выглядело как
    испорченная картинка. Картинка была в порядке.
    """

    def test_cyrillic_lookalike_code_is_recognised(self) -> None:
        from vpn.flags import country_code

        # Первая буква кириллическая, вторая латинская — так и было.
        self.assertEqual(country_code("АL Албания N1 (YouTube без рекл)"), "AL")

    def test_fully_cyrillic_code_is_recognised(self) -> None:
        from vpn.flags import country_code

        self.assertEqual(country_code("СН Швейцария N1"), "CH")
        self.assertEqual(country_code("РТ Португалия N1"), "PT")

    def test_country_is_found_by_name_without_any_code(self) -> None:
        # Запасной путь: у Албании его не было вовсе — страны не
        # оказалось в списке названий.
        from vpn.flags import country_code

        self.assertEqual(country_code("Албания N1"), "AL")

    def test_latin_names_still_work(self) -> None:
        from vpn.flags import country_code

        self.assertEqual(country_code("NL Нидерланды N1"), "NL")
        self.assertEqual(country_code("GB Великобритания N1"), "GB")

    def test_russian_words_do_not_become_countries(self) -> None:
        """Замена похожих букв не должна делать страну из русского слова.

        Первая попытка резала строку по латинице, считая кириллицу
        разделителем. «Мой сервер» распадалось на куски, из которых
        складывалось «MO», и сервер получал флаг Макао. Поэтому слово
        берётся целиком и только потом нормализуется: «Мой» и «сервер»
        длиннее двух букв и отсеиваются сразу.
        """
        from vpn.flags import country_code

        for title in ("Мой сервер", "Сервер быстрый", "Тест", "Node 3"):
            with self.subTest(title=title):
                self.assertEqual(country_code(title), "")

    def test_cyrillic_code_is_stripped_next_to_the_flag(self) -> None:
        """Рядом с флагом не остаётся букв кода — даже кириллических.

        Проверка требовала ASCII, и код, набранный русской раскладкой,
        её не проходил: флаг стоял, а «АL» рядом с ним оставалось —
        страна была написана дважды.
        """
        from vpn.flags import strip_country_prefix

        self.assertEqual(strip_country_prefix("АL Албания N1"), "Албания N1")
        self.assertEqual(strip_country_prefix("СН Швейцария N1"), "Швейцария N1")
        self.assertEqual(strip_country_prefix("GB Великобритания N1"), "Великобритания N1")

    def test_plain_names_keep_their_first_word(self) -> None:
        # Срезать первое слово можно только если это код страны.
        from vpn.flags import strip_country_prefix

        for title in ("Авто выбор", "Мой сервер", "Node 3"):
            with self.subTest(title=title):
                self.assertEqual(strip_country_prefix(title), title)

    def test_small_capital_code_is_recognised_and_stripped(self) -> None:
        """Код малыми капителями — тоже код.

        Подписка пишет его красиво: «ɢʙ», «ɴʟ», «ᴅᴇ». Это отдельные
        символы Unicode (U+0262, U+0274, U+1D05), и верхнего регистра у
        них нет вовсе — `"ɢʙ".upper()` возвращает то же самое. Проверка
        на код страны их не узнавала, и рядом с флагом оставались буквы,
        которые он и должен был заменить.

        Сбивало с толку то, что флаг при этом появлялся: он находился по
        названию страны, а не по коду.
        """
        from vpn.flags import country_code, strip_country_prefix

        self.assertEqual(country_code("ɢʙ Великобритания N1"), "GB")
        self.assertEqual(country_code("ᴅᴇ Германия N1"), "DE")
        self.assertEqual(strip_country_prefix("ɴʟ Нидерланды N1"), "Нидерланды N1")
        self.assertEqual(strip_country_prefix("ᴀʟ Албания N1"), "Албания N1")


class FlagEmojiPrefixTests(unittest.TestCase):
    """Флаг-эмодзи в начале названия — тоже сокращение, и его надо срезать.

    Он и остался на экране после первой правки. Обмануло то, как его
    рисует Windows: шрифта для флагов там нет, и пара символов-индикаторов
    выводится двумя буквами в рамочках. Со стороны это неотличимо от
    кода страны, который мы уже вроде бы срезали, — поэтому я и проверял
    разбор кодов вместо разбора эмодзи.

    Разбор его не брал: символы-индикаторы не буквы, `isalpha()` на них
    отвечает False, и функция выходила на первой же строчке.
    """

    def test_flag_emoji_is_removed(self) -> None:
        from vpn.flags import strip_country_prefix

        self.assertEqual(
            strip_country_prefix("\U0001F1EC\U0001F1E7 Великобритания N1"),
            "Великобритания N1",
        )

    def test_flag_and_code_together(self) -> None:
        """Подписки ставят и то, и другое сразу."""
        from vpn.flags import strip_country_prefix

        self.assertEqual(
            strip_country_prefix("\U0001F1EC\U0001F1E7 GB Великобритания N1"),
            "Великобритания N1",
        )

    def test_variation_selector_does_not_stop_it(self) -> None:
        """Между символами попадает невидимая служебная разметка."""
        from vpn.flags import strip_country_prefix

        self.assertEqual(
            strip_country_prefix("\U0001F1F3\U0001F1F1️ NL Нидерланды N1"),
            "Нидерланды N1",
        )

    def test_single_indicator_is_not_a_flag(self) -> None:
        """Один символ — не флаг, и трогать строку незачем."""
        from vpn.flags import strip_country_prefix

        title = "\U0001F1EC Что-то N1"

        self.assertEqual(strip_country_prefix(title), title)

    def test_flag_in_the_middle_is_left_alone(self) -> None:
        """Режем только начало: в середине это часть названия."""
        from vpn.flags import strip_country_prefix

        title = "Сервер \U0001F1EC\U0001F1E7 N1"

        self.assertEqual(strip_country_prefix(title), title)

    def test_country_is_still_recognised(self) -> None:
        """Флаг обязан находиться и по эмодзи, иначе значка не будет."""
        from vpn.flags import country_code

        self.assertEqual(country_code("\U0001F1F5\U0001F1F9 Португалия N1"), "PT")

    def test_bare_code_survives(self) -> None:
        """Если кроме кода в имени ничего нет, подпись не должна опустеть."""
        from vpn.flags import strip_country_prefix

        self.assertEqual(strip_country_prefix("US"), "US")

    def test_nothing_to_strip(self) -> None:
        from vpn.flags import strip_country_prefix

        for title in ("Мой сервер", "", "   "):
            with self.subTest(title=title):
                self.assertEqual(strip_country_prefix(title), title.strip())
