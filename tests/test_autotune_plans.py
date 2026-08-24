"""Автоподбор при запуске: когда искать и куда класть найденное.

Замысел: после старта движка проверить YouTube, Discord и Rutracker.
Если что-то не открывается даже с включённым обходом, значит пресет
провайдера этой сети не подошёл — надо искать стратегию перебором.

Перебор идёт минутами на каждую цель, поэтому два правила здесь важнее
всего остального, и оба про «не сделать хуже»:

* искать только когда движок уже работает — иначе недоступным окажется
  всё, и минуты сгорят на каждой машине впустую;
* не повторять перебор для той же цели в одном сеансе.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

PRESET = PROJECT_SRC / "presets" / "builtin" / "winws2" / "Стандартный 1.txt"


def _results(**pairs):
    from autotune.plans import CheckResult

    return [CheckResult(key, available) for key, available in pairs.items()]


class DecisionTests(unittest.TestCase):
    def test_no_scan_while_the_engine_is_down(self) -> None:
        """Иначе недоступно всё, и перебор запустится на пустом месте."""
        from autotune.plans import Decision, build_plan

        plan = build_plan(_results(youtube=False, discord=False), engine_running=False)

        self.assertIs(plan.decision, Decision.ENGINE_DOWN)
        self.assertEqual(plan.targets, ())

    def test_no_scan_when_everything_opens(self) -> None:
        from autotune.plans import Decision, build_plan

        plan = build_plan(_results(youtube=True, discord=True), engine_running=True)

        self.assertIs(plan.decision, Decision.NOTHING)
        self.assertEqual(plan.targets, ())

    def test_scan_only_the_broken_ones(self) -> None:
        from autotune.plans import Decision, build_plan

        plan = build_plan(
            _results(youtube=False, discord=True, rutracker=False),
            engine_running=True,
        )

        self.assertIs(plan.decision, Decision.SCAN)
        self.assertEqual(plan.targets, ("youtube", "rutracker"))

    def test_the_same_target_is_not_scanned_twice(self) -> None:
        """Перебор идёт минутами — по кругу его гонять нельзя."""
        from autotune.plans import build_plan

        plan = build_plan(
            _results(youtube=False, rutracker=False),
            engine_running=True,
            already_scanned=["youtube"],
        )

        self.assertEqual(plan.targets, ("rutracker",))

    def test_repeat_check_is_case_insensitive(self) -> None:
        from autotune.plans import Decision, build_plan

        plan = build_plan(
            _results(youtube=False),
            engine_running=True,
            already_scanned=["YouTube"],
        )

        self.assertIs(plan.decision, Decision.NOTHING)


class ApplyTargetTests(unittest.TestCase):
    def test_youtube_gets_its_own_profiles_and_the_catch_all(self) -> None:
        """Профиль сайта чинит сайт, общий по адресам — доступ вообще."""
        from autotune.plans import profiles_to_update
        from autotune.targets import CATCH_ALL_UDP_PROFILE

        profiles = profiles_to_update("youtube")

        self.assertIn("youtube.com (интерфейс)", profiles)
        self.assertIn(CATCH_ALL_UDP_PROFILE, profiles)

    def test_every_target_also_updates_a_catch_all(self) -> None:
        from autotune.targets import (
            CATCH_ALL_TCP_PROFILE,
            CATCH_ALL_UDP_PROFILE,
            TARGETS,
        )

        for target in TARGETS:
            with self.subTest(target=target.key):
                self.assertTrue(
                    {CATCH_ALL_TCP_PROFILE, CATCH_ALL_UDP_PROFILE} & set(target.profiles),
                    "правится только свой профиль — доступ вообще не починится",
                )

    def test_unknown_target_asks_for_nothing(self) -> None:
        from autotune.plans import profiles_to_update

        self.assertEqual(profiles_to_update("мусор"), ())


class PresetMatchTests(unittest.TestCase):
    """Имена профилей обязаны совпадать с пресетом.

    Опечатка здесь не упадёт с ошибкой: стратегия просто ляжет мимо, и
    человек получит «подобрано и применено» при неработающем сайте.
    """

    def test_preset_exists(self) -> None:
        self.assertTrue(PRESET.is_file())

    def test_all_profile_names_exist_in_the_preset(self) -> None:
        from autotune.targets import TARGETS

        names = set(re.findall(r"^--name=(.+)$", PRESET.read_text(encoding="utf-8"), re.M))

        for target in TARGETS:
            for profile in target.profiles:
                with self.subTest(target=target.key, profile=profile):
                    self.assertIn(profile, names, "такого профиля в пресете нет")


class OutcomeTests(unittest.TestCase):
    def test_empty_result_says_so_plainly(self) -> None:
        """Врать «применено», когда ничего не нашлось, нельзя."""
        from autotune.plans import describe_outcome

        text = describe_outcome({})

        self.assertIn("не нашлась", text)
        self.assertIn("вручную", text)

    def test_applied_result_counts_profiles(self) -> None:
        from autotune.plans import describe_outcome

        text = describe_outcome({"youtube": ("a", "b")})

        self.assertIn("youtube", text)
        self.assertIn("2", text)


class CheckTests(unittest.TestCase):
    def test_check_uses_the_honest_probe(self) -> None:
        """TCP-коннект врёт на подменённых в hosts адресах."""
        import inspect

        from autotune import check

        source = inspect.getsource(check.check_target)

        self.assertIn("probe_domain_over_https", source)
        self.assertNotIn("probe_tcp_target_health", source)

    def test_probe_failure_is_not_an_exception(self) -> None:
        """Упавшая проверка — это «недоступно», а не падение запуска."""
        import autotune.check as check
        import oneclick.deps as deps

        original = deps.probe_domain_over_https
        try:
            def _boom(*_args, **_kwargs):
                raise OSError("сеть недоступна")

            deps.probe_domain_over_https = _boom
            from autotune.targets import TARGETS

            result = check.check_target(TARGETS[0], timeout=0.1)
        finally:
            deps.probe_domain_over_https = original

        self.assertFalse(result.available)
        self.assertIn("не выполнилась", result.detail)


if __name__ == "__main__":
    unittest.main()


class NamedProfileApplyTests(unittest.TestCase):
    """Стратегия должна лечь в профиль по ИМЕНИ.

    Готовое применение из «Подбора стратегии» ищет профиль по цели: по
    фильтрам или по хостлисту с нужным доменом. Общий профиль по адресам
    так не найдётся — в нём нет хостлиста с youtube.com. А чинит доступ
    вообще именно он.
    """

    def _feature(self):
        from types import SimpleNamespace

        saved = {}
        text = PRESET.read_text(encoding="utf-8")
        feature = SimpleNamespace(
            get_selected_source_preset_manifest=lambda mode: SimpleNamespace(
                file_name="Стандартный 1.txt"
            ),
            read_preset_source_by_file_name=lambda mode, name: text,
            save_preset_source_by_file_name=lambda mode, name, body: saved.__setitem__(name, body),
        )
        return feature, saved

    def test_named_profiles_receive_the_strategy(self) -> None:
        from autotune.apply import apply_strategy_to_named_profiles

        feature, saved = self._feature()

        updated = apply_strategy_to_named_profiles(
            presets_feature=feature,
            strategy_lines=["--lua-desync=fake:blob=tls7"],
            profile_names=["youtube.com (интерфейс)", "Все сайты UDP (айпи)"],
        )

        self.assertEqual(len(updated), 2)
        body = saved["Стандартный 1.txt"]
        for name in updated:
            block = next(b for b in body.split("--new") if f"--name={name}\n" in b)
            with self.subTest(profile=name):
                self.assertIn("blob=tls7", block, "стратегия не попала в профиль")

    def test_unknown_profile_is_skipped_not_invented(self) -> None:
        from autotune.apply import apply_strategy_to_named_profiles

        feature, saved = self._feature()

        updated = apply_strategy_to_named_profiles(
            presets_feature=feature,
            strategy_lines=["--lua-desync=fake:blob=tls7"],
            profile_names=["Такого профиля нет"],
        )

        self.assertEqual(updated, ())
        self.assertEqual(saved, {}, "пресет переписан впустую")

    def test_nothing_to_apply_does_not_touch_the_preset(self) -> None:
        from autotune.apply import apply_strategy_to_named_profiles

        feature, saved = self._feature()

        self.assertEqual(
            apply_strategy_to_named_profiles(
                presets_feature=feature, strategy_lines=[], profile_names=["Все сайты UDP (айпи)"]
            ),
            (),
        )
        self.assertEqual(saved, {})


class ScanAdapterTests(unittest.TestCase):
    """Перебор берёт синхронный сканер, а не Qt-обёртку.

    Автоподбор идёт в обычном потоке, без цикла событий: сигналы Qt там
    доставлять некому.
    """

    def _report(self, *strategies):
        from types import SimpleNamespace

        return SimpleNamespace(
            working_strategies=[
                SimpleNamespace(strategy_args=args, strategy_name=name, time_ms=ms)
                for name, args, ms in strategies
            ]
        )

    def _run(self, report):
        import blockcheck.strategy_scanner as scanner_module
        from autotune.scan import run_strategy_scan

        original = scanner_module.StrategyScanner
        try:
            class _Fake:
                def __init__(self, **kwargs):
                    self.kwargs = kwargs

                def run(self):
                    return report

            scanner_module.StrategyScanner = _Fake
            return run_strategy_scan("youtube.com", "tcp_https", shutdown_sync=lambda **k: None)
        finally:
            scanner_module.StrategyScanner = original

    def test_fastest_working_strategy_wins(self) -> None:
        """Порядок в отчёте — порядок проверки, а не качество."""
        lines = self._run(
            self._report(
                ("медленная", "--lua-desync=slow", 900.0),
                ("быстрая", "--lua-desync=fast", 120.0),
            )
        )

        self.assertEqual(lines, ["--lua-desync=fast"])

    def test_nothing_working_gives_empty(self) -> None:
        self.assertEqual(self._run(self._report()), [])

    def test_scanner_failure_is_not_fatal(self) -> None:
        """Упавший перебор не должен ронять запуск приложения."""
        import blockcheck.strategy_scanner as scanner_module
        from autotune.scan import run_strategy_scan

        original = scanner_module.StrategyScanner
        try:
            def _boom(**kwargs):
                raise RuntimeError("движок занят")

            scanner_module.StrategyScanner = _boom
            lines = run_strategy_scan("youtube.com", "tcp_https", shutdown_sync=lambda **k: None)
        finally:
            scanner_module.StrategyScanner = original

        self.assertEqual(lines, [])


class RuntimeChainTests(unittest.TestCase):
    def _feature(self):
        from types import SimpleNamespace

        store = {"text": PRESET.read_text(encoding="utf-8")}
        return SimpleNamespace(
            get_selected_source_preset_manifest=lambda mode: SimpleNamespace(file_name="p.txt"),
            read_preset_source_by_file_name=lambda mode, name: store["text"],
            save_preset_source_by_file_name=lambda mode, name, body: store.__setitem__("text", body),
        )

    def test_broken_target_is_scanned_and_applied(self) -> None:
        import autotune.check as check_module
        import autotune.runtime as runtime_module
        from autotune.plans import CheckResult
        from autotune.targets import CATCH_ALL_UDP_PROFILE

        saved_check, saved_engine = check_module.check_all, runtime_module.is_engine_running
        try:
            check_module.check_all = lambda **kwargs: [
                CheckResult("youtube", False),
                CheckResult("discord", True),
            ]
            runtime_module.is_engine_running = lambda: True

            applied = runtime_module.run_autotune(
                presets_feature=self._feature(),
                scan_runner=lambda target, protocol: ["--lua-desync=fake:blob=tls7"],
            )
        finally:
            check_module.check_all = saved_check
            runtime_module.is_engine_running = saved_engine

        self.assertIn("youtube", applied)
        self.assertIn(CATCH_ALL_UDP_PROFILE, applied["youtube"])
        self.assertNotIn("discord", applied, "трогали работающую цель")

    def test_nothing_happens_while_the_engine_is_down(self) -> None:
        import autotune.check as check_module
        import autotune.runtime as runtime_module
        from autotune.plans import CheckResult

        saved_check, saved_engine = check_module.check_all, runtime_module.is_engine_running
        calls = []
        try:
            check_module.check_all = lambda **kwargs: [CheckResult("youtube", False)]
            runtime_module.is_engine_running = lambda: False

            applied = runtime_module.run_autotune(
                presets_feature=self._feature(),
                scan_runner=lambda target, protocol: calls.append(target) or [],
            )
        finally:
            check_module.check_all = saved_check
            runtime_module.is_engine_running = saved_engine

        self.assertEqual(applied, {})
        self.assertEqual(calls, [], "перебор запустился при остановленном движке")
