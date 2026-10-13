"""Gemini AI и Antigravity — одна плитка, имя-ключ прежнее.

Отдельный сервис «Google Antigravity» делил с Gemini AI адрес
daily-cloudcode-pa.googleapis.com: при разных профилях у двух плиток этот
адрес получал профиль той, что ниже в каталоге. Теперь сайт Antigravity
лежит в Gemini AI. Надпись плитки — «Gemini AI и Antigravity» из поля
title каталога, а имя остаётся «Gemini AI»: по нему лежит сохранённый
выбор людей, и переименование выключило бы Gemini у всех, кто его включал.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

GEMINI_PROFILES = ("geohide", "dns_ai", "comss_dns", "astracat", "zapret_dns")


class GeminiCatalogTests(unittest.TestCase):
    def test_antigravity_lives_in_gemini_under_the_old_key(self) -> None:
        from hosts.proxy_domains import get_service_domain_ip_rows, get_services_profile_index

        index = get_services_profile_index()
        self.assertIn("Gemini AI", index["services"])
        self.assertNotIn("Google Antigravity", index["services"])
        self.assertEqual(index["title_by_service"].get("Gemini AI"), "Gemini AI и Antigravity")

        for profile in GEMINI_PROFILES:
            hosts = {host for host, _ip in get_service_domain_ip_rows("Gemini AI", profile)}
            with self.subTest(profile=profile):
                # Профиль не выпал: у него есть адрес для каждого имени, и для новых тоже.
                self.assertTrue(
                    {"gemini.google.com", "antigravity.google", "www.antigravity.google",
                     "daily-cloudcode-pa.googleapis.com"} <= hosts,
                    sorted(hosts)[:5],
                )

    def test_no_host_belongs_to_two_services_any_more(self) -> None:
        import json

        catalog = Path(__file__).resolve().parents[1] / "json" / "hosts_catalog" / "dns"
        owners: dict[str, list[str]] = {}
        for path in sorted(catalog.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for domain in data.get("domains") or []:
                owners.setdefault(domain["host"].lower(), []).append(data["name"])
        self.assertEqual({host: names for host, names in owners.items() if len(names) > 1}, {})


class GeminiTileTests(unittest.TestCase):
    def test_tile_shows_title_and_search_finds_antigravity(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from hosts.page_snapshot import CATEGORY_AI, CATEGORY_DIRECT, HostsPageSnapshot, HostsServiceEntry
        from hosts.ui.page import HostsPage

        _app = QApplication.instance() or QApplication([])
        entries = (
            HostsServiceEntry("Direct", CATEGORY_DIRECT, "fa5s.globe", None, ("hosts",), None),
            HostsServiceEntry("Gemini AI", CATEGORY_AI, "fa5s.globe", None, ("geohide",), None,
                              title="Gemini AI и Antigravity"),
            HostsServiceEntry("Claude AI", CATEGORY_AI, "fa5s.globe", None, ("geohide",), None),
        )
        snapshot = HostsPageSnapshot(entries, (("geohide", "GeoHide"),), None)
        feature = SimpleNamespace(
            peek_page_snapshot=lambda: snapshot,
            create_snapshot_worker=lambda request_id, parent=None: None,
            create_apply_worker=lambda request_id, selection, adobe, parent=None: None,
        )
        page = HostsPage(deps=SimpleNamespace(hosts_feature=feature, open_file_page=lambda: None))
        def drop() -> None:
            # Страницу без окна-родителя Qt может удалить сам раньше нас.
            try:
                page.deleteLater()
            except RuntimeError:
                pass

        self.addCleanup(drop)
        with patch.object(page, "_request_snapshot"):
            page._set_snapshot(snapshot)
            tile = next(t for t in page.tiles.tiles() if t.key == "Gemini AI")
            self.assertEqual(tile.title, "Gemini AI и Antigravity")

            page._on_search_changed("antigravity")
            keys = [t.key for t in page.tiles.tiles() if t.kind == "tile"]
            self.assertEqual(keys, ["Gemini AI"])


if __name__ == "__main__":
    unittest.main()
