"""Сайты BlockCheck стартуют в случайном порядке, а отчёт остаётся в прежнем."""

import random
import unittest

from diagnostics.limits import SITE_START_GAP_S, SITES_AT_ONCE
from diagnostics.run_context import submit_in_random_order


class SubmitInRandomOrderTests(unittest.TestCase):
    def test_every_item_once_and_results_in_original_order(self) -> None:
        started: list[str] = []

        def submit(item: str) -> str:
            started.append(item)
            return f"итог {item}"

        items = [f"сайт{i}" for i in range(12)]
        random.seed(7)
        results = submit_in_random_order(items, submit)

        self.assertEqual(sorted(started), sorted(items))
        self.assertEqual(results, [f"итог {item}" for item in items])
        # С таким числом сайтов совпадение с исходным порядком — не случайность.
        self.assertNotEqual(started, items)

    def test_empty(self) -> None:
        self.assertEqual(submit_in_random_order([], lambda item: item), [])

    def test_browser_like_pace(self) -> None:
        # Человек открывает сайты по одному-два; десять рукопожатий в секунду — узор.
        self.assertLessEqual(SITES_AT_ONCE, 4)
        low, high = SITE_START_GAP_S
        self.assertTrue(0 < low < high)


if __name__ == "__main__":
    unittest.main()
