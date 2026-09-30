"""Обучающий тур в net67: простой вид, мастер первого запуска, одна кнопка.

Тур пришёл из исходного проекта и в net67 даже не импортировался:
шаги ссылались на страницы режима Zapret 1 и Оркестратора, которых здесь
нет. Главное в net67 — «одна кнопка» и простой вид без боковой панели, и
тур о них не знал. Эти тесты держат то, чем тур net67 отличается.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402

from app.page_names import PageName  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class TourStepsTests(unittest.TestCase):
    def test_steps_import_and_speak_about_net67_first(self) -> None:
        from ui.onboarding.steps import TOUR_STEPS

        keys = [step.key for step in TOUR_STEPS]
        # Сначала то, что видит каждый: одна кнопка и переключатель вида.
        self.assertEqual(
            keys[:7],
            ["welcome", "how_it_works", "oneclick", "services", "program_settings", "bell", "view_switch"],
        )
        self.assertEqual(keys[-1], "finish")
        for gone in ("dpi_mode", "tools", "geo_blocks"):
            self.assertNotIn(gone, keys)

    def test_simple_view_keeps_only_the_main_page(self) -> None:
        from ui.onboarding import steps

        _app()
        window = QWidget()
        with (
            patch.object(steps, "_advanced_view_enabled", return_value=False),
            patch.object(steps, "get_window_ui_session", return_value=SimpleNamespace(nav_items={})),
        ):
            ctx = steps.build_tour_context(window)

        # Боковой панели в простом виде нет, но главная страница есть.
        self.assertEqual(ctx.control_page_name, PageName.ZAPRET2_MODE_CONTROL)
        self.assertEqual(ctx.pages, {"control": PageName.ZAPRET2_MODE_CONTROL})
        self.assertFalse(ctx.advanced)
        window.deleteLater()

    def test_advanced_view_opens_preset_and_profile_pages(self) -> None:
        from ui.onboarding import steps

        _app()
        window = QWidget()
        with (
            patch.object(steps, "_advanced_view_enabled", return_value=True),
            patch.object(steps, "get_window_ui_session", return_value=SimpleNamespace(nav_items={})),
        ):
            ctx = steps.build_tour_context(window)

        self.assertTrue(ctx.advanced)
        self.assertIn("user_presets", ctx.pages)
        self.assertIn("profile_setup", ctx.pages)
        window.deleteLater()

    def test_advanced_only_steps_are_skipped_in_simple_view(self) -> None:
        from ui.onboarding.overlay import OnboardingOverlay
        from ui.onboarding.steps import TOUR_STEPS, TourContext

        _app()
        window = QWidget()
        simple = SimpleNamespace(
            _ctx=TourContext(
                window=window,
                control_page_name=PageName.ZAPRET2_MODE_CONTROL,
                pages={"control": PageName.ZAPRET2_MODE_CONTROL},
                advanced=False,
            )
        )
        by_key = {step.key: step for step in TOUR_STEPS}

        self.assertFalse(OnboardingOverlay._is_step_available(simple, by_key["building_blocks"]))
        self.assertFalse(OnboardingOverlay._is_step_available(simple, by_key["preset"]))
        # Страницы пресетов в простом виде нет — шаг недоступен без всяких флагов.
        self.assertFalse(OnboardingOverlay._is_step_available(simple, by_key["presets_list"]))
        self.assertTrue(OnboardingOverlay._is_step_available(simple, by_key["oneclick"]))
        self.assertTrue(OnboardingOverlay._is_step_available(simple, by_key["welcome"]))
        window.deleteLater()

    def test_view_switch_points_at_title_bar_button(self) -> None:
        from ui.onboarding.steps import TOUR_STEPS, TourContext

        _app()
        window = QWidget()
        window.advancedButton = QPushButton("Расширенные настройки", window)
        window.resize(400, 300)
        window.show()
        ctx = TourContext(window=window)
        step = next(step for step in TOUR_STEPS if step.key == "view_switch")

        self.assertEqual(step.target(ctx), [window.advancedButton])
        window.advancedButton.hide()
        self.assertEqual(step.target(ctx), [])
        window.close()
        window.deleteLater()


class ControlPageTargetTests(unittest.TestCase):
    def test_oneclick_target_is_the_main_button(self) -> None:
        from presets.ui.control.control_page_shared import ControlPageActionMixin

        button = object()
        page = SimpleNamespace(oneclick_button=button)

        self.assertIs(ControlPageActionMixin.onboarding_target(page, "oneclick"), button)


class EnableAdvancedActionTests(unittest.TestCase):
    def _overlay(self, *, advanced: bool, button_shown: bool):
        from ui.onboarding.overlay import OnboardingOverlay
        from ui.onboarding.steps import TourContext

        _app()
        window = QWidget()
        window.advancedButton = QPushButton("Расширенные настройки", window)
        window.resize(400, 300)
        window.show()
        if not button_shown:
            window.advancedButton.hide()
        fake = SimpleNamespace(
            _ctx=TourContext(window=window, advanced=advanced),
            _window=window,
        )
        self.addCleanup(window.deleteLater)
        return OnboardingOverlay, fake

    def test_view_switch_offers_enabling_advanced_only_in_simple_view(self) -> None:
        from ui.onboarding.steps import TOUR_STEPS

        step = next(step for step in TOUR_STEPS if step.key == "view_switch")
        self.assertEqual(step.action, "enable_advanced")

        overlay_cls, simple = self._overlay(advanced=False, button_shown=True)
        self.assertTrue(overlay_cls._step_action_available(simple, step))
        _cls, advanced = self._overlay(advanced=True, button_shown=True)
        self.assertFalse(overlay_cls._step_action_available(advanced, step))
        _cls, hidden = self._overlay(advanced=False, button_shown=False)
        self.assertFalse(overlay_cls._step_action_available(hidden, step))

    def test_simple_view_has_its_own_text_and_button_label(self) -> None:
        from app.ui_texts import tr

        body = tr("onboarding.step.view_switch.body_simple", language="ru", default="")
        self.assertIn("Включить расширенные настройки", body)
        self.assertEqual(tr("onboarding.action.enable_advanced", language="ru", default=""), "Включить расширенные настройки")


class FirstRunSetupTourTests(unittest.TestCase):
    """Первый запуск: тур сам задаёт вопросы мастера и записывает ответы."""

    def _install(self, *, wizard_pending: bool, tour_done: bool):
        from main import post_startup_onboarding

        _app()
        startup_host = SimpleNamespace(
            startup_post_init_ready=object(),
            startup_state=SimpleNamespace(post_init_ready=True),
            is_alive=Mock(return_value=True),
            start_onboarding_tour=Mock(return_value=True),
        )
        mark = Mock()
        with (
            patch.object(post_startup_onboarding, "bind_startup_gate", side_effect=lambda _s, cb, **_k: cb()),
            patch.object(post_startup_onboarding, "schedule_after", side_effect=lambda _d, cb: cb()),
            patch.object(post_startup_onboarding, "enqueue_subsystem_task", side_effect=lambda _q, _n, target: target()),
            patch.object(post_startup_onboarding, "_read_tour_done", return_value=tour_done),
            patch.object(post_startup_onboarding, "_mark_tour_done", mark),
            patch.object(post_startup_onboarding, "_first_run_wizard_pending", return_value=wizard_pending),
            patch.object(post_startup_onboarding, "log"),
        ):
            post_startup_onboarding.install_onboarding_tour(startup_host)
        return startup_host, mark

    def test_first_run_starts_setup_tour_even_after_an_old_tour(self) -> None:
        """Тур показывали прежней версией, а настройка не пройдена — спрашиваем."""
        host, mark = self._install(wizard_pending=True, tour_done=True)
        host.start_onboarding_tour.assert_called_once_with(setup=True)
        # Флаг поставит сам тур, когда запишет ответы.
        mark.assert_not_called()

    def test_ordinary_first_tour_has_no_questions(self) -> None:
        host, mark = self._install(wizard_pending=False, tour_done=False)
        host.start_onboarding_tour.assert_called_once_with(setup=False)
        mark.assert_called_once_with()

    def test_nothing_starts_when_everything_is_done(self) -> None:
        host, _mark = self._install(wizard_pending=False, tour_done=True)
        host.start_onboarding_tour.assert_not_called()

    def _overlay(self, *, setup: bool):
        from ui.onboarding.overlay import OnboardingOverlay
        from ui.onboarding.steps import TourContext, TourStep

        _app()
        window = QWidget()
        window.resize(900, 700)
        self.addCleanup(window.deleteLater)
        ctx = TourContext(window=window, advanced=True, setup=setup)
        steps = (TourStep("welcome", hero=True), TourStep("finish", hero=True))
        return OnboardingOverlay(window, ctx, steps)

    def test_done_and_skip_write_answers_hidden_does_not(self) -> None:
        from ui.onboarding import overlay as overlay_module

        for reason, expected in (("done", 1), ("skipped", 1), ("hidden", 0)):
            overlay = self._overlay(setup=True)
            with patch.object(overlay_module, "apply_setup_answers") as apply:
                overlay.finish(reason, immediate=True)
            self.assertEqual(apply.call_count, expected, reason)

    def test_ordinary_tour_writes_nothing(self) -> None:
        from ui.onboarding import overlay as overlay_module

        overlay = self._overlay(setup=False)
        with patch.object(overlay_module, "apply_setup_answers") as apply:
            overlay.finish("done", immediate=True)
        apply.assert_not_called()

    def test_choices_show_only_on_first_run(self) -> None:
        from ui.onboarding.steps import TourStep

        overlay = self._overlay(setup=True)
        overlay._show_choice(TourStep("menu_presets", choice="provider"))
        self.assertIsNotNone(overlay._choice_widget)
        overlay._show_choice(TourStep("oneclick"))
        self.assertIsNone(overlay._choice_widget)

        plain = self._overlay(setup=False)
        plain._show_choice(TourStep("menu_presets", choice="provider"))
        self.assertIsNone(plain._choice_widget)

    def test_provider_is_written_when_leaving_its_step(self) -> None:
        """Пресеты — следующие шаги, и там должен стоять уже выбранный."""
        from ui.onboarding import overlay as overlay_module
        from ui.onboarding.steps import TourStep

        overlay = self._overlay(setup=True)
        overlay._steps = [TourStep("menu_presets", choice="provider"), TourStep("finish")]
        overlay._index = 0
        with (
            patch.object(overlay_module, "apply_provider_answer") as apply,
            patch.object(overlay, "_enter_step"),
        ):
            overlay.go_next()
        apply.assert_called_once()

    def test_card_grows_when_detect_results_arrive(self) -> None:
        """Итог проверки не втискивается в карточку прежнего размера.

        Высоту мерили сразу после смены текста, а раскладка пересчитывает
        её цепочкой отложенных событий. Карточка оставалась маленькой, итог
        налезал сам на себя — до «Назад»/«Далее», которые собирали её заново.
        """
        import time

        from ui.onboarding import setup_choices
        from ui.onboarding.overlay import OnboardingOverlay
        from ui.onboarding.steps import TourContext, TourStep

        results = [(f"site{index}.example", False, "DNS таймаут — DNS-сервер не ответил") for index in range(3)]

        def fake_run(worker) -> None:
            time.sleep(0.2)
            worker.finished_with.emit(list(results))

        app = _app()
        window = QWidget()
        window.resize(1400, 1000)
        window.show()
        self.addCleanup(window.deleteLater)
        ctx = TourContext(window=window, advanced=True, setup=True)
        steps = (TourStep("welcome", hero=True), TourStep("blockcheck", choice="detect"))

        def pump(seconds: float) -> None:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                app.processEvents()
                time.sleep(0.01)

        with patch.object(setup_choices._DetectWorker, "run", fake_run):
            overlay = OnboardingOverlay(window, ctx, steps)
            overlay.start()
            overlay.go_next()
            pump(1.5)
            card = overlay._card
            needed = card.content_height_for_width(card.width())
            self.assertIn("3 из 3", overlay._choice_widget.status.text())
            self.assertGreaterEqual(card.height() + 2, needed)
            overlay.finish("hidden", immediate=True)


class MenuStepsTests(unittest.TestCase):
    """Меню — вкладки. Шаги, целившиеся в скрытую панель, пропускались молча."""

    def test_every_menu_page_has_its_own_step(self) -> None:
        from ui.onboarding.steps import TOUR_STEPS

        from configsets import CONFIGS_READY

        keys = {step.key for step in TOUR_STEPS}
        for key in (
            "menu_root", "menu_presets", "menu_tools", "menu_diagnostics",
            "dns", "hosts", "telegram_proxy", "vpn",
            "blockcheck", "log_analyzer", "logs",
        ):
            self.assertIn(key, keys)
        # Раздел «в разработке» тур не описывает как рабочий.
        self.assertEqual("configs" in keys, CONFIGS_READY)

    def test_group_and_page_tabs_are_targets(self) -> None:
        from shell.tabs import GroupTabBar, PageTabBar
        from ui.navigation.schema import get_page_route_key
        from ui.onboarding.steps import TOUR_STEPS, TourContext

        _app()
        window = QWidget()
        window.groupTabs = GroupTabBar(window)
        window.groupTabs.set_groups(["root", "system"])
        window.pageTabs = PageTabBar(window)
        window.pageTabs.move(0, 40)
        window.pageTabs.set_pages([
            (get_page_route_key(PageName.HOSTS), "Редактор hosts"),
            (get_page_route_key(PageName.NETWORK), "Настройка DNS"),
        ])
        window.resize(900, 300)
        window.show()
        self.addCleanup(window.deleteLater)
        ctx = TourContext(window=window)
        by_key = {step.key: step for step in TOUR_STEPS}

        self.assertEqual(by_key["menu_tools"].target(ctx), [window.groupTabs.tabs["system"]])
        self.assertEqual(
            by_key["hosts"].target(ctx),
            [window.pageTabs.tabs[get_page_route_key(PageName.HOSTS)]],
        )
        # Раздела нет на экране — шаг пропустится, а не подсветит пустоту.
        self.assertEqual(by_key["menu_diagnostics"].target(ctx), [])

    def test_preset_details_are_an_optional_branch(self) -> None:
        from ui.onboarding.overlay import OnboardingOverlay
        from ui.onboarding.steps import TOUR_STEPS, TourContext

        _app()
        window = QWidget()
        self.addCleanup(window.deleteLater)
        ctx = TourContext(window=window, advanced=True, pages={"profile_setup": PageName.ZAPRET2_PROFILE_SETUP})
        fake = SimpleNamespace(_ctx=ctx)
        technique = next(step for step in TOUR_STEPS if step.key == "technique_fake")

        self.assertFalse(OnboardingOverlay._is_step_available(fake, technique))
        ctx.branches.add("presets")
        self.assertTrue(OnboardingOverlay._is_step_available(fake, technique))
        presets_list = next(step for step in TOUR_STEPS if step.key == "presets_list")
        self.assertEqual(presets_list.action, "branch:presets")


class BypassTourTests(unittest.TestCase):
    """Экскурсия «Как работает обход»: схемы техник подряд, без страниц."""

    def test_every_technique_is_shown_with_its_diagram(self) -> None:
        from ui.onboarding.steps import BYPASS_TOUR_STEPS

        techniques = [step for step in BYPASS_TOUR_STEPS if step.key.startswith("technique_")]
        self.assertEqual(len(techniques), 8)
        for step in techniques:
            self.assertEqual(step.illustration, step.key.removeprefix("technique_"))
            # Без страниц: экскурсия идёт и в простом виде.
            self.assertIsNone(step.page)
            self.assertFalse(step.branch)

    def test_available_in_simple_view(self) -> None:
        from ui.onboarding.overlay import OnboardingOverlay
        from ui.onboarding.steps import BYPASS_TOUR_STEPS, TourContext

        _app()
        window = QWidget()
        self.addCleanup(window.deleteLater)
        simple = SimpleNamespace(_ctx=TourContext(window=window, advanced=False, pages={"control": PageName.ZAPRET2_MODE_CONTROL}))
        for step in BYPASS_TOUR_STEPS:
            self.assertTrue(OnboardingOverlay._is_step_available(simple, step), step.key)

    def test_every_step_has_texts_in_both_languages(self) -> None:
        from app.ui_texts import TEXTS
        from ui.onboarding.steps import BYPASS_TOUR_STEPS

        missing = [
            f"{step.key}.{part}[{language}]"
            for step in BYPASS_TOUR_STEPS
            for part in ("title", "body")
            for language in ("ru", "en")
            if not str((TEXTS.get(f"onboarding.step.{step.key}.{part}") or {}).get(language) or "").strip()
        ]
        self.assertEqual(missing, [])

    def test_kind_selects_the_bypass_steps_and_never_asks_questions(self) -> None:
        from ui import onboarding
        from ui.onboarding import overlay as overlay_module
        from ui.onboarding.steps import BYPASS_TOUR_STEPS

        _app()
        window = QWidget()
        window.resize(900, 700)
        window.show()
        self.addCleanup(window.deleteLater)
        created = []

        class FakeOverlay:
            def __init__(self, _window, context, steps, **_kwargs):
                created.append((context, steps))

            def start(self):
                return True

        with (
            patch.object(overlay_module, "OnboardingOverlay", FakeOverlay),
            patch("ui.window_adapter.get_current_page", return_value=None),
        ):
            self.assertTrue(onboarding.start_onboarding_tour(window, kind="bypass", setup=True))

        context, steps = created[0]
        self.assertIs(steps, BYPASS_TOUR_STEPS)
        self.assertFalse(context.setup)

    def test_main_tour_ends_with_a_door_into_the_bypass_tour(self) -> None:
        from ui.onboarding import overlay as overlay_module
        from ui.onboarding.steps import TOUR_STEPS, TourContext, TourStep

        finish = next(step for step in TOUR_STEPS if step.key == "finish")
        self.assertEqual(finish.action, "bypass_tour")

        _app()
        window = QWidget()
        window.resize(900, 700)
        self.addCleanup(window.deleteLater)
        overlay = overlay_module.OnboardingOverlay(window, TourContext(window=window), (TourStep("finish", action="bypass_tour"),))
        overlay._steps = [TourStep("finish", action="bypass_tour")]
        overlay._index = 0
        calls = []
        with (
            patch.object(overlay_module.QTimer, "singleShot", side_effect=lambda _ms, cb: cb()),
            patch("ui.onboarding.start_onboarding_tour", side_effect=lambda w, **kw: calls.append(kw) or True),
        ):
            overlay._run_step_action()
        self.assertEqual(calls, [{"kind": "bypass"}])
        self.assertTrue(overlay.is_finishing())

    def test_no_bypass_tour_door_after_the_detailed_preset_branch(self) -> None:
        """Подробная ветка уже показала все техники — звать туда же незачем.

        Владелец прошёл «Разобрать пресет подробно» и на последней карточке
        увидел кнопку «Как работает обход» — экскурсию из тех же схем.
        """
        from ui.onboarding import overlay as overlay_module
        from ui.onboarding.steps import PRESETS_BRANCH, TourContext, TourStep

        _app()
        window = QWidget()
        window.resize(900, 700)
        self.addCleanup(window.deleteLater)
        step = TourStep("finish", action="bypass_tour")

        for opened, expect_button in (((), True), ((PRESETS_BRANCH,), False)):
            with self.subTest(branches=opened):
                context = TourContext(window=window)
                context.branches.update(opened)
                overlay = overlay_module.OnboardingOverlay(window, context, (step,))
                self.addCleanup(overlay.deleteLater)
                overlay._steps = [step]
                overlay._index = 0
                self.assertEqual(overlay._step_action_available(step), expect_button)
                overlay._apply_step_texts(step, has_target=False)
                body = overlay._card.body_label.text()
                self.assertEqual("Как работает обход" in body, expect_button, body)

    def test_control_page_button_asks_for_the_bypass_tour(self) -> None:
        from presets.ui.control.control_page_shared import ControlPageActionMixin

        calls = []
        page = SimpleNamespace(_start_onboarding_tour_callback=lambda **kw: calls.append(kw))
        ControlPageActionMixin._start_bypass_tour(page)
        self.assertEqual(calls, [{"kind": "bypass"}])


class DetectSummaryTests(unittest.TestCase):
    def test_dns_timeout_is_not_counted_as_blocked(self) -> None:
        """«Закрыто 3 из 4» при медленном DNS — неправда: до блокировок не дошло."""
        from ui.onboarding.setup_choices import describe_detect_results

        timeout = "DNS таймаут — DNS-сервер не ответил"
        title, body = describe_detect_results([
            ("rutracker.org", False, timeout, "dns_timeout"),
            ("www.youtube.com", False, "сброс TLS", ""),
            ("discord.com", True, "", ""),
        ])
        self.assertEqual(title, "Закрыто 1 из 2")
        self.assertIn("Не проверены: rutracker.org", body)
        self.assertNotIn("rutracker.org — DNS таймаут", body)

        title, _body = describe_detect_results([("rutracker.org", False, timeout, "dns_timeout")])
        self.assertEqual(title, "DNS не успел ответить")


if __name__ == "__main__":
    unittest.main()
