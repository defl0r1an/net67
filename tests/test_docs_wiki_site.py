"""Документация — сайт в интернете, а не копия внутри сборки.

Вики ехала с программой: папка `docs` и сервер на 127.0.0.1. Когда её
опубликовали, владелец попросил вести кнопки на сайт и убрать копию из
сборки. Тесты держат это решение целиком: адрес собирается верно, кнопка
и экскурсия ходят на сайт, а сборка вики больше не кладёт — иначе она
вернётся молча, вместе с проверкой «вики битая», роняющей сборку.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))


class PageUrlTests(unittest.TestCase):
    def test_site_address_is_the_published_wiki(self) -> None:
        from docs import wiki_site

        self.assertEqual(wiki_site.base_url(), "https://defl0r1an.github.io/net67/")

    def test_article_and_anchor_are_quoted(self) -> None:
        from docs import wiki_site

        self.assertEqual(
            wiki_site.page_url("presets#фейки"),
            "https://defl0r1an.github.io/net67/presets#%D1%84%D0%B5%D0%B9%D0%BA%D0%B8",
        )
        self.assertEqual(wiki_site.page_url("techniques"), "https://defl0r1an.github.io/net67/techniques")

    def test_index_is_the_site_root(self) -> None:
        from docs import wiki_site

        self.assertEqual(wiki_site.page_url("index"), "https://defl0r1an.github.io/net67/")
        self.assertEqual(wiki_site.page_url(""), "https://defl0r1an.github.io/net67/")

    def test_no_address_no_link(self) -> None:
        import branding
        from docs import wiki_site

        with patch.object(branding, "DOCS_URL", ""):
            self.assertEqual(wiki_site.page_url("presets"), "")
            self.assertEqual(wiki_site.open_in_browser(), (False, "Адрес документации не задан"))

    def test_address_without_trailing_slash_still_joins(self) -> None:
        import branding
        from docs import wiki_site

        with patch.object(branding, "DOCS_URL", "https://example.org/wiki"):
            self.assertEqual(wiki_site.page_url("dns"), "https://example.org/wiki/dns")

    def test_open_in_browser_opens_the_site(self) -> None:
        from docs import wiki_site

        with patch("webbrowser.open") as opened:
            ok, url = wiki_site.open_in_browser("hosts")
        self.assertTrue(ok)
        self.assertEqual(url, "https://defl0r1an.github.io/net67/hosts")
        opened.assert_called_once_with(url)


class NoBundledCopyTests(unittest.TestCase):
    """Встроенной копии и её сервера больше нет."""

    def test_local_server_module_is_gone(self) -> None:
        self.assertFalse((PROJECT_ROOT / "src" / "docs" / "local_site.py").exists())
        for path in (PROJECT_ROOT / "src").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(PROJECT_ROOT).as_posix()):
                self.assertNotIn("docs.local_site", text)

    def test_docs_card_and_tour_use_the_site(self) -> None:
        card = (PROJECT_ROOT / "src" / "presets" / "ui" / "control" / "shared_builders.py").read_text(encoding="utf-8")
        tour = (PROJECT_ROOT / "src" / "ui" / "onboarding" / "overlay.py").read_text(encoding="utf-8")
        self.assertIn("from docs.wiki_site import open_in_browser", card)
        self.assertIn("from docs.wiki_site import page_url", tour)

    def test_builds_do_not_ship_the_wiki(self) -> None:
        for name in ("scripts/build_local.ps1", ".github/workflows/windows-release.yml"):
            text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertNotIn("wiki\\site", text)
                self.assertNotIn("docs\\index.html", text)


if __name__ == "__main__":
    unittest.main()
