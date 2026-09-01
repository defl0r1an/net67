# tests/test_vpn_tab_texts.py
"""Тексты вкладок VPN обязаны описывать свою вкладку, а не соседнюю.

Примечание внизу страницы было одно на обе вкладки и рассказывало про
службу Windows и клиент AmneziaWG. На вкладке подключения по ссылке это
неправда от первого слова до последнего: там поднимается ядро Xray,
никакой службы нет, а совет «остановите обход и подключитесь снова»
отправляет чинить не то.

Примечание, которое врёт, хуже отсутствующего: по нему начинают
действовать.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vpn.tabs import (  # noqa: E402
    TAB_AMNEZIA,
    TAB_HINTS,
    TAB_INPUT_TITLES,
    TAB_LINKS,
    TAB_NOTES,
    TAB_ORDER,
    TAB_PLACEHOLDERS,
    TAB_SUBTITLES,
    TAB_TITLES,
    TAB_WARNINGS,
)


ALL_TABLES = {
    "TAB_TITLES": TAB_TITLES,
    "TAB_SUBTITLES": TAB_SUBTITLES,
    "TAB_INPUT_TITLES": TAB_INPUT_TITLES,
    "TAB_HINTS": TAB_HINTS,
    "TAB_PLACEHOLDERS": TAB_PLACEHOLDERS,
    "TAB_NOTES": TAB_NOTES,
    "TAB_WARNINGS": TAB_WARNINGS,
}


class CoverageTests(unittest.TestCase):
    def test_every_table_covers_every_tab(self) -> None:
        """Пропущенная вкладка — это KeyError при переключении."""
        for name, table in ALL_TABLES.items():
            for tab in TAB_ORDER:
                self.assertIn(tab, table, f"{name} не знает вкладку {tab}")


class NoteTests(unittest.TestCase):
    def test_links_note_does_not_mention_amnezia(self) -> None:
        note = TAB_NOTES[TAB_LINKS].lower()
        self.assertNotIn("amnezia", note)
        self.assertNotIn("wireguard", note)
        # Проверяем утверждение, а не слово: «служба не заводится» здесь
        # как раз правда и стоит того, чтобы быть сказанной. Ловим ровно
        # обратное — обещание, что туннель поднимает служба.
        self.assertNotIn("поднимается службой", note)

    def test_links_note_names_the_real_engine(self) -> None:
        self.assertIn("Xray", TAB_NOTES[TAB_LINKS])

    def test_amnezia_note_keeps_its_own_explanation(self) -> None:
        self.assertIn("AmneziaWG", TAB_NOTES[TAB_AMNEZIA])

    def test_notes_differ(self) -> None:
        self.assertNotEqual(TAB_NOTES[TAB_LINKS], TAB_NOTES[TAB_AMNEZIA])

    def test_both_notes_warn_about_the_bypass(self) -> None:
        """Обход мешает рукопожатию на обеих вкладках — это общее."""
        for tab in TAB_ORDER:
            self.assertIn("бход", TAB_NOTES[tab], f"вкладка {tab} молчит про обход")


class WarningTests(unittest.TestCase):
    def test_amnezia_warns_about_bugs(self) -> None:
        warning = TAB_WARNINGS[TAB_AMNEZIA]
        self.assertTrue(warning.strip(), "предупреждение пустое")
        self.assertIn("сбои", warning)

    def test_amnezia_points_to_the_working_tab(self) -> None:
        """Предупреждение без выхода — просто плохая новость."""
        self.assertIn("ссылке", TAB_WARNINGS[TAB_AMNEZIA])

    def test_links_tab_has_nothing_to_warn_about(self) -> None:
        self.assertEqual(TAB_WARNINGS[TAB_LINKS], "")


class PageWiringTests(unittest.TestCase):
    """Тексты должны меняться вместе с вкладкой, а не остаться от первой.

    Файл читается как текст: импорт страницы потянул бы Qt с
    графическими библиотеками, а проверка — про то, что обработчик
    смены вкладки трогает нужные подписи.
    """

    SOURCE = Path(__file__).resolve().parents[1] / "src" / "vpn" / "ui" / "page.py"

    def _tab_change_handler(self) -> str:
        source = self.SOURCE.read_text(encoding="utf-8")
        start = source.index("    def _on_tab_changed(self, key: str) -> None:")
        end = source.index("\n    def ", start + 10)
        return source[start:end]

    def test_the_page_file_exists(self) -> None:
        self.assertTrue(self.SOURCE.is_file(), f"не найден {self.SOURCE}")

    def test_note_is_updated_on_tab_change(self) -> None:
        self.assertIn("TAB_NOTES[tab]", self._tab_change_handler())

    def test_warning_is_updated_on_tab_change(self) -> None:
        self.assertIn("_sync_warning_label(tab)", self._tab_change_handler())

    def test_warning_is_applied_on_first_paint_too(self) -> None:
        """Иначе предупреждение появлялось бы только со второго захода."""
        source = self.SOURCE.read_text(encoding="utf-8")
        self.assertIn("self._sync_warning_label(self._tab)", source)

    def test_hardcoded_amnezia_note_is_gone_from_the_page(self) -> None:
        source = self.SOURCE.read_text(encoding="utf-8")
        self.assertNotIn(
            "Туннель поднимается службой Windows",
            source,
            "текст примечания снова вшит в страницу вместо таблицы вкладок",
        )


if __name__ == "__main__":
    unittest.main()
