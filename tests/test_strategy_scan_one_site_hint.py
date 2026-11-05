"""Короткая подсказка помогает сравнивать стратегии для одного сайта."""

from __future__ import annotations

import unittest

from app.ui_texts import tr
from blockcheck.strategy_scan_page_plans import ONE_SITE_HINT_RU, build_language_plan, build_protocol_ui_plan
from blockcheck.strategy_search.probe_profile import PROTOCOL_STUN_VOICE, PROTOCOL_TCP_HTTPS, PROTOCOL_UDP_GAMES

_KEY = "page.strategy_scan.one_site_hint"


class OneSiteHintTests(unittest.TestCase):
    def test_hint_is_shown_only_when_a_site_is_checked(self) -> None:
        for protocol, expected in (
            (PROTOCOL_TCP_HTTPS, True),
            (PROTOCOL_STUN_VOICE, False),
            (PROTOCOL_UDP_GAMES, False),
        ):
            with self.subTest(protocol=protocol):
                plan = build_protocol_ui_plan(scan_protocol=protocol, current_value="")
                self.assertEqual(plan.show_one_site_hint, expected)

    def test_text_explains_why_sites_are_checked_one_by_one_in_both_languages(self) -> None:
        ru = tr(_KEY, language="ru")
        en = tr(_KEY, language="en")

        self.assertEqual(ru, ONE_SITE_HINT_RU)
        for phrase in ("по одному", "не открывайте", "сравнить результаты"):
            self.assertIn(phrase, ru)
        self.assertTrue(en)
        self.assertNotEqual(en, ru)
        for phrase in ("one at a time", "compare strategies"):
            self.assertIn(phrase, en)

    def test_language_switch_carries_the_hint(self) -> None:
        self.assertEqual(build_language_plan(language="ru").one_site_hint, ONE_SITE_HINT_RU)
        self.assertEqual(build_language_plan(language="en").one_site_hint, tr(_KEY, language="en"))


if __name__ == "__main__":
    unittest.main()
