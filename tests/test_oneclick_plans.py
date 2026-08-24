from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


@dataclass
class _FakeIntegrity:
    domain: str
    is_comparable: bool = True
    is_consistent: bool = True
    is_stub: bool = False


class OneClickEnablePlanTests(unittest.TestCase):
    def test_minimal_plan_has_conflicts_and_dpi(self) -> None:
        from oneclick.plans import OneClickRequest, build_enable_plan
        from oneclick.state import StepKey

        plan = build_enable_plan(OneClickRequest(allow_dns_fix=False, run_selfcheck=False))

        self.assertEqual([s.key for s in plan], [StepKey.CONFLICTS, StepKey.DPI])

    def test_telegram_proxy_only_when_service_selected(self) -> None:
        from oneclick.plans import OneClickRequest, build_enable_plan
        from oneclick.state import StepKey

        without = build_enable_plan(OneClickRequest(services=frozenset({"video"})))
        with_tg = build_enable_plan(OneClickRequest(services=frozenset({"messengers"}), needs_telegram_proxy=True))

        self.assertNotIn(StepKey.TELEGRAM_PROXY, [s.key for s in without])
        self.assertIn(StepKey.TELEGRAM_PROXY, [s.key for s in with_tg])

    def test_hosts_step_absent_without_profiles(self) -> None:
        from oneclick.plans import OneClickRequest, build_enable_plan
        from oneclick.state import StepKey

        plan = build_enable_plan(OneClickRequest(hosts_entries={}))

        self.assertNotIn(StepKey.HOSTS, [s.key for s in plan])

    def test_persistent_steps_go_after_reversible_ones(self) -> None:
        """Главный инвариант порядка: необратимое — в самом конце."""
        from oneclick.plans import OneClickRequest, build_enable_plan

        plan = build_enable_plan(
            OneClickRequest(
                services=frozenset({"messengers"}),
                needs_telegram_proxy=True,
                hosts_entries={"example.com": "1.2.3.4"},
            )
        )
        changing = [s for s in plan if not s.read_only]
        first_persistent = next(i for i, s in enumerate(changing) if s.persistent)
        last_reversible = max(i for i, s in enumerate(changing) if not s.persistent)

        self.assertLess(
            last_reversible,
            first_persistent,
            "персистентный шаг оказался раньше обратимого — при сбое откатывать будет нечем",
        )


class OneClickRollbackTests(unittest.TestCase):
    def test_rollback_is_reverse_and_includes_failed_step(self) -> None:
        """Упавший шаг мог измениться до падения — откатываем и его."""
        from oneclick.plans import build_rollback_plan
        from oneclick.state import StepKey, StepResult

        results = [
            StepResult(StepKey.CONFLICTS, ok=True),
            StepResult(StepKey.DPI, ok=True),
            StepResult(StepKey.TELEGRAM_PROXY, ok=True),
            StepResult(StepKey.HOSTS, ok=False, message="нет прав"),
        ]

        self.assertEqual(
            build_rollback_plan(results),
            (StepKey.HOSTS, StepKey.TELEGRAM_PROXY, StepKey.DPI),
        )

    def test_read_only_steps_are_never_rolled_back(self) -> None:
        from oneclick.plans import build_rollback_plan
        from oneclick.state import StepKey, StepResult

        results = [
            StepResult(StepKey.CONFLICTS, ok=True),
            StepResult(StepKey.DPI, ok=True),
            StepResult(StepKey.SELFCHECK, ok=True),
        ]

        self.assertEqual(build_rollback_plan(results), (StepKey.DPI,))

    def test_skipped_steps_are_not_rolled_back(self) -> None:
        from oneclick.plans import build_rollback_plan
        from oneclick.state import StepKey, StepResult

        results = [
            StepResult(StepKey.DPI, ok=True),
            StepResult(StepKey.DNS, ok=True, skipped=True),
        ]

        self.assertEqual(build_rollback_plan(results), (StepKey.DPI,))

    def test_disable_plan_does_not_touch_hosts_or_dns(self) -> None:
        from oneclick.plans import build_disable_plan
        from oneclick.state import StepKey

        plan = build_disable_plan()

        self.assertNotIn(StepKey.HOSTS, plan)
        self.assertNotIn(StepKey.DNS, plan)


class OneClickDnsDecisionTests(unittest.TestCase):
    def test_clean_dns_is_left_alone(self) -> None:
        from oneclick.plans import should_change_dns

        change, _ = should_change_dns([_FakeIntegrity("a.com"), _FakeIntegrity("b.com")])

        self.assertFalse(change)

    def test_inconsistent_dns_triggers_change(self) -> None:
        from oneclick.plans import should_change_dns

        change, message = should_change_dns(
            [_FakeIntegrity("a.com"), _FakeIntegrity("b.com", is_consistent=False)]
        )

        self.assertTrue(change)
        self.assertIn("b.com", message)

    def test_stub_dns_triggers_change(self) -> None:
        from oneclick.plans import should_change_dns

        change, _ = should_change_dns([_FakeIntegrity("a.com", is_stub=True)])

        self.assertTrue(change)

    def test_uncomparable_results_do_not_touch_network(self) -> None:
        """Не смогли проверить — не лезем в сеть."""
        from oneclick.plans import should_change_dns

        change, _ = should_change_dns([_FakeIntegrity("a.com", is_comparable=False)])

        self.assertFalse(change)

    def test_empty_results_do_not_touch_network(self) -> None:
        from oneclick.plans import should_change_dns

        self.assertFalse(should_change_dns([])[0])


class OneClickSummaryTests(unittest.TestCase):
    def test_all_ok_gives_running(self) -> None:
        from oneclick.plans import summarize
        from oneclick.state import OneClickState, StepKey, StepResult

        outcome = summarize([StepResult(StepKey.DPI, ok=True)])

        self.assertIs(outcome.state, OneClickState.RUNNING)
        self.assertTrue(outcome.ok)

    def test_failure_gives_error_with_first_reason(self) -> None:
        from oneclick.plans import summarize
        from oneclick.state import OneClickState, StepKey, StepResult

        outcome = summarize(
            [
                StepResult(StepKey.DPI, ok=False, message="winws не запустился"),
                StepResult(StepKey.HOSTS, ok=False, message="нет прав"),
            ]
        )

        self.assertIs(outcome.state, OneClickState.ERROR)
        self.assertEqual(outcome.message, "winws не запустился")

    def test_skipped_step_is_not_a_failure(self) -> None:
        from oneclick.plans import summarize
        from oneclick.state import OneClickState, StepKey, StepResult

        outcome = summarize(
            [
                StepResult(StepKey.DPI, ok=True),
                StepResult(StepKey.DNS, ok=False, skipped=True),
            ]
        )

        self.assertIs(outcome.state, OneClickState.RUNNING)


class OneClickSelfcheckMessageTests(unittest.TestCase):
    def test_all_domains_reachable(self) -> None:
        from oneclick.plans import build_selfcheck_message

        self.assertIn("открываются", build_selfcheck_message(total=3, failed_domains=()))

    def test_partial_failure_lists_domains(self) -> None:
        from oneclick.plans import build_selfcheck_message

        message = build_selfcheck_message(total=3, failed_domains=("youtube.com",))

        self.assertIn("частично", message)
        self.assertIn("youtube.com", message)

    def test_total_failure_is_distinguished_from_partial(self) -> None:
        from oneclick.plans import build_selfcheck_message

        message = build_selfcheck_message(total=2, failed_domains=("a.com", "b.com"))

        self.assertIn("не открываются", message)
        self.assertNotIn("частично", message)

    def test_long_failure_list_is_truncated(self) -> None:
        from oneclick.plans import build_selfcheck_message

        message = build_selfcheck_message(
            total=9,
            failed_domains=("a.com", "b.com", "c.com", "d.com", "e.com"),
        )

        self.assertIn("ещё 2", message)
        self.assertNotIn("e.com", message)


if __name__ == "__main__":
    unittest.main()
