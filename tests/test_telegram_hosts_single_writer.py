"""Telegram в hosts пишет только страница Telegram Proxy.

Раньше те же домены прописывала ещё и плитка редактора hosts. Два
писателя переписывали друг друга: «Прописать» на странице прокси
вырезало строки Telegram из блока net67, а сверка при запуске
возвращала их обратно.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from hosts.proxy_domains import TELEGRAM_HOSTS_SERVICE, _parse_hosts_catalog_json  # noqa: E402
from telegram_proxy.telegram_hosts import (  # noqa: E402
    TELEGRAM_DOMAINS,
    TelegramHostsError,
    split_hosts_editor_selection,
)


_CATALOG_TELEGRAM_FILE = PROJECT_ROOT / "json" / "hosts_catalog" / "hosts" / "070_telegram.json"


def _catalog_text(*names: str) -> str:
    return json.dumps(
        {
            "services": [
                {
                    "name": name,
                    "category": "direct",
                    "mode": "hosts",
                    "hosts": [{"ip": "149.154.167.220", "host": f"{index}.example.org"}],
                }
                for index, name in enumerate(names)
            ]
        },
        ensure_ascii=False,
    )


class CatalogHidesTelegramTests(unittest.TestCase):
    def test_telegram_is_not_a_service_of_the_editor(self) -> None:
        catalog = _parse_hosts_catalog_json(_catalog_text(TELEGRAM_HOSTS_SERVICE, "Discord"))

        self.assertEqual(catalog.service_order, ["Discord"])
        self.assertNotIn(TELEGRAM_HOSTS_SERVICE, catalog.services)

    def test_proxy_page_knows_every_domain_the_tile_wrote(self) -> None:
        # Каталог из zapret может пополниться — тогда этот тест скажет,
        # какие домены добавить в TELEGRAM_DOMAINS, иначе при переносе
        # они пропадут у тех, кто пользовался плиткой.
        if not _CATALOG_TELEGRAM_FILE.exists():
            self.skipTest("файла Telegram в каталоге нет")
        data = json.loads(_CATALOG_TELEGRAM_FILE.read_text(encoding="utf-8"))
        tile_domains = {row["host"].lower() for row in data["hosts"]}

        self.assertEqual(tile_domains - {d.lower() for d in TELEGRAM_DOMAINS}, set())


class SplitSelectionTests(unittest.TestCase):
    def test_enabled_tile_is_taken_out_and_reported(self) -> None:
        kept, found, enabled = split_hosts_editor_selection(
            {TELEGRAM_HOSTS_SERVICE: "hosts", "Discord": "hosts"}
        )

        self.assertEqual(kept, {"Discord": "hosts"})
        self.assertTrue(found)
        self.assertTrue(enabled)

    def test_disabled_tile_is_taken_out_but_not_enabled(self) -> None:
        kept, found, enabled = split_hosts_editor_selection({TELEGRAM_HOSTS_SERVICE: "off"})

        self.assertEqual(kept, {})
        self.assertTrue(found)
        self.assertFalse(enabled)

    def test_selection_without_telegram_is_untouched(self) -> None:
        kept, found, enabled = split_hosts_editor_selection({"Discord": "hosts"})

        self.assertEqual(kept, {"Discord": "hosts"})
        self.assertFalse(found)
        self.assertFalse(enabled)


class StartupHandoverTests(unittest.TestCase):
    def _run(self, selection, *, add_error=None):
        from hosts import commands

        calls: list[str] = []
        saved: list[dict] = []

        def fake_add():
            calls.append("add")
            if add_error is not None:
                raise add_error
            return True, ""

        with (
            patch("telegram_proxy.telegram_hosts.add_telegram_hosts", side_effect=fake_add),
            patch.object(commands, "save_user_selection", side_effect=lambda s: saved.append(s) or True),
        ):
            result = commands._hand_telegram_to_proxy_page(selection)
        return result, calls, saved

    def test_enabled_tile_moves_to_proxy_page_before_leaving_selection(self) -> None:
        result, calls, saved = self._run({TELEGRAM_HOSTS_SERVICE: "hosts", "Discord": "hosts"})

        self.assertEqual(calls, ["add"])
        self.assertEqual(saved, [{"Discord": "hosts"}])
        self.assertEqual(result, {"Discord": "hosts"})

    def test_failed_write_keeps_selection_for_next_start(self) -> None:
        selection = {TELEGRAM_HOSTS_SERVICE: "hosts"}
        result, calls, saved = self._run(selection, add_error=TelegramHostsError("только чтение"))

        self.assertEqual(calls, ["add"])
        self.assertEqual(saved, [])
        self.assertEqual(result, selection)

    def test_disabled_tile_only_leaves_selection(self) -> None:
        result, calls, saved = self._run({TELEGRAM_HOSTS_SERVICE: "off"})

        self.assertEqual(calls, [])
        self.assertEqual(saved, [{}])
        self.assertEqual(result, {})

    def test_nothing_to_move_writes_nothing(self) -> None:
        result, calls, saved = self._run({"Discord": "hosts"})

        self.assertEqual((calls, saved), ([], []))
        self.assertEqual(result, {"Discord": "hosts"})


class WizardWritesTelegramThroughProxyPageTests(unittest.TestCase):
    def _apply(self, **kwargs) -> list[str]:
        from wizard.apply import WizardWriters, apply_wizard

        calls: list[str] = []
        writers = WizardWriters(
            set_gui_autostart_enabled=lambda _v: "",
            set_dpi_autostart=lambda _v: None,
            set_tray_close_mode=lambda _v: None,
            apply_hosts=lambda _p: "",
            set_wizard_services=lambda _v: None,
            set_wizard_completed=lambda _v: None,
            set_telegram_proxy_with_bypass=lambda _v: "",
            add_telegram_hosts=lambda: calls.append("telegram") or "",
        )
        apply_wizard(autostart_with_windows=False, minimize_to_tray=False, writers=writers, **kwargs)
        return calls

    def test_social_group_writes_telegram_block(self) -> None:
        self.assertEqual(self._apply(selection={"messengers"}, hosts_groups={"social"}), ["telegram"])

    def test_without_social_group_telegram_is_not_written(self) -> None:
        self.assertEqual(self._apply(selection={"messengers"}, hosts_groups={"ai"}), [])

    def test_legacy_path_follows_messengers_choice(self) -> None:
        self.assertEqual(self._apply(selection={"messengers"}), ["telegram"])
        self.assertEqual(self._apply(selection={"video"}), [])


if __name__ == "__main__":
    unittest.main()
