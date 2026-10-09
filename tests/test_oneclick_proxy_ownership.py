"""«Одна кнопка» снимает прокси Telegram только там, где сама его поднимает.

Человек включал прокси на его собственной странице — работало. Нажимал
«Включить обход» — прокси пропадал и больше не поднимался ничем, кроме
повторного ручного включения.

Причин было две, и обе про несимметричность.

Первая — план. Включение добавляло шаг с прокси только при настройке
«Прокси Telegram вместе с обходом», а выключение снимало прокси всегда.
Одно нажатие «выключить» убирало то, чего «одна кнопка» не ставила.

Вторая, главная — сам шаг остановки писал в настройки `set_enabled(False)`,
то есть переключал за человека тумблер на странице прокси. После этого
поднять прокси было нечем: start_proxy_if_enabled_async уходит ни с чем
при выключенной настройке, а сама она больше не включается — обратный
`set_enabled(True)` со старта убрали раньше и намеренно.

И третья, из-за которой «Включить обход» падал целиком: запуск шага
спрашивал тумблер на странице прокси, хотя сам шаг заводит сюда другая
настройка — «Прокси Telegram вместе с обходом». Включена одна, выключен
другой — и запуск молча не делал ничего.

Здесь проверяется ровно это: план симметричен настройке, запуск не
спрашивает чужой тумблер, остановка не пишет его, а не поднявшийся
прокси не уносит с собой весь обход.
"""


from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

DEPS = PROJECT_SRC / "oneclick" / "deps.py"
# Включение и выключение делает поток кнопки, вынесенный из ui/button.py.
BUTTON = PROJECT_SRC / "oneclick" / "ui" / "oneclick_worker.py"


def _function(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"в {path.name} нет функции {name}")


def _function_source(path: Path, name: str) -> str:
    return ast.unparse(_function(path, name))


def _function_code(path: Path, name: str) -> str:
    """Тело функции без описания.

    Описание тут читать нельзя: оно как раз и рассказывает, почему
    `set_enabled` отсюда убран, — и поиск по слову находил бы сам
    рассказ о запрете.
    """
    node = _function(path, name)
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    return "\n".join(ast.unparse(statement) for statement in body)


class DisablePlanTests(unittest.TestCase):
    def test_proxy_is_stopped_when_the_button_owns_it(self) -> None:
        from oneclick.plans import build_disable_plan
        from oneclick.state import StepKey

        plan = build_disable_plan(owns_telegram_proxy=True)

        self.assertIn(StepKey.TELEGRAM_PROXY, plan)
        self.assertIn(StepKey.DPI, plan)

    def test_foreign_proxy_is_left_running(self) -> None:
        """Прокси, включённый на своей странице, — не наше дело."""
        from oneclick.plans import build_disable_plan
        from oneclick.state import StepKey

        plan = build_disable_plan(owns_telegram_proxy=False)

        self.assertNotIn(StepKey.TELEGRAM_PROXY, plan)
        self.assertIn(StepKey.DPI, plan)

    def test_disable_still_leaves_hosts_and_dns_alone(self) -> None:
        """Старое правило не должно потеряться в новой развилке."""
        from oneclick.plans import build_disable_plan
        from oneclick.state import StepKey

        for owns in (True, False):
            with self.subTest(owns=owns):
                plan = build_disable_plan(owns_telegram_proxy=owns)
                self.assertNotIn(StepKey.HOSTS, plan)
                self.assertNotIn(StepKey.DNS, plan)

    def test_plan_matches_the_enable_side(self) -> None:
        """Та же настройка решает и включение, и выключение.

        Разойдись эти две развилки — и вернётся ровно тот баг, ради
        которого файл написан.
        """
        from oneclick.plans import OneClickRequest, build_disable_plan, build_enable_plan
        from oneclick.state import StepKey

        for owns in (True, False):
            with self.subTest(owns=owns):
                request = OneClickRequest(needs_telegram_proxy=owns)
                in_enable = StepKey.TELEGRAM_PROXY in [
                    step.key for step in build_enable_plan(request)
                ]
                in_disable = StepKey.TELEGRAM_PROXY in build_disable_plan(
                    owns_telegram_proxy=owns
                )
                self.assertEqual(in_enable, in_disable)


class _Recorder:
    """Заглушки зависимостей: запоминают, что позвали."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def build(self):
        from oneclick.runner import OneClickDeps

        def record(name, result=(True, "")):
            def _call(*_args, **_kwargs):
                self.calls.append(name)
                return result

            return _call

        return OneClickDeps(
            check_conflicts=record("check_conflicts"),
            start_dpi=record("start_dpi"),
            stop_dpi=record("stop_dpi"),
            check_telegram_ready=record("check_telegram_ready"),
            start_telegram_proxy=record("start_telegram_proxy"),
            stop_telegram_proxy=record("stop_telegram_proxy"),
            backup_hosts=record("backup_hosts"),
            apply_hosts=record("apply_hosts"),
            restore_hosts=record("restore_hosts"),
            check_dns_integrity=record("check_dns_integrity", []),
            apply_dns=record("apply_dns"),
            restore_dns=record("restore_dns"),
            probe_domains=record("probe_domains", (0, ())),
        )


class DisableRunnerTests(unittest.TestCase):
    def test_runner_leaves_a_foreign_proxy_alone(self) -> None:
        from oneclick.runner import OneClickRunner

        recorder = _Recorder()
        OneClickRunner(recorder.build()).disable(owns_telegram_proxy=False)

        self.assertIn("stop_dpi", recorder.calls)
        self.assertNotIn("stop_telegram_proxy", recorder.calls)

    def test_runner_stops_its_own_proxy(self) -> None:
        from oneclick.runner import OneClickRunner

        recorder = _Recorder()
        OneClickRunner(recorder.build()).disable(owns_telegram_proxy=True)

        self.assertIn("stop_telegram_proxy", recorder.calls)


class StopStepTests(unittest.TestCase):
    def test_stop_does_not_write_the_setting(self) -> None:
        """Тот самый `set_enabled(False)`, из-за которого прокси не возвращался."""
        code = _function_code(DEPS, "_stop_telegram_proxy")

        self.assertNotIn("set_enabled", code)

    def test_stop_still_stops_the_process(self) -> None:
        """Не трогать настройку — не значит не останавливать."""
        source = _function_source(DEPS, "_stop_telegram_proxy")

        self.assertIn("stop_proxy", source)

    def test_start_does_not_write_the_setting_either(self) -> None:
        """Симметрия, из-за нарушения которой всё и сломалось."""
        code = _function_code(DEPS, "_start_telegram_proxy")

        self.assertNotIn("set_enabled", code)


class StartStepTests(unittest.TestCase):
    def test_start_does_not_consult_the_page_toggle(self) -> None:
        """Шаг завела сюда одна настройка, а запуск спрашивал другую."""
        code = _function_code(DEPS, "_start_telegram_proxy")

        self.assertIn("start_proxy_with_settings", code)
        self.assertNotIn("start_proxy_if_enabled_async", code)

    def test_direct_start_ignores_the_enabled_flag(self) -> None:
        """Прямой запуск не читает `telegram_proxy.enabled` и не пишет его."""
        commands = PROJECT_SRC / "telegram_proxy" / "runtime" / "commands.py"
        code = _function_code(commands, "start_proxy_with_settings")

        self.assertIn("start_proxy", code)
        self.assertNotIn("get_tg_proxy_enabled", code)
        self.assertNotIn("set_enabled", code)

    def test_direct_start_is_exported(self) -> None:
        """Иначе шаг тянул бы её мимо публичного слоя."""
        from telegram_proxy import public

        self.assertIn("start_proxy_with_settings", public.__all__)


class FailedProxyIsNotFatalTests(unittest.TestCase):
    def test_bypass_survives_a_proxy_that_did_not_come_up(self) -> None:
        """Обход работает и без прокси — ронять его из-за мессенджера нельзя."""
        from oneclick.plans import OneClickRequest
        from oneclick.runner import OneClickRunner
        from oneclick.state import OneClickState

        recorder = _Recorder()
        deps = recorder.build()
        deps.start_telegram_proxy = lambda: (False, "Прокси для Telegram не поднялся")

        outcome = OneClickRunner(deps).enable(
            OneClickRequest(needs_telegram_proxy=True, run_selfcheck=False)
        )

        self.assertIs(outcome.state, OneClickState.RUNNING)
        self.assertNotIn("stop_dpi", recorder.calls)

    def test_the_reason_reaches_the_person(self) -> None:
        """Тихо пропустить шаг, ради которого нажимали, — хуже, чем упасть."""
        from oneclick.plans import OneClickRequest
        from oneclick.runner import OneClickRunner

        deps = _Recorder().build()
        deps.start_telegram_proxy = lambda: (False, "Прокси для Telegram не поднялся")

        outcome = OneClickRunner(deps).enable(
            OneClickRequest(needs_telegram_proxy=True, run_selfcheck=False)
        )

        self.assertIn("Прокси для Telegram не поднялся", outcome.message)


class ButtonWiringTests(unittest.TestCase):
    def test_button_passes_ownership_to_disable(self) -> None:
        """Без этого развилка в плане осталась бы мёртвой."""
        source = _function_source(BUTTON, "run")

        self.assertIn("owns_telegram_proxy=request.needs_telegram_proxy", source)


if __name__ == "__main__":
    unittest.main()
