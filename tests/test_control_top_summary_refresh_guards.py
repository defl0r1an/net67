from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from app.state_store import AppUiState


class _FakePresetSwitchTimer:
    """Замена QTimer из refresh_runtime_state: копит start()/timeout-колбэки."""

    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.single_shot = False
        self.start_calls: list[int] = []
        self._callbacks: list = []
        self.timeout = SimpleNamespace(connect=self._callbacks.append)

    def setSingleShot(self, value) -> None:
        self.single_shot = bool(value)

    def start(self, delay_ms) -> None:
        self.start_calls.append(int(delay_ms))

    def stop(self) -> None:
        pass

    def fire(self) -> None:
        for callback in list(self._callbacks):
            callback()


class ControlTopSummaryRefreshGuardTests(unittest.TestCase):
    def _assert_subscription_change_updates_premium_without_worker(self, page_cls) -> None:
        page = page_cls.__new__(page_cls)
        page._cleanup_in_progress = False
        page.top_summary = Mock()
        page._request_top_summary_worker = Mock(
            side_effect=AssertionError("subscription-only change must not reload preset/profile summary")
        )
        page.set_loading = Mock()
        page.update_status = Mock()
        page.update_strategy = Mock(side_effect=AssertionError("subscription-only change must not repaint strategy state"))

        page_cls._on_ui_state_changed(
            page,
            AppUiState(subscription_is_premium=True, subscription_days_remaining=14),
            frozenset({"subscription_is_premium", "subscription_days_remaining"}),
        )

        page.top_summary.set_premium.assert_called_once_with(
            is_premium=True,
            days_remaining=14,
        )
        page._request_top_summary_worker.assert_not_called()

    def _assert_subscription_change_skips_runtime_repaint(self, page_cls) -> None:
        page = page_cls.__new__(page_cls)
        page._cleanup_in_progress = False
        page.top_summary = Mock()
        page._request_top_summary_worker = Mock()
        page.set_loading = Mock(side_effect=AssertionError("subscription-only change must not repaint loading controls"))
        page.update_status = Mock(side_effect=AssertionError("subscription-only change must not repaint runtime status"))
        page.update_strategy = Mock()

        page_cls._on_ui_state_changed(
            page,
            AppUiState(subscription_is_premium=True, subscription_days_remaining=14),
            frozenset({"subscription_is_premium", "subscription_days_remaining"}),
        )

        page.set_loading.assert_not_called()
        page.update_status.assert_not_called()
        page.update_strategy.assert_not_called()


    def test_zapret2_subscription_change_skips_top_summary_worker(self) -> None:
        from presets.ui.control.zapret2.page import Zapret2ModeControlPage

        self._assert_subscription_change_updates_premium_without_worker(Zapret2ModeControlPage)


    def test_zapret2_subscription_change_skips_runtime_repaint(self) -> None:
        from presets.ui.control.zapret2.page import Zapret2ModeControlPage

        self._assert_subscription_change_skips_runtime_repaint(Zapret2ModeControlPage)


if __name__ == "__main__":
    unittest.main()
