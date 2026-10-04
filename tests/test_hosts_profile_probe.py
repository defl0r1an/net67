"""Кнопка проверки DNS-профилей на плитке hosts.

У сервиса до семи профилей, и какой из них рабочий у этого человека, по
каталогу не понять: люди перебирали значки вслепую. Владелец попросил
кнопку, которая сама проверит каждый профиль — открывается ли сайт через
его адреса — и предложит лучший.

Три слоя: выбор лучшего (без сети, сеть подменена), сама кнопка на
плитке и связка со страницей.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_SRC = TESTS_DIR.parent / "src"
for folder in (PROJECT_SRC, TESTS_DIR):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

from hosts.profile_probe import (  # noqa: E402
    VERDICT_DEAD,
    VERDICT_OK,
    VERDICT_REGION,
    ProfileProbe,
    ServiceProbe,
    pick_probe_domains,
    pick_sample_domains,
    probe_service,
    rank_profiles,
)
from hosts.ui.services_tiles import HostsChoice, HostsTile, HostsTilesGrid  # noqa: E402


class SampleDomainsTests(unittest.TestCase):
    def test_main_domains_come_first(self) -> None:
        domains = ["accounts.x.ai", "x.ai", "api.x.ai", "grok.com", "a.b.x.ai"]
        self.assertEqual(pick_sample_domains(domains, 3), ["x.ai", "grok.com", "api.x.ai"])

    def test_duplicates_and_case_do_not_take_places(self) -> None:
        self.assertEqual(pick_sample_domains(["X.ai", "x.ai", "", "grok.com"], 6), ["x.ai", "grok.com"])



class ProbeDomainsTests(unittest.TestCase):
    """В hosts пишутся все домены, а проверялись шесть самых коротких."""

    def test_small_service_is_checked_whole(self) -> None:
        from hosts.profile_probe import FULL_CHECK_MAX_DOMAINS

        domains = [f"d{i}.claude.ai" for i in range(FULL_CHECK_MAX_DOMAINS - 1)] + ["claude.ai"]
        self.assertEqual(sorted(pick_probe_domains(domains)), sorted(domains))

    def test_large_service_takes_login_and_api_after_main(self) -> None:
        from hosts.profile_probe import LARGE_SAMPLE_DOMAINS, SAMPLE_DOMAINS

        noise = [f"cdn{i}.oaistatic.com" for i in range(60)]
        key = ["auth.openai.com", "api.openai.com", "chat.openai.com"]
        main = ["openai.com", "chatgpt.com", "sora.com", "x.ai", "a.co", "b.co"]
        picked = pick_probe_domains(noise + key + main)

        self.assertEqual(len(picked), LARGE_SAMPLE_DOMAINS)
        self.assertEqual(set(picked[:SAMPLE_DOMAINS]), set(main))
        for domain in key:
            self.assertIn(domain, picked)

    def test_result_says_how_much_was_checked(self) -> None:
        rows = {"a": [(f"s{i}.x.ai", "1.1.1.1") for i in range(40)]}
        result = probe_service(
            "X",
            ["a"],
            lambda profile: rows[profile],
            prober=lambda _ip, _domain: (VERDICT_OK, 10),
            reacher=lambda _ip: True,
        )
        self.assertEqual(result.domain_total, 40)
        self.assertLess(len(result.domains), 40)
        self.assertFalse(result.checked_all)


class ProbeServiceTests(unittest.TestCase):
    """Сеть подменена: prober отвечает по таблице «(адрес, домен) → вердикт»."""

    def _run(self, rows: dict, table: dict, *, dead_ips=(), cancelled=None):
        self.probed: list[tuple[str, str]] = []
        self.progress: list[tuple[int, int]] = []

        def prober(ip, host):
            self.probed.append((ip, host))
            return table.get((ip, host), (VERDICT_DEAD, None))

        return probe_service(
            "Сервис",
            list(rows),
            lambda profile: rows[profile],
            prober=prober,
            reacher=lambda ip: ip not in dead_ips,
            progress=lambda done, total: self.progress.append((done, total)),
            cancelled=cancelled,
        )

    def test_best_is_the_one_that_opens_more_domains(self) -> None:
        rows = {
            "p1": [("a.com", "1.1.1.1"), ("b.com", "1.1.1.1")],
            "p2": [("a.com", "2.2.2.2"), ("b.com", "2.2.2.2")],
        }
        table = {
            ("1.1.1.1", "a.com"): (VERDICT_OK, 50),
            ("2.2.2.2", "a.com"): (VERDICT_OK, 300),
            ("2.2.2.2", "b.com"): (VERDICT_OK, 300),
        }
        result = self._run(rows, table)

        self.assertEqual(result.best, "p2")  # медленнее, но открыл оба домена
        self.assertEqual((result.result_for("p1").ok, result.result_for("p1").total), (1, 2))
        self.assertTrue(result.result_for("p1").works)

    def test_equal_profiles_are_split_by_speed(self) -> None:
        rows = {"slow": [("a.com", "1.1.1.1")], "fast": [("a.com", "2.2.2.2")]}
        table = {("1.1.1.1", "a.com"): (VERDICT_OK, 900), ("2.2.2.2", "a.com"): (VERDICT_OK, 80)}

        self.assertEqual(self._run(rows, table).best, "fast")

    def test_region_page_is_not_an_open_site(self) -> None:
        # Адрес отвечает, сертификат настоящий — но сайт пишет «недоступно в
        # вашей стране»: профиль задачу не решил.
        rows = {"geo": [("a.com", "1.1.1.1")], "good": [("a.com", "2.2.2.2")]}
        table = {("1.1.1.1", "a.com"): (VERDICT_REGION, 40), ("2.2.2.2", "a.com"): (VERDICT_OK, 400)}
        result = self._run(rows, table)

        self.assertEqual(result.best, "good")
        self.assertFalse(result.result_for("geo").works)
        self.assertEqual(result.result_for("geo").reason, VERDICT_REGION)

    def test_domain_dead_everywhere_does_not_count_against_profiles(self) -> None:
        # Служебный домен не открылся ни через один профиль: это говорит о
        # домене, а не о профилях.
        rows = {"p1": [("a.com", "1.1.1.1"), ("junk.a.com", "1.1.1.1")]}
        result = self._run(rows, {("1.1.1.1", "a.com"): (VERDICT_OK, 60)})

        self.assertEqual((result.result_for("p1").ok, result.result_for("p1").total), (1, 1))
        self.assertEqual(result.best, "p1")

    def test_nothing_opens_means_no_best(self) -> None:
        rows = {"p1": [("a.com", "1.1.1.1")], "p2": [("a.com", "2.2.2.2")]}
        result = self._run(rows, {})

        self.assertIsNone(result.best)
        self.assertEqual(result.result_for("p1").total, 1)
        self.assertFalse(result.result_for("p1").works)

    def test_dead_address_is_not_asked_for_every_domain(self) -> None:
        rows = {"p1": [("a.com", "9.9.9.9"), ("b.com", "9.9.9.9")]}
        result = self._run(rows, {}, dead_ips={"9.9.9.9"})

        self.assertEqual(self.probed, [])  # одно соединение на адрес, а не на пару
        self.assertEqual(result.result_for("p1").reason, VERDICT_DEAD)

    def test_one_working_address_of_a_domain_is_enough(self) -> None:
        rows = {"p1": [("a.com", "1.1.1.1"), ("a.com", "1.1.1.2")]}
        result = self._run(rows, {("1.1.1.2", "a.com"): (VERDICT_OK, 70)})

        self.assertEqual((result.result_for("p1").ok, result.result_for("p1").total), (1, 1))

    def test_ipv6_rows_are_skipped(self) -> None:
        rows = {"p1": [("a.com", "2001:db8::1"), ("a.com", "1.1.1.1")]}
        self._run(rows, {("1.1.1.1", "a.com"): (VERDICT_OK, 70)})

        self.assertEqual(self.probed, [("1.1.1.1", "a.com")])

    def test_progress_reaches_the_total(self) -> None:
        rows = {"p1": [("a.com", "1.1.1.1"), ("b.com", "1.1.1.1")]}
        self._run(rows, {})

        self.assertEqual(self.progress[-1], (3, 3))  # один адрес и две пары

    def test_cancelled_probe_opens_no_connections(self) -> None:
        rows = {"p1": [("a.com", "1.1.1.1")]}
        self._run(rows, {("1.1.1.1", "a.com"): (VERDICT_OK, 70)}, cancelled=lambda: True)

        self.assertEqual(self.probed, [])

    def test_rank_ignores_profiles_that_do_not_work(self) -> None:
        results = [ProfileProbe("bad", 0, 4, None, VERDICT_DEAD), ProfileProbe("ok", 2, 4, 500)]
        self.assertEqual(rank_profiles(results), "ok")


def _choice(profile_id: str, *, mark: str = "", note: str = "") -> HostsChoice:
    return HostsChoice(profile_id, profile_id.upper(), "fa5s.circle", "#888888", mark=mark, mark_note=note)


class ProbeButtonTests(unittest.TestCase):
    def _grid(self, **tile_kwargs):
        grid = HostsTilesGrid()
        grid.resize(1200, 400)
        self.addCleanup(grid.deleteLater)
        tile = HostsTile(
            kind="tile",
            title="Grok",
            key="Grok",
            choices=tile_kwargs.pop("choices", (_choice("p1"), _choice("p2"))),
            selected=tile_kwargs.pop("selected", "p1"),
            state_text="P1",
            can_probe=True,
            **tile_kwargs,
        )
        grid.set_tiles([tile])
        QApplication.processEvents()
        self.requested: list[str] = []
        self.chosen: list[tuple[str, object]] = []
        grid.probe_requested.connect(self.requested.append)
        grid.profile_chosen.connect(lambda key, profile: self.chosen.append((key, profile)))
        return grid

    def test_button_stands_right_after_the_title(self) -> None:
        grid = self._grid()
        tile_rect, button = grid.tile_rect("Grok"), grid.probe_rect("Grok")

        self.assertTrue(tile_rect.contains(button))
        self.assertEqual(button.width(), button.height())  # круглая
        # В строке названия, выше ряда значков профилей.
        self.assertLess(button.bottom(), grid.choice_rect("Grok", "p1").top())

    def test_tile_without_profiles_has_no_button(self) -> None:
        grid = HostsTilesGrid()
        self.addCleanup(grid.deleteLater)
        grid.resize(1200, 400)
        grid.set_tiles([HostsTile(kind="tile", title="Direct", key="Direct", has_switch=True)])

        self.assertTrue(grid.probe_rect("Direct").isNull())

    def test_click_asks_to_probe_and_does_not_touch_the_profile(self) -> None:
        grid = self._grid()
        QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=grid.probe_rect("Grok").center())

        self.assertEqual(self.requested, ["Grok"])
        self.assertEqual(self.chosen, [])

    def test_click_after_a_result_probes_again_and_keeps_the_choice(self) -> None:
        # Кнопка не переставляет профиль на лучший: человек мог нарочно
        # оставить другой. После проверки она — «проверить ещё раз».
        grid = self._grid(best="p2", choices=(_choice("p1", mark="ok"), _choice("p2", mark="best")))
        QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=grid.probe_rect("Grok").center())

        self.assertEqual(self.requested, ["Grok"])
        self.assertEqual(self.chosen, [])
        self.assertIn("ещё раз", grid._tooltip_at(grid.probe_rect("Grok").center()))

    def test_best_is_picked_by_a_click_on_its_own_icon(self) -> None:
        grid = self._grid(best="p2", choices=(_choice("p1", mark="ok"), _choice("p2", mark="best")))
        QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=grid.choice_rect("Grok", "p2").center())

        self.assertEqual(self.chosen, [("Grok", "p2")])

    def test_best_name_with_a_bolt_stands_on_the_right(self) -> None:
        grid = self._grid(best="p2", choices=(_choice("p1", mark="ok"), _choice("p2", mark="best")))
        tile = grid.tiles()[0]
        plain = HostsTile(kind="tile", title="Grok", key="Grok", choices=tile.choices, selected="p1", state_text="P1", can_probe=True)
        rect = grid.tile_rect("Grok")

        self.assertTrue(grid._shows_best(tile))
        # Под молнию перед именем отведено место.
        self.assertGreater(grid._state_width(tile, rect), grid._state_width(plain, rect))
        # Пока идёт запись или проверка, справа их ход, а не имя лучшего.
        self.assertFalse(grid._shows_best(HostsTile(kind="tile", title="G", best="p2", probing=True)))

    def test_finish_effects_play_and_end(self) -> None:
        """Конец проверки: вспышка, искры, блик — и после них обычная плитка."""
        import hosts.ui.services_tiles as tiles_module

        with patch.object(tiles_module, "are_live_animations_enabled", return_value=True):
            grid = self._grid(probing=True)
            clock = [50.0]
            grid._now = lambda: clock[0]
            done = HostsTile(
                kind="tile", title="Grok", key="Grok", selected="p1", state_text="P2", can_probe=True, best="p2",
                choices=(_choice("p1", mark="bad"), _choice("p2", mark="best")),
            )
            grid.set_tiles([done])

            self.assertEqual(grid._changes["Grok"].kind, "probe")
            self.assertEqual(grid._changes["Grok"].profile_id, "p2")
            for moment in (0.02, 0.2, 0.45, 0.8, 1.1):
                clock[0] = 50.0 + moment
                grid.grab()  # рисуется без ошибок на всём протяжении
            clock[0] = 50.0 + grid.PROBE_DONE_SECONDS + 0.05
            grid._on_frame()

            self.assertNotIn("Grok", grid._changes)

    def test_click_while_probing_does_nothing(self) -> None:
        grid = self._grid(probing=True)
        QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=grid.probe_rect("Grok").center())

        self.assertEqual((self.requested, self.chosen), ([], []))

    def test_profile_icons_still_work_next_to_the_button(self) -> None:
        grid = self._grid()
        QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=grid.choice_rect("Grok", "p2").center())

        self.assertEqual(self.chosen, [("Grok", "p2")])
        self.assertEqual(self.requested, [])

    def test_shift_enter_is_the_keyboard_way_to_the_button(self) -> None:
        grid = self._grid()
        grid.setFocus()
        grid._set_cursor(grid._index_of("Grok"), ensure_visible=False)
        QTest.keyClick(grid, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)

        self.assertEqual(self.requested, ["Grok"])
        self.assertEqual(self.chosen, [])  # обычный Enter листал бы профили

    def test_tooltips_tell_what_the_button_and_the_marks_mean(self) -> None:
        fresh = self._grid()
        self.assertIn("подсказать лучший", fresh._tooltip_at(fresh.probe_rect("Grok").center()))

        grid = self._grid(choices=(_choice("p1", mark="bad", note="не открылся (0 из 6): адрес не отвечает"), _choice("p2")))
        # Рабочих нет — про молнию подсказка не говорит: молнии на плитке нет.
        self.assertEqual(grid._tooltip_at(grid.probe_rect("Grok").center()), "Проверить ещё раз (Shift+Enter)")
        self.assertIn("адрес не отвечает", grid._tooltip_at(grid.choice_rect("Grok", "p1").center()))
        self.assertEqual(grid._tooltip_at(grid.choice_rect("Grok", "p2").center()), "P2")

    def test_long_caption_gives_way_to_the_title(self) -> None:
        # «ChatGPT & Sora» превращался в «ChatGP…», когда справа вставала
        # длинная подпись хода проверки: уступает подпись, а не название.
        grid = HostsTilesGrid()
        self.addCleanup(grid.deleteLater)
        grid.resize(1200, 400)
        tile = HostsTile(
            kind="tile", title="Grok", key="Grok", choices=(_choice("p1"),), selected="p1",
            state_text="очень длинная подпись хода проверки профилей", can_probe=True, probing=True,
        )
        grid.set_tiles([tile])
        rect = grid.tile_rect("Grok")
        title_room = grid._title_right(tile, rect) - (rect.left() + grid._PAD + grid._ICON + 10)

        from PyQt6.QtGui import QFontMetrics

        self.assertGreaterEqual(title_room, QFontMetrics(grid._title_font_on).horizontalAdvance("Grok"))


class ProbePageFlowTests(unittest.TestCase):
    def _page(self):
        import test_hosts_page_draft as fixtures
        from hosts.ui.page import HostsPage

        snapshot = fixtures._snapshot("")
        self.created: list[tuple[str, dict]] = []
        feature = SimpleNamespace(
            peek_page_snapshot=lambda: snapshot,
            create_snapshot_worker=lambda request_id, parent=None: None,
            create_apply_worker=lambda request_id, selection, adobe, parent=None: None,
            create_profile_probe_worker=lambda request_id, service, rows, parent=None: self.created.append(
                (service, dict(rows))
            ),
        )
        page = HostsPage(deps=SimpleNamespace(hosts_feature=feature, open_file_page=lambda: None))
        self.addCleanup(page.deleteLater)
        self.starts: list[dict] = []

        def _start(**kwargs):
            self.starts.append(kwargs)
            kwargs["worker_factory"](len(self.starts))
            return len(self.starts), None

        for target, attribute, options in (
            (page._probe_runtime, "start_qthread_worker", {"side_effect": _start}),
            (page._probe_runtime, "is_current", {"return_value": True}),
            (page._apply_runtime, "start_qthread_worker", {"return_value": (1, None)}),
            (page, "_request_snapshot", {}),
        ):
            patcher = patch.object(target, attribute, **options)
            patcher.start()
            self.addCleanup(patcher.stop)
        page._set_snapshot(snapshot)
        return page

    @staticmethod
    def _tile(page, name: str) -> HostsTile:
        return next(tile for tile in page.tiles.tiles() if tile.key == name)

    @staticmethod
    def _result(service: str, best: str | None) -> ServiceProbe:
        return ServiceProbe(
            service,
            (ProfileProbe("p1", 0, 2, None, VERDICT_DEAD), ProfileProbe("p2", 2, 2, 120)),
            best,
        )

    def test_request_starts_a_probe_with_the_rows_that_would_be_written(self) -> None:
        page = self._page()
        page.tiles.probe_requested.emit("Alpha")

        service, rows = self.created[0]
        self.assertEqual(service, "Alpha")
        self.assertEqual(set(rows), {"p1", "p2"})
        self.assertTrue(all(rows.values()))
        self.assertTrue(self._tile(page, "Alpha").probing)

    def test_progress_is_shown_on_the_tile(self) -> None:
        page = self._page()
        page.tiles.probe_requested.emit("Alpha")
        page._on_probe_progress(1, 3, 10)

        self.assertEqual(self._tile(page, "Alpha").state_text, "3/10")

    def test_result_marks_profiles_and_suggests_the_best(self) -> None:
        page = self._page()
        page.tiles.probe_requested.emit("Alpha")
        self.starts[0]["on_loaded"](1, self._result("Alpha", "p2"))

        tile = self._tile(page, "Alpha")
        marks = {choice.profile_id: choice.mark for choice in tile.choices if choice.available}
        self.assertFalse(tile.probing)
        self.assertEqual(marks, {"p1": "bad", "p2": "best"})
        self.assertEqual(tile.best, "p2")
        self.assertEqual(tile.state_text, "Профиль 2")
        self.assertIsNone(tile.selected)  # выбор проверка не трогает
        self.assertIn("Лучший по проверке — Профиль 2", tile.accessible_text)

    def test_marks_stay_whatever_profile_is_chosen(self) -> None:
        page = self._page()
        page.tiles.probe_requested.emit("Alpha")
        self.starts[0]["on_loaded"](1, self._result("Alpha", "p2"))

        for chosen in ("p1", "p2"):
            page._set_service_profile("Alpha", chosen)
            tile = self._tile(page, "Alpha")
            with self.subTest(chosen=chosen):
                self.assertEqual(tile.selected, chosen)
                # Лучший остаётся лучшим, какой бы профиль ни выбрали.
                self.assertEqual(tile.best, "p2")
                self.assertEqual({c.profile_id: c.mark for c in tile.choices if c.available}["p2"], "best")

    def test_probing_again_drops_the_old_result(self) -> None:
        page = self._page()
        page.tiles.probe_requested.emit("Alpha")
        self.starts[0]["on_loaded"](1, self._result("Alpha", "p2"))
        page.tiles.probe_requested.emit("Alpha")

        tile = self._tile(page, "Alpha")
        self.assertTrue(tile.probing)
        self.assertIsNone(tile.best)
        self.assertEqual([c.mark for c in tile.choices if c.available], ["", ""])

    def test_nothing_works_is_said_plainly(self) -> None:
        page = self._page()
        page.tiles.probe_requested.emit("Alpha")
        self.starts[0]["on_loaded"](1, ServiceProbe("Alpha", (ProfileProbe("p1", 0, 2, None, VERDICT_DEAD),), None))

        tile = self._tile(page, "Alpha")
        self.assertIsNone(tile.best)
        self.assertEqual(tile.state_text, "нет рабочих")

    def test_second_service_waits_for_its_turn(self) -> None:
        page = self._page()
        page.tiles.probe_requested.emit("Alpha")
        page.tiles.probe_requested.emit("Beta")
        page.tiles.probe_requested.emit("Beta")  # повторный щелчок не ставит дважды

        self.assertEqual([service for service, _rows in self.created], ["Alpha"])
        self.assertEqual(self._tile(page, "Beta").state_text, "в очереди")

        self.starts[0]["on_loaded"](1, self._result("Alpha", "p2"))
        self.assertEqual([service for service, _rows in self.created], ["Alpha", "Beta"])
        self.assertTrue(self._tile(page, "Beta").probing)

    def test_direct_service_is_not_probed(self) -> None:
        page = self._page()
        page.tiles.probe_requested.emit("Direct")

        self.assertEqual(self.created, [])
        self.assertFalse(self._tile(page, "Direct").can_probe)


if __name__ == "__main__":
    unittest.main()
