"""Экспресс-подбор: пять кандидатов, остановка на первой подтверждённой."""

import unittest
from unittest.mock import Mock

from blockcheck.scan_models import StrategyScanReport
from blockcheck.strategy_search.engine import (
    SearchRequest,
    StrategySearch,
)
from blockcheck.strategy_search.ordering import (
    MODE_BATCH_SIZES,
    Candidate,
    batch_for_mode,
)
from blockcheck.strategy_search.verdict import CONFIRM_ATTEMPTS, VERDICT_WORKING, VERDICT_FAILED


class SmartStrategySearchTests(unittest.TestCase):
    def test_displayed_modes_reach_candidate_selection(self):
        from blockcheck.strategy_scan_page_plans import MODE_ITEMS
        from blockcheck.strategy_scan_targeting import build_selection_state

        candidates = [Candidate(str(i), str(i), "--lua-desync=fake") for i in range(100)]
        for index, ((_key, _text, mode), expected_count) in enumerate(zip(MODE_ITEMS, (5, 30, 80, 100))):
            with self.subTest(mode=mode):
                selection = build_selection_state(
                    protocol_value="tcp_https", udp_scope_value="all", mode_index=index,
                )
                self.assertEqual(selection.mode, mode)
                self.assertEqual(len(batch_for_mode(candidates, selection.mode)), expected_count)

    def test_remembered_sni_variant_is_restored_within_the_express_budget(self):
        from blockcheck.strategy_search.sni_discovery import with_allowed_name

        candidates = [Candidate(f"id_{i}", f"Стратегия {i}", "--lua-desync=fake:tls_mod=sni=example.com") for i in range(10)]
        remembered = with_allowed_name(candidates[0], "vk.com")
        self.assertIsNotNone(remembered)
        env = Mock()
        env.load_candidates.return_value = candidates
        env.load_history.return_value = Mock(confirmed=(remembered.strategy_id,), failed={})
        env.wall_time.return_value = 1.0
        engine = StrategySearch(SearchRequest(target="example.com", mode="smart"), env=env, events=Mock())
        batch, _total = engine._select_batch("test")
        self.assertEqual(len(batch), 5)
        self.assertEqual(batch[0], remembered)

    def test_smart_mode_batch_size(self):
        self.assertIn("smart", MODE_BATCH_SIZES)
        self.assertEqual(MODE_BATCH_SIZES["smart"], 5)

        candidates = [Candidate(f"id_{i}", f"Strat {i}", f"--lua-desync=fake{i}") for i in range(20)]
        batch = batch_for_mode(candidates, "smart")
        self.assertEqual(len(batch), 5)

    def test_smart_mode_stops_on_first_working_strategy(self):
        candidates = [
            Candidate("c1", "Candidate 1", "--lua-desync=fake"),
            Candidate("c2", "Candidate 2", "--lua-desync=split2"),
            Candidate("c3", "Candidate 3", "--lua-desync=multisplit"),
        ]
        request = SearchRequest(
            target="discord.com",
            mode="smart",
        )
        env = Mock()
        env.load_candidates.return_value = candidates
        env.load_history.return_value = Mock(confirmed=(), failed={})
        env.wall_time.return_value = 1000.0
        env.monotonic.return_value = 0.0
        env.strategy_pause_seconds.return_value = 0.0
        env.blob_lines.return_value = []

        events = Mock()
        events.is_cancelled.return_value = False
        engine = StrategySearch(request, env=env, events=events)

        # Baseline: закрыто
        engine._baseline = Mock(return_value=True)
        engine._target = Mock(forced=False, host="discord.com", addresses=["162.159.135.232"])
        # Pass control: закрыто
        engine._pass_control = Mock(return_value=True)

        # Кандидат 1: не работает, Кандидат 2: работает
        from blockcheck.strategy_search.engine import _StrategyRun, _Attempt
        run_fail = _StrategyRun(verdict=VERDICT_FAILED, attempts=[_Attempt(passed=False, reason="timeout", time_ms=0.0)])
        run_success = _StrategyRun(verdict=VERDICT_WORKING, attempts=[_Attempt(passed=True, reason="ok", time_ms=32.0)])

        engine._test_strategy = Mock(side_effect=[run_fail, run_success])

        result = engine.run()

        # Должен проверить только 2 стратегии и остановиться на успехе!
        self.assertEqual(engine._test_strategy.call_count, 2)
        self.assertEqual(len(result.working_strategies), 1)
        self.assertEqual(result.working_strategies[0].strategy_name, "Candidate 2")
        # Экспресс подтверждает находку так же, как остальные режимы:
        # один удачный проход бывает и у нестабильной стратегии.
        self.assertEqual(result.working_strategies[0].attempts_total, CONFIRM_ATTEMPTS)


if __name__ == "__main__":
    unittest.main()
