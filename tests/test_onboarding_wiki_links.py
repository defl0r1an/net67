"""Кнопка «Подробнее в вики» в туре ведёт на существующую статью нашей вики.

У исходного проекта шаги тура вели на его сайт. Ссылки убрали вместе с
остальными упоминаниями, и кнопки не стало вовсе. Теперь статьи свои
(wiki/content), и ссылка — страница с якорем заголовка. Такая ссылка
ломается молча: переименовали заголовок — браузер откроет статью с
начала. Тест находит это раньше человека.

Вики открывается с сайта, и проверить ссылку по сети тест не может:
статьи и заголовки сверяются по исходникам в wiki/content, из которых
сайт собирается.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

WIKI_CONTENT = PROJECT_ROOT / "wiki" / "content"


def slug(heading: str) -> str:
    """Якорь заголовка, как его делает генератор вики (Quartz).

    Правило сверено с собранным сайтом: «Почему пресет со временем
    «портится»» → почему-пресет-со-временем-портится, «1. Обход включён?»
    → 1-обход-включён.
    """
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def anchors(page: str) -> set[str]:
    text = (WIKI_CONTENT / f"{page}.md").read_text(encoding="utf-8")
    return {slug(match.group(1)) for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.MULTILINE)}


class WikiLinksTests(unittest.TestCase):
    def test_slug_rule_matches_the_built_site(self) -> None:
        self.assertEqual(slug("Почему пресет со временем «портится»"), "почему-пресет-со-временем-портится")
        self.assertEqual(slug("1. Обход включён?"), "1-обход-включён")
        self.assertEqual(slug("Hostlist или IPset"), "hostlist-или-ipset")

    def test_every_tour_link_points_to_an_existing_article_and_heading(self) -> None:
        from config.urls import ONBOARDING_WIKI_URLS

        for step, link in ONBOARDING_WIKI_URLS.items():
            with self.subTest(step=step, link=link):
                page, _, anchor = link.partition("#")
                self.assertTrue((WIKI_CONTENT / f"{page}.md").is_file(), f"нет статьи {page}.md")
                if anchor:
                    self.assertIn(anchor, anchors(page))

    def test_built_site_has_the_same_headings_once_rebuilt(self) -> None:
        """Если сайт уже пересобран, якоря в HTML совпадают с нашими."""
        site = PROJECT_ROOT / "wiki" / "site"
        from config.urls import ONBOARDING_WIKI_URLS

        for step, link in ONBOARDING_WIKI_URLS.items():
            page, _, anchor = link.partition("#")
            html = site / f"{page}.html"
            if not anchor or not html.is_file():
                continue
            with self.subTest(step=step, link=link):
                self.assertIn(f'id="{anchor}"', html.read_text(encoding="utf-8"))


class PageUrlTests(unittest.TestCase):
    def test_every_tour_link_resolves_to_the_site(self) -> None:
        from config.urls import ONBOARDING_WIKI_URLS
        from ui.onboarding import overlay

        for step, link in ONBOARDING_WIKI_URLS.items():
            with self.subTest(step=step):
                url = overlay._resolve_wiki_url(link)
                self.assertTrue(url.startswith("https://defl0r1an.github.io/net67/"), url)
                # Локальный адрес — признак вернувшейся встроенной копии.
                self.assertNotIn("127.0.0.1", url)

    def test_tour_card_keeps_full_urls_and_resolves_wiki_pages(self) -> None:
        from ui.onboarding import overlay

        self.assertEqual(overlay._resolve_wiki_url("https://example.org/a"), "https://example.org/a")
        self.assertEqual(overlay._resolve_wiki_url(""), "")
        with patch("docs.wiki_site.page_url", return_value="https://example.org/presets") as page_url:
            self.assertEqual(overlay._resolve_wiki_url("presets"), "https://example.org/presets")
        page_url.assert_called_once_with("presets")


if __name__ == "__main__":
    unittest.main()
