"""Профили DNS net67 поверх каталога zapret (AstraCat, GeoHide).

Каталог приходит из zapret слиянием. Свои профили лежат отдельным
файлом, чтобы не превращать каждое слияние в конфликт в шестидесяти
файлах, — и программа обязана увидеть их так же, как родные.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for extra in (PROJECT_ROOT / "src", PROJECT_ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from hosts import proxy_domains  # noqa: E402


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _catalog(root: Path, *, overlay: dict | None, catalog_profiles=("xbox_dns",)) -> None:
    _write(root / "dns_sources.json", {"dns_sources": [{"id": p, "name": p} for p in catalog_profiles]})
    _write(
        root / "dns" / "001_claude.json",
        {
            "name": "Claude",
            "category": "ai",
            "domains": [
                {"host": "claude.ai", "ips": {p: "10.0.0.1" for p in catalog_profiles}},
                {"host": "api.anthropic.com", "ips": {p: "10.0.0.2" for p in catalog_profiles}},
            ],
        },
    )
    _write(
        root / "dns" / "002_notion.json",
        {"name": "Notion", "domains": [{"host": "notion.so", "ips": {p: "10.0.0.3" for p in catalog_profiles}}]},
    )
    if overlay is not None:
        _write(root / proxy_domains.NET67_OVERLAY_FILE_NAME, overlay)


def _load(root: Path):
    data, _sig = proxy_domains._load_split_catalog_data_with_sig(root)
    return proxy_domains._parse_hosts_catalog_json(json.dumps(data, ensure_ascii=False))


class OverlayLoadTests(unittest.TestCase):
    def test_overlay_profile_is_offered_only_where_it_covers_every_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _catalog(
                root,
                overlay={
                    "dns_sources": [{"id": "astracat", "name": "AstraCat"}],
                    "ips": {
                        "claude.ai": {"astracat": "20.0.0.1"},
                        "API.anthropic.com": {"astracat": "20.0.0.2"},
                    },
                },
            )
            catalog = _load(root)

            self.assertIn("astracat", catalog.dns_profiles)
            self.assertEqual(catalog.dns_profile_names["astracat"], "AstraCat")
            with patch.object(proxy_domains, "_load_catalog", return_value=catalog):
                self.assertIn("astracat", proxy_domains.get_service_available_dns_profiles("Claude"))
                # Для Notion адресов нет — кружка AstraCat у него быть не должно.
                self.assertNotIn("astracat", proxy_domains.get_service_available_dns_profiles("Notion"))
                rows = dict(proxy_domains.get_service_domain_ip_rows("Claude", "astracat"))
            self.assertEqual(rows, {"claude.ai": "20.0.0.1", "api.anthropic.com": "20.0.0.2"})

    def test_catalog_wins_when_zapret_ships_the_same_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _catalog(
                root,
                catalog_profiles=("xbox_dns", "astracat"),
                overlay={
                    "dns_sources": [{"id": "astracat", "name": "AstraCat net67"}],
                    "ips": {"claude.ai": {"astracat": "99.9.9.9"}},
                },
            )
            catalog = _load(root)

            self.assertEqual(catalog.dns_profiles.count("astracat"), 1)
            self.assertEqual(catalog.dns_profile_names["astracat"], "astracat")
            with patch.object(proxy_domains, "_load_catalog", return_value=catalog):
                rows = dict(proxy_domains.get_service_domain_ip_rows("Claude", "astracat"))
            self.assertEqual(rows["claude.ai"], "10.0.0.1")

    def test_broken_overlay_leaves_catalog_working(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _catalog(root, overlay=None)
            (root / proxy_domains.NET67_OVERLAY_FILE_NAME).write_text("{ битый", encoding="utf-8")
            catalog = _load(root)

            self.assertEqual(catalog.dns_profiles[:1], ["xbox_dns"])
            self.assertIn("Claude", catalog.service_order)

    def test_overlay_change_changes_catalog_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _catalog(root, overlay={"dns_sources": [{"id": "astracat", "name": "AstraCat"}], "ips": {}})
            files = proxy_domains._split_catalog_files(root)
            self.assertIn(root / proxy_domains.NET67_OVERLAY_FILE_NAME, files)

    def test_shipped_overlay_matches_resolver_config(self) -> None:
        """Файл в каталоге и настройки инструмента называют одни профили."""
        overlay_path = PROJECT_ROOT / "json" / "hosts_catalog" / proxy_domains.NET67_OVERLAY_FILE_NAME
        if not overlay_path.exists():
            self.skipTest("дополнение ещё не заполнено")
        shipped = {p["id"] for p in json.loads(overlay_path.read_text(encoding="utf-8"))["dns_sources"]}
        config = json.loads((PROJECT_ROOT / "tools" / "hosts_catalog_resolvers.json").read_text(encoding="utf-8"))
        declared = {key for key, value in config["sources"].items() if value.get("overlay")}
        self.assertEqual(shipped, declared)


class OverlayRefreshTests(unittest.TestCase):
    """Инструмент пишет профиль только там, где резолвер подменяет адрес."""

    def _run(self, answers: dict, *, previous: dict | None = None, proxy_min: int = 1):
        import refresh_hosts_catalog as tool

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _catalog(root, overlay=previous)
            real = {"claude.ai": "1.1.1.1", "api.anthropic.com": "1.1.1.2", "notion.so": "1.1.1.3"}

            def fake_resolve(host, _qtype, source, **_kw):
                if isinstance(source, dict):
                    value = answers.get((source["name"], host))
                    if value is None:
                        raise tool.DnsError("молчит")
                    return [value]
                return [real[host]]

            sources = {"geohide": {"name": "GeoHide", "overlay": True, "servers": ["x"]}}
            report = tool.Report()
            with (
                patch.object(tool, "CATALOG_ROOT", root),
                patch.object(tool, "OVERLAY_FILE", root / proxy_domains.NET67_OVERLAY_FILE_NAME),
                patch.object(tool, "resolve", side_effect=fake_resolve),
                patch.object(tool, "PROXY_MIN_SERVICES", proxy_min),
            ):
                data = tool.refresh_overlay(sources, ["1.1.1.1"], report)
            return data, report

    def test_real_addresses_do_not_make_a_profile(self) -> None:
        data, report = self._run(
            {
                ("GeoHide", "claude.ai"): "30.0.0.1",
                ("GeoHide", "api.anthropic.com"): "1.1.1.2",
                ("GeoHide", "notion.so"): "1.1.1.3",
            }
        )
        # Claude подменён хотя бы частично — пишется целиком, как отвечает резолвер.
        self.assertEqual(data["ips"]["claude.ai"], {"geohide": "30.0.0.1"})
        self.assertEqual(data["ips"]["api.anthropic.com"], {"geohide": "1.1.1.2"})
        # Notion отдан настоящим адресом — профиля у него нет.
        self.assertNotIn("notion.so", data["ips"])
        self.assertEqual(report.not_substituted, ["002_notion.json [geohide]"])

    def test_cdn_address_that_merely_differs_is_not_a_substitution(self) -> None:
        # Akamai отдаёт разным резолверам разные узлы: адрес не совпал с
        # публичным, но повторяется у одного сервиса — это не прокси.
        data, report = self._run(
            {
                ("GeoHide", "claude.ai"): "30.0.0.1",
                ("GeoHide", "api.anthropic.com"): "30.0.0.1",
                ("GeoHide", "notion.so"): "23.12.156.165",
            },
            proxy_min=2,
        )
        self.assertNotIn("notion.so", data["ips"])
        self.assertIn("002_notion.json [geohide]", report.not_substituted)
        # Повтор внутри одного сервиса прокси не делает: считаются сервисы.
        self.assertIn("001_claude.json [geohide]", report.not_substituted)

    def test_address_shared_by_services_is_the_proxy(self) -> None:
        data, report = self._run(
            {
                ("GeoHide", "claude.ai"): "30.0.0.1",
                ("GeoHide", "api.anthropic.com"): "1.1.1.2",
                ("GeoHide", "notion.so"): "30.0.0.1",
            },
            proxy_min=2,
        )
        self.assertEqual(report.not_substituted, [])
        self.assertEqual(data["ips"]["notion.so"], {"geohide": "30.0.0.1"})

    def test_dead_domain_of_substituted_service_gets_its_proxy(self) -> None:
        # api.anthropic.com «мёртв»: пусто и у резолвера, и у публичного DNS.
        # Без строки профиль у Claude был бы неполным и пропал бы из ряда.
        import refresh_hosts_catalog as tool

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _catalog(root, overlay=None)

            def fake_resolve(host, _qtype, source, **_kw):
                if isinstance(source, dict):
                    return {"claude.ai": ["30.0.0.1"], "api.anthropic.com": [], "notion.so": ["1.1.1.3"]}[host]
                return {"claude.ai": ["1.1.1.1"], "api.anthropic.com": [], "notion.so": ["1.1.1.3"]}[host]

            report = tool.Report()
            with (
                patch.object(tool, "CATALOG_ROOT", root),
                patch.object(tool, "OVERLAY_FILE", root / proxy_domains.NET67_OVERLAY_FILE_NAME),
                patch.object(tool, "resolve", side_effect=fake_resolve),
                patch.object(tool, "PROXY_MIN_SERVICES", 1),
            ):
                data = tool.refresh_overlay(
                    {"geohide": {"name": "GeoHide", "overlay": True, "servers": ["x"]}}, ["1.1.1.1"], report
                )
        self.assertEqual(data["ips"]["api.anthropic.com"], {"geohide": "30.0.0.1"})

    def test_dead_domain_answered_with_sinkhole_gets_the_proxy_too(self) -> None:
        # DNS-AI на несуществующее имя отвечает 0.0.0.0, а не пустотой
        # (statsig.anthropic.com) — и Claude терял профиль из-за него.
        import refresh_hosts_catalog as tool

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _catalog(root, overlay=None)

            def fake_resolve(host, _qtype, source, **_kw):
                if isinstance(source, dict):
                    return {"claude.ai": ["30.0.0.1"], "api.anthropic.com": ["0.0.0.0"], "notion.so": ["1.1.1.3"]}[host]
                return {"claude.ai": ["1.1.1.1"], "api.anthropic.com": [], "notion.so": ["1.1.1.3"]}[host]

            with (
                patch.object(tool, "CATALOG_ROOT", root),
                patch.object(tool, "OVERLAY_FILE", root / proxy_domains.NET67_OVERLAY_FILE_NAME),
                patch.object(tool, "resolve", side_effect=fake_resolve),
                patch.object(tool, "PROXY_MIN_SERVICES", 1),
            ):
                data = tool.refresh_overlay(
                    {"dns_ai": {"name": "DNS-AI", "overlay": True, "dot": "x"}}, ["1.1.1.1"], tool.Report()
                )
        self.assertEqual(data["ips"]["api.anthropic.com"], {"dns_ai": "30.0.0.1"})

    def test_sinkhole_answer_is_never_written(self) -> None:
        data, _report = self._run(
            {
                ("GeoHide", "claude.ai"): "30.0.0.1",
                ("GeoHide", "api.anthropic.com"): "0.0.0.0",
                ("GeoHide", "notion.so"): "1.1.1.3",
            }
        )
        self.assertEqual(data["ips"]["claude.ai"], {"geohide": "30.0.0.1"})
        self.assertNotIn("api.anthropic.com", data["ips"])

    def test_silent_resolver_keeps_previous_addresses(self) -> None:
        previous = {
            "dns_sources": [{"id": "geohide", "name": "GeoHide"}],
            "ips": {"notion.so": {"geohide": "30.0.0.9"}},
        }
        data, report = self._run({}, previous=previous)
        self.assertEqual(data["ips"]["notion.so"], {"geohide": "30.0.0.9"})
        self.assertTrue(report.unresolved)

    def test_resolver_that_stopped_substituting_loses_the_service(self) -> None:
        previous = {
            "dns_sources": [{"id": "geohide", "name": "GeoHide"}],
            "ips": {"notion.so": {"geohide": "30.0.0.9"}},
        }
        data, _report = self._run({("GeoHide", "notion.so"): "1.1.1.3"}, previous=previous)
        self.assertNotIn("notion.so", data["ips"])


if __name__ == "__main__":
    unittest.main()
