from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass, field
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


@dataclass
class _Recorder:
    """Записывает вызовы и позволяет заказать падение конкретного шага."""

    calls: list[str] = field(default_factory=list)
    fail: set[str] = field(default_factory=set)
    integrity: list = field(default_factory=list)
    probe: tuple[int, tuple[str, ...]] = (3, ())
    #: Готовность Telegram: (готов, что сказать человеку).
    telegram_ready: tuple[bool, str] = (True, "")

    def _op(self, name: str):
        def run(*_args, **_kwargs):
            self.calls.append(name)
            if name in self.fail:
                return (False, f"{name} упал")
            return (True, "")

        return run

    def build(self):
        from oneclick.runner import OneClickDeps

        return OneClickDeps(
            check_conflicts=self._op("check_conflicts"),
            start_dpi=self._op("start_dpi"),
            stop_dpi=self._op("stop_dpi"),
            check_telegram_ready=lambda: (
                self.calls.append("check_telegram_ready"),
                self.telegram_ready,
            )[1],
            start_telegram_proxy=self._op("start_telegram_proxy"),
            stop_telegram_proxy=self._op("stop_telegram_proxy"),
            backup_hosts=self._op("backup_hosts"),
            apply_hosts=self._op("apply_hosts"),
            restore_hosts=self._op("restore_hosts"),
            check_dns_integrity=lambda: (self.calls.append("check_dns_integrity"), self.integrity)[1],
            apply_dns=self._op("apply_dns"),
            restore_dns=self._op("restore_dns"),
            probe_domains=lambda: (self.calls.append("probe_domains"), self.probe)[1],
        )


def _request(**kwargs):
    from oneclick.plans import OneClickRequest

    return OneClickRequest(**kwargs)


class OneClickEnableTests(unittest.TestCase):
    def test_happy_path_reaches_running(self) -> None:
        from oneclick.runner import OneClickRunner
        from oneclick.state import OneClickState

        rec = _Recorder()
        runner = OneClickRunner(rec.build())

        outcome = runner.enable(_request(services=frozenset({"messengers"}), needs_telegram_proxy=True))

        self.assertIs(outcome.state, OneClickState.RUNNING)
        self.assertIs(runner.state, OneClickState.RUNNING)
        self.assertIn("start_dpi", rec.calls)
        self.assertIn("start_telegram_proxy", rec.calls)

    def test_hosts_backup_runs_before_apply(self) -> None:
        from oneclick.runner import OneClickRunner

        rec = _Recorder()
        OneClickRunner(rec.build()).enable(
            _request(hosts_entries={"a.com": "1.2.3.4"})
        )

        self.assertLess(rec.calls.index("backup_hosts"), rec.calls.index("apply_hosts"))

    def test_hosts_not_applied_when_backup_fails(self) -> None:
        """Без копии hosts править нельзя: откатывать будет нечем."""
        from oneclick.runner import OneClickRunner
        from oneclick.state import OneClickState

        rec = _Recorder(fail={"backup_hosts"})
        outcome = OneClickRunner(rec.build()).enable(
            _request(hosts_entries={"a.com": "1.2.3.4"})
        )

        self.assertIs(outcome.state, OneClickState.ERROR)
        self.assertNotIn("apply_hosts", rec.calls)

    def test_dns_untouched_when_no_spoofing(self) -> None:
        from oneclick.runner import OneClickRunner

        rec = _Recorder(integrity=[_FakeIntegrity("a.com")])
        OneClickRunner(rec.build()).enable(_request())

        self.assertIn("check_dns_integrity", rec.calls)
        self.assertNotIn("apply_dns", rec.calls)

    def test_dns_changed_when_spoofing_detected(self) -> None:
        from oneclick.runner import OneClickRunner

        rec = _Recorder(integrity=[_FakeIntegrity("a.com", is_consistent=False)])
        OneClickRunner(rec.build()).enable(_request())

        self.assertIn("apply_dns", rec.calls)

    def test_unreachable_sites_do_not_break_running_state(self) -> None:
        """winws запущен, стратегия не подошла — это не ошибка запуска."""
        from oneclick.runner import OneClickRunner
        from oneclick.state import OneClickState

        rec = _Recorder(probe=(3, ("youtube.com",)))
        outcome = OneClickRunner(rec.build()).enable(_request())

        self.assertIs(outcome.state, OneClickState.RUNNING)
        self.assertEqual(outcome.failed_domains, ("youtube.com",))
        self.assertIn("youtube.com", outcome.message)

    def test_exception_in_step_becomes_error_not_crash(self) -> None:
        from oneclick.runner import OneClickRunner
        from oneclick.state import OneClickState

        rec = _Recorder()
        deps = rec.build()

        def boom():
            raise RuntimeError("нет прав администратора")

        deps.start_dpi = boom
        outcome = OneClickRunner(deps).enable(_request())

        self.assertIs(outcome.state, OneClickState.ERROR)
        self.assertIn("нет прав администратора", outcome.message)


class OneClickRollbackTests(unittest.TestCase):
    def test_failure_rolls_back_earlier_steps_in_reverse(self) -> None:
        from oneclick.runner import OneClickRunner

        rec = _Recorder(fail={"apply_hosts"})
        OneClickRunner(rec.build()).enable(
            _request(
                services=frozenset({"messengers"}),
                needs_telegram_proxy=True,
                hosts_entries={"a.com": "1.2.3.4"},
            )
        )

        self.assertIn("restore_hosts", rec.calls)
        self.assertLess(rec.calls.index("stop_telegram_proxy"), rec.calls.index("stop_dpi"))

    def test_dns_not_rolled_back_when_it_was_skipped(self) -> None:
        from oneclick.runner import OneClickRunner

        rec = _Recorder(integrity=[_FakeIntegrity("a.com")], fail={"probe_domains"})
        deps = rec.build()

        def failing_probe():
            rec.calls.append("probe_domains")
            raise RuntimeError("сеть недоступна")

        deps.probe_domains = failing_probe
        OneClickRunner(deps).enable(_request())

        self.assertNotIn("restore_dns", rec.calls)

    def test_rollback_continues_after_a_failing_step(self) -> None:
        from oneclick.runner import OneClickRunner

        rec = _Recorder(fail={"apply_hosts", "restore_hosts"})
        OneClickRunner(rec.build()).enable(
            _request(
                services=frozenset({"messengers"}),
                needs_telegram_proxy=True,
                hosts_entries={"a.com": "1.2.3.4"},
            )
        )

        self.assertIn("stop_dpi", rec.calls)


class OneClickDisableTests(unittest.TestCase):
    def test_disable_stops_only_reversible_parts(self) -> None:
        from oneclick.runner import OneClickRunner
        from oneclick.state import OneClickState

        rec = _Recorder()
        outcome = OneClickRunner(rec.build()).disable()

        self.assertIs(outcome.state, OneClickState.OFF)
        self.assertIn("stop_dpi", rec.calls)
        self.assertNotIn("restore_hosts", rec.calls)
        self.assertNotIn("restore_dns", rec.calls)

    def test_disable_failure_reports_error(self) -> None:
        from oneclick.runner import OneClickRunner
        from oneclick.state import OneClickState

        rec = _Recorder(fail={"stop_dpi"})
        outcome = OneClickRunner(rec.build()).disable()

        self.assertIs(outcome.state, OneClickState.ERROR)


class OneClickReportTests(unittest.TestCase):
    def test_states_are_reported_in_order(self) -> None:
        from oneclick.runner import OneClickRunner
        from oneclick.state import OneClickState

        rec = _Recorder()
        deps = rec.build()
        seen: list = []
        deps.report = lambda state, _message: seen.append(state)

        OneClickRunner(deps).enable(_request())

        self.assertEqual(seen[0], OneClickState.PREPARING)
        self.assertIn(OneClickState.CHECKING, seen)
        self.assertEqual(seen[-1], OneClickState.RUNNING)

    def test_broken_report_callback_does_not_break_run(self) -> None:
        from oneclick.runner import OneClickRunner
        from oneclick.state import OneClickState

        rec = _Recorder()
        deps = rec.build()

        def bad_report(*_args):
            raise RuntimeError("UI уже закрыт")

        deps.report = bad_report
        outcome = OneClickRunner(deps).enable(_request())

        self.assertIs(outcome.state, OneClickState.RUNNING)


if __name__ == "__main__":
    unittest.main()
