from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class GlobalSearchIndexTests(unittest.TestCase):
    def test_ui_texts_are_separate_from_search_index(self) -> None:
        import app.ui_texts as ui_texts
        import app.search_index as search_index

        # Проверялось на строке страницы доната — её больше нет, берём
        # любую живую. Суть проверки не в конкретной строке: тексты
        # интерфейса и указатель поиска должны лежать в разных модулях.
        self.assertIn("page.about.title", ui_texts.TEXTS)
        self.assertFalse(hasattr(ui_texts, "SEARCH_ENTRIES"))
        self.assertTrue(hasattr(search_index, "find_search_entries"))



    def test_about_support_search_opens_about_tab(self) -> None:
        from app.search_index import SEARCH_ENTRIES

        support_entries = [
            entry for entry in SEARCH_ENTRIES
            if entry.entry_id.startswith("about.support.")
        ]

        self.assertTrue(support_entries)
        self.assertTrue(all(entry.tab_key == "about" for entry in support_entries))
        self.assertFalse(any(entry.entry_id == "about.tab.support" for entry in SEARCH_ENTRIES))


    def test_profile_search_entries_use_profile_summary_not_list_contents(self) -> None:
        from app.page_names import PageName
        from app.search_index import build_profile_search_entries, find_search_entries
        from settings.mode import ZAPRET2_MODE

        profile = SimpleNamespace(
            key="profile:0",
            display_name="Discord Voice",
            strategy_name="Fake",
            group_name="Voice",
            list_type="hostlist",
            match_lines=("--hostlist=lists/private-discord-file.txt",),
        )

        entries = build_profile_search_entries(ZAPRET2_MODE, (profile,))

        discord_matches = find_search_entries(
            "discord",
            language="ru",
            visible_pages={PageName.ZAPRET2_PRESET_SETUP},
            extra_entries=entries,
        )
        file_matches = find_search_entries(
            "private-discord-file",
            language="ru",
            visible_pages={PageName.ZAPRET2_PRESET_SETUP},
            extra_entries=entries,
        )

        self.assertTrue(any(match.entry.kind == "profile" for match in discord_matches))
        self.assertFalse(any(match.entry.kind == "profile" for match in file_matches))

    def test_preset_search_entries_use_manifest_not_preset_body(self) -> None:
        from app.page_names import PageName
        from app.search_index import build_preset_search_entries, find_search_entries
        from settings.mode import ZAPRET2_MODE

        manifest = SimpleNamespace(
            file_name="gaming.txt",
            name="Gaming Preset",
            body_text="internal-hostlist-content.example",
        )

        entries = build_preset_search_entries(ZAPRET2_MODE, (manifest,))

        name_matches = find_search_entries(
            "gaming",
            language="ru",
            visible_pages={PageName.ZAPRET2_USER_PRESETS},
            extra_entries=entries,
        )
        body_matches = find_search_entries(
            "internal-hostlist-content",
            language="ru",
            visible_pages={PageName.ZAPRET2_USER_PRESETS},
            extra_entries=entries,
        )

        self.assertTrue(any(match.entry.kind == "preset" for match in name_matches))
        self.assertFalse(any(match.entry.kind == "preset" for match in body_matches))


if __name__ == "__main__":
    unittest.main()


    def test_premium_page_is_not_searchable(self) -> None:
        """Подписки удалены: страница скрыта и не должна находиться поиском."""
        from app.page_names import PageName
        from settings.mode import ZAPRET2_MODE
        from ui.navigation.schema import get_sidebar_search_pages_for_method

        visible = get_sidebar_search_pages_for_method(ZAPRET2_MODE, set(PageName), advanced=True)

        self.assertNotIn(PageName.PREMIUM, visible)

    def test_search_finds_a_real_page(self) -> None:
        """Поиск в принципе работает — проверяем на существующем разделе."""
        from app.page_names import PageName
        from app.search_index import find_search_entries
        from settings.mode import ZAPRET2_MODE
        from ui.navigation.schema import get_sidebar_search_pages_for_method

        visible = get_sidebar_search_pages_for_method(ZAPRET2_MODE, set(PageName), advanced=True)
        matches = find_search_entries("логи", language="ru", visible_pages=visible, max_results=10)

        self.assertTrue(matches)


if __name__ == "__main__":
    unittest.main()
