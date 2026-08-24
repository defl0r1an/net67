"""Собранная вика должна быть собрана целиком.

Quartz при неудачной сборке не откатывается: стили он записать успевает,
а страницы — нет. В `wiki/site` остаются css-файлы и одинокий 404.html,
и выглядит папка вполне наполненной. Дальше её копируют в сборку, кнопка
«Документация» открывает пустоту, а разобраться, что именно пропало, по
виду папки нельзя.

Ровно это и случилось: 66 файлов превратились в 29 и в таком виде уехали
в коммит. Проверка сборки ловит это на своей стороне, но полагаться на
неё одну не стоит — она отрабатывает только когда кто-то собирает.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "wiki" / "site"
CONTENT = ROOT / "wiki" / "content"

#: Страницы, без которых вика бессмысленна.
REQUIRED_PAGES = ("index.html", "faq.html", "bypass.html", "vpn.html")


class DocsSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        if not SITE.is_dir():
            self.skipTest("wiki/site не собрана")

    def test_home_page_exists(self) -> None:
        self.assertTrue(
            (SITE / "index.html").is_file(),
            "нет index.html — программа не найдёт, что открывать",
        )

    def test_key_pages_exist(self) -> None:
        missing = [name for name in REQUIRED_PAGES if not (SITE / name).is_file()]
        self.assertEqual(missing, [], f"в собранной вике не хватает страниц: {missing}")

    def test_every_article_became_a_page(self) -> None:
        """Каждой статье из content соответствует страница в site."""
        if not CONTENT.is_dir():
            self.skipTest("wiki/content отсутствует")

        articles = sorted(p.stem for p in CONTENT.glob("*.md"))
        self.assertTrue(articles, "статей нет — проверять нечего")

        missing = [name for name in articles if not (SITE / f"{name}.html").is_file()]
        self.assertEqual(missing, [], f"статьи не собрались в страницы: {missing}")

    def test_search_index_is_present(self) -> None:
        """Без указателя поиск по вике молча ничего не находит."""
        self.assertTrue((SITE / "static" / "contentIndex.json").is_file())

    def test_site_is_not_just_stylesheets(self) -> None:
        pages = list(SITE.glob("*.html"))
        self.assertGreaterEqual(
            len(pages),
            10,
            f"страниц всего {len(pages)} — похоже на недописанную сборку",
        )


if __name__ == "__main__":
    unittest.main()
