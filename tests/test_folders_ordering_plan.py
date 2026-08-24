"""Прямые тесты generic-ядра порядка папок (folders.ordering).

Единственная реализация move-семантики: resolve_folder_order + plan_view_move
+ plan_item_move. Доменные адаптеры (профили, пресеты) проверяются в своих
наборах; здесь — контракт самого ядра.
"""
from __future__ import annotations

import unittest

from folders.ordering import plan_item_move, plan_view_move, resolve_folder_order


def _state() -> dict:
    return {
        "version": 1,
        "folders": {
            "alpha": {"name": "Alpha", "order": 0, "collapsed": False, "system": False},
            "beta": {"name": "Beta", "order": 1, "collapsed": True, "system": False},
            "common": {"name": "Общие", "order": 2, "collapsed": False, "system": True},
        },
        "items": {
            "a1": {"folder_key": "alpha", "order": 0, "rating": 0},
            "a2": {"folder_key": "alpha", "order": 1, "rating": 0},
            "b1": {"folder_key": "beta", "order": 0, "rating": 5},
        },
    }


def _live(*keys: str) -> list[dict]:
    return [{"key": key, "name": key} for key in keys]


class ResolveFolderOrderTests(unittest.TestCase):
    def test_folders_sorted_by_saved_order_and_items_by_manual_then_auto(self) -> None:
        view = resolve_folder_order(_state(), _live("a1", "a2", "b1", "free-z", "free-a"))

        self.assertEqual(view.folder_keys, ("alpha", "beta", "common"))
        self.assertEqual(view.items_by_folder["alpha"], ("a1", "a2"))
        # Элементы без meta падают в common (нет folder_key у live) и
        # сортируются по имени.
        self.assertEqual(view.items_by_folder["common"], ("free-a", "free-z"))
        self.assertTrue(view.collapsed["beta"])
        self.assertEqual(view.position_by_item["a2"], 1)

    def test_rating_orders_auto_items_before_name(self) -> None:
        state = _state()
        state["items"]["rated"] = {"folder_key": "common", "order": None, "rating": 9}
        view = resolve_folder_order(state, _live("rated", "aaa"))

        # rating=9 выигрывает у имени "aaa" при отсутствии ручного order.
        self.assertEqual(view.items_by_folder["common"], ("rated", "aaa"))


class PlanViewMoveTests(unittest.TestCase):
    def test_before_and_after_insert_relative_to_destination(self) -> None:
        view = resolve_folder_order(_state(), _live("a1", "a2"))

        planned = plan_view_move(view, action="before", source_key="a2", destination_key="a1")
        self.assertEqual(planned, ("alpha", ("a2", "a1")))

        planned_after = plan_view_move(view, action="after", source_key="a1", destination_key="a2")
        self.assertEqual(planned_after, ("alpha", ("a2", "a1")))

    def test_noop_when_display_order_unchanged(self) -> None:
        view = resolve_folder_order(_state(), _live("a1", "a2"))

        self.assertIsNone(plan_view_move(view, action="before", source_key="a1", destination_key="a2"))
        self.assertIsNone(plan_view_move(view, action="end", source_key="a2"))
        self.assertIsNone(plan_view_move(view, action="after", source_key="a2", destination_key="a2"))

    def test_destination_rehomed_only_with_explicit_folder(self) -> None:
        view = resolve_folder_order(_state(), _live("a1", "a2", "b1"))

        # Без явной папки источник переезжает в папку цели.
        self.assertEqual(
            plan_view_move(view, action="before", source_key="a1", destination_key="b1"),
            ("beta", ("a1", "b1")),
        )
        # С явной папкой цель переезжает вместе с ходом (UI авторитетен).
        planned = plan_view_move(
            view,
            action="after",
            source_key="a1",
            destination_key="b1",
            destination_folder_key="alpha",
        )
        self.assertEqual(planned, ("alpha", ("a2", "b1", "a1")))


class PlanItemMoveTests(unittest.TestCase):
    def test_renumbers_only_target_folder_and_keeps_foreign_meta(self) -> None:
        state = _state()
        before_beta = dict(state["items"]["b1"])

        planned = plan_item_move(
            state,
            _live("a1", "a2"),
            action="before",
            source_key="a2",
            destination_key="a1",
        )
        self.assertIsNotNone(planned)
        self.assertEqual(planned["items"]["a2"]["order"], 0)
        self.assertEqual(planned["items"]["a1"]["order"], 1)
        self.assertEqual(planned["items"]["b1"], before_beta)
        # Исходное состояние не мутируется (план — чистая функция).
        self.assertEqual(state["items"]["a1"]["order"], 0)

    def test_cross_folder_move_sets_folder_key_only_for_moved_item(self) -> None:
        planned = plan_item_move(
            _state(),
            _live("a1", "a2", "b1"),
            action="folder",
            source_key="a1",
            destination_folder_key="beta",
        )
        self.assertIsNotNone(planned)
        self.assertEqual(planned["items"]["a1"]["folder_key"], "beta")
        self.assertEqual(planned["items"]["b1"]["folder_key"], "beta")
        self.assertEqual(planned["items"]["b1"]["order"], 0)
        self.assertEqual(planned["items"]["a1"]["order"], 1)
        # Оставшийся в alpha элемент не тронут.
        self.assertEqual(planned["items"]["a2"]["folder_key"], "alpha")
        self.assertEqual(planned["items"]["a2"]["order"], 1)

    def test_unknown_target_folder_is_rejected(self) -> None:
        self.assertIsNone(
            plan_item_move(
                _state(),
                _live("a1"),
                action="folder",
                source_key="a1",
                destination_folder_key="ghost",
            )
        )


if __name__ == "__main__":
    unittest.main()
