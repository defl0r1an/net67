from __future__ import annotations

import unittest
from unittest.mock import Mock

from updater.ui.main_build import (
    handle_servers_breadcrumb_item_changed,
    rebuild_servers_breadcrumb,
)


def _tr(_key, default, **_kwargs):
    return default


class _FakeBreadcrumb:
    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []
        self.signals_blocked = False
        self.unblocked_add_item_calls = 0

    def blockSignals(self, blocked) -> None:  # noqa: N802
        self.signals_blocked = bool(blocked)

    def clear(self) -> None:
        self.items = []

    def addItem(self, key: str, text: str) -> None:  # noqa: N802
        if not self.signals_blocked:
            self.unblocked_add_item_calls += 1
        self.items.append((str(key), str(text)))

    def count(self) -> int:
        return len(self.items)


class UpdaterServersBreadcrumbTests(unittest.TestCase):
    def test_rebuild_restores_items_after_click_truncation(self) -> None:
        # Клик по крошке заставляет BreadcrumbBar удалить элементы правее
        # выбранного — перестройка обязана восстановить обе крошки.
        breadcrumb = _FakeBreadcrumb()
        rebuild_servers_breadcrumb(breadcrumb, tr_fn=_tr)
        self.assertEqual(
            breadcrumb.items,
            [("about", "О программе"), ("servers", "Серверы")],
        )

        breadcrumb.items = breadcrumb.items[:1]
        rebuild_servers_breadcrumb(breadcrumb, tr_fn=_tr)

        self.assertEqual(breadcrumb.count(), 2)
        self.assertEqual([key for key, _text in breadcrumb.items], ["about", "servers"])

    def test_rebuild_blocks_signals_while_adding_items(self) -> None:
        # addItem под незаблокированными сигналами эмитит currentItemChanged
        # и зациклил бы обработчик клика.
        breadcrumb = _FakeBreadcrumb()

        rebuild_servers_breadcrumb(breadcrumb, tr_fn=_tr)

        self.assertEqual(breadcrumb.unblocked_add_item_calls, 0)
        self.assertFalse(breadcrumb.signals_blocked)

    def test_about_click_restores_crumbs_and_navigates(self) -> None:
        breadcrumb = _FakeBreadcrumb()
        rebuild_servers_breadcrumb(breadcrumb, tr_fn=_tr)
        on_about_clicked = Mock()

        # Симулируем клик по "О программе": бар уже обрезан до первой крошки.
        breadcrumb.items = breadcrumb.items[:1]
        handle_servers_breadcrumb_item_changed(
            "about",
            breadcrumb=breadcrumb,
            tr_fn=_tr,
            on_about_clicked=on_about_clicked,
        )

        self.assertEqual(breadcrumb.count(), 2)
        self.assertEqual([key for key, _text in breadcrumb.items], ["about", "servers"])
        on_about_clicked.assert_called_once()

    def test_servers_click_does_not_navigate(self) -> None:
        breadcrumb = _FakeBreadcrumb()
        rebuild_servers_breadcrumb(breadcrumb, tr_fn=_tr)
        on_about_clicked = Mock()

        handle_servers_breadcrumb_item_changed(
            "servers",
            breadcrumb=breadcrumb,
            tr_fn=_tr,
            on_about_clicked=on_about_clicked,
        )

        self.assertEqual(breadcrumb.count(), 2)
        on_about_clicked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
