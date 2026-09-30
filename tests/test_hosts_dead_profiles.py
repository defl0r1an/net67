"""Неработающие профили DNS не предлагаются в редакторе hosts.

Claude через Malw DNS открывал 8 доменов из 16, Malw DNS v2 отдавал чужой
сертификат на всё подряд — а кружки этих профилей стояли наравне с
рабочими. Список убранного ведётся по замерам отдельным файлом,
json/hosts_catalog/net67_dead_profiles.json.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hosts import proxy_domains  # noqa: E402

REAL_CATALOG = Path(__file__).resolve().parents[1] / "json" / "hosts_catalog"


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class DeadProfilesLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="net67-dead-profiles-"))
        _write(
            self.root / "dns_sources.json",
            {"dns_sources": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}, {"id": "c", "name": "C"}]},
        )
        for index, name in enumerate(("Сервис", "Другой")):
            _write(
                self.root / "dns" / f"00{index}_{index}.json",
                {
                    "name": name,
                    "domains": [
                        {"host": f"s{index}.example", "ips": {"a": "1.1.1.1", "b": "2.2.2.2", "c": "3.3.3.3"}}
                    ],
                },
            )

    def _load(self) -> dict:
        return proxy_domains._load_split_catalog_data(self.root)

    @staticmethod
    def _ips(data: dict, service: str) -> dict:
        found = next(s for s in data["services"] if s["name"] == service)
        return found["domains"][0]["ips"]

    def test_dead_profile_disappears_everywhere_and_service_one_only_there(self) -> None:
        _write(
            self.root / proxy_domains.NET67_DEAD_PROFILES_FILE_NAME,
            {
                "dead_profiles": {"c": "чужой сертификат на всё"},
                "services": {"сервис": {"b": "главный сайт не открывается"}},
            },
        )

        data = self._load()

        self.assertEqual([p["id"] for p in data["profiles"]], ["a", "b"])
        self.assertEqual(self._ips(data, "Сервис"), {"a": "1.1.1.1"})
        self.assertEqual(self._ips(data, "Другой"), {"a": "1.1.1.1", "b": "2.2.2.2"})

    def test_service_left_without_profiles_is_hidden(self) -> None:
        """Плитка без единого рабочего кружка — та же ловушка."""
        _write(
            self.root / proxy_domains.NET67_DEAD_PROFILES_FILE_NAME,
            {"services": {"Сервис": {"a": "x", "b": "x", "c": "x"}}},
        )

        names = [s["name"] for s in self._load()["services"]]

        self.assertEqual(names, ["Другой"])

    def test_without_the_file_catalog_is_untouched(self) -> None:
        data = self._load()
        self.assertEqual(len(data["profiles"]), 3)
        self.assertEqual(len(self._ips(data, "Сервис")), 3)

    def test_broken_file_does_not_take_the_catalog_down(self) -> None:
        (self.root / proxy_domains.NET67_DEAD_PROFILES_FILE_NAME).write_text("{ не json", encoding="utf-8")
        data = self._load()
        self.assertEqual(len(self._ips(data, "Другой")), 3)

    def test_not_default_profile_stays_visible_but_is_not_chosen(self) -> None:
        """Адрес молчал в двух сетях, а с других узлов отвечал: убирать
        нельзя, у другого человека может работать. Но сама программа его
        не ставит."""
        _write(
            self.root / proxy_domains.NET67_DEAD_PROFILES_FILE_NAME,
            {"not_default": {"Сервис": {"a": "главный сайт не открылся"}}},
        )
        data = self._load()
        self.assertEqual(self._ips(data, "Сервис"), {"a": "1.1.1.1", "b": "2.2.2.2", "c": "3.3.3.3"})

        catalog = proxy_domains._parse_hosts_catalog_json(json.dumps(data))
        self.assertEqual(catalog.not_default_profiles, {"сервис": frozenset({"a"})})
        with unittest.mock.patch.object(proxy_domains, "_load_catalog", return_value=catalog):
            self.assertEqual(proxy_domains.prefer_measured_profiles("Сервис", ["a", "b"]), ["b"])
            # Проверенных нет — выбирать всё равно из чего-то надо.
            self.assertEqual(proxy_domains.prefer_measured_profiles("Сервис", ["a"]), ["a"])
            self.assertEqual(proxy_domains.prefer_measured_profiles("Другой", ["a", "b"]), ["a", "b"])

    def test_file_is_part_of_the_catalog_signature(self) -> None:
        """Правка списка должна сбрасывать кэш каталога, как правка любого файла."""
        _write(self.root / proxy_domains.NET67_DEAD_PROFILES_FILE_NAME, {"dead_profiles": {}})
        files = proxy_domains._split_catalog_files(self.root)
        self.assertIn(self.root / proxy_domains.NET67_DEAD_PROFILES_FILE_NAME, files)


class RealDeadProfilesListTests(unittest.TestCase):
    """Список сверяется с каталогом: после слияния с zapret сервис могут
    переименовать, и исключение молча перестанет работать."""

    @classmethod
    def setUpClass(cls) -> None:
        path = REAL_CATALOG / proxy_domains.NET67_DEAD_PROFILES_FILE_NAME
        cls.data = json.loads(path.read_text(encoding="utf-8"))
        profiles = {p["id"] for p in json.loads((REAL_CATALOG / "dns_sources.json").read_text(encoding="utf-8"))["dns_sources"]}
        overlay = json.loads((REAL_CATALOG / proxy_domains.NET67_OVERLAY_FILE_NAME).read_text(encoding="utf-8"))
        profiles |= {p["id"] for p in overlay["dns_sources"]}
        cls.profiles = profiles
        cls.services = {
            json.loads(f.read_text(encoding="utf-8"))["name"].casefold()
            for f in (REAL_CATALOG / "dns").glob("*.json")
        }

    def test_every_profile_exists(self) -> None:
        named = set(self.data.get("dead_profiles", {}))
        for section in ("services", "not_default"):
            for entry in self.data.get(section, {}).values():
                named |= set(entry)
        self.assertEqual(named - self.profiles, set())

    def test_every_service_exists(self) -> None:
        for section in ("services", "not_default"):
            with self.subTest(section=section):
                names = {name.casefold() for name in self.data.get(section, {})}
                self.assertEqual(names - self.services, set())

    def test_every_exclusion_says_why(self) -> None:
        reasons = list(self.data.get("dead_profiles", {}).values())
        for section in ("services", "not_default"):
            for entry in self.data.get(section, {}).values():
                reasons.extend(entry.values())
        self.assertTrue(reasons)
        self.assertTrue(all(isinstance(r, str) and r.strip() for r in reasons))
        self.assertTrue(str(self.data.get("checked", "")).strip())


if __name__ == "__main__":
    unittest.main()
