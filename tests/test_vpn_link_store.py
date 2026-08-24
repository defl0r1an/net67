"""Хранение серверов, добавленных по ссылке.

Отдельно от профилей WireGuard: те лежат файлами .conf и поднимаются
службой Windows, эти — строки, которые отдаются ядру Xray как есть.
Общее хранилище потребовало бы поля «а это какого рода профиль» и его
разбора в каждом месте, где список читают.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


VLESS = "vless://11111111-2222-3333-4444-555555555555@example.org:443?security=tls#Берлин"
TROJAN = "trojan://secret@node.example.net:8443#Амстердам"


class RoundTripTests(unittest.TestCase):
    def _root(self) -> Path:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def _parse(self, link: str):
        from vpn.links import parse_link

        return parse_link(link)

    def test_missing_file_is_an_empty_list_not_an_error(self) -> None:
        """Страница обязана открыться на чистой установке."""
        from vpn.link_store import load_links

        profiles, errors = load_links(self._root())

        self.assertEqual(profiles, [])
        self.assertEqual(errors, [])

    def test_saved_links_come_back(self) -> None:
        from vpn.link_store import load_links, save_links

        root = self._root()
        saved, message = save_links(root, [self._parse(VLESS), self._parse(TROJAN)])
        self.assertTrue(saved, message)

        profiles, errors = load_links(root)

        self.assertEqual([item.raw for item in profiles], [VLESS, TROJAN])
        self.assertEqual(errors, [])

    def test_only_name_and_link_are_stored(self) -> None:
        """Разбор со временем улучшается, и старые записи должны это ловить.

        Хранить разобранные хост и порт значило бы законсервировать
        сегодняшнее незнание о параметрах ссылки.
        """
        from vpn.link_store import save_links, store_path

        root = self._root()
        save_links(root, [self._parse(VLESS)])

        record = json.loads(store_path(root).read_text(encoding="utf-8"))["links"][0]

        self.assertEqual(set(record), {"title", "link"})

    def test_human_given_name_wins_over_the_one_in_the_link(self) -> None:
        """Его человек и будет искать глазами в списке."""
        from vpn.link_store import load_links, save_links

        import dataclasses

        root = self._root()
        profile = dataclasses.replace(self._parse(VLESS), title="Рабочий")
        save_links(root, [profile])

        profiles, _errors = load_links(root)

        self.assertEqual(profiles[0].title, "Рабочий")

    def test_broken_record_is_reported_not_swallowed(self) -> None:
        """Потерять три сервера из тридцати и промолчать — хуже, чем ошибка."""
        from vpn.link_store import load_links, store_path

        root = self._root()
        store_path(root).write_text(
            json.dumps({"version": 1, "links": [{"link": "мусор"}, {"link": VLESS}]}),
            encoding="utf-8",
        )

        profiles, errors = load_links(root)

        self.assertEqual(len(profiles), 1)
        self.assertEqual(len(errors), 1)

    def test_damaged_file_does_not_crash_the_page(self) -> None:
        from vpn.link_store import load_links, store_path

        root = self._root()
        store_path(root).write_text("{ это не json", encoding="utf-8")

        profiles, errors = load_links(root)

        self.assertEqual(profiles, [])
        self.assertTrue(errors)

    def test_format_version_is_written(self) -> None:
        """Будущая правка формата должна отличать свои записи от чужих."""
        from vpn.link_store import FORMAT_VERSION, save_links, store_path

        root = self._root()
        save_links(root, [self._parse(VLESS)])

        data = json.loads(store_path(root).read_text(encoding="utf-8"))

        self.assertEqual(data["version"], FORMAT_VERSION)


class MergeTests(unittest.TestCase):
    def _parse(self, link: str):
        from vpn.links import parse_link

        return parse_link(link)

    def test_new_servers_are_appended(self) -> None:
        from vpn.link_store import merge

        result = merge([self._parse(VLESS)], [self._parse(TROJAN)])

        self.assertEqual([item.raw for item in result], [VLESS, TROJAN])

    def test_same_link_is_not_added_twice(self) -> None:
        """Подписку обновляют регулярно, и половина серверов в ней те же."""
        from vpn.link_store import merge

        result = merge([self._parse(VLESS)], [self._parse(VLESS)])

        self.assertEqual(len(result), 1)

    def test_a_renamed_server_is_still_the_same_server(self) -> None:
        """У одного сервера в подписке может быть разное имя в разные дни."""
        from vpn.link_store import merge

        import dataclasses

        renamed = dataclasses.replace(self._parse(VLESS), title="Другое имя")

        result = merge([self._parse(VLESS)], [renamed])

        self.assertEqual(len(result), 1)

    def test_empty_inputs_are_fine(self) -> None:
        from vpn.link_store import merge

        self.assertEqual(merge(None, None), [])


if __name__ == "__main__":
    unittest.main()
