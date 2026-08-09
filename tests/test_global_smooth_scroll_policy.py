from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from PyQt6.QtWidgets import QApplication, QWidget

from qfluentwidgets import ListWidget, ScrollArea, SmoothScrollArea, TextEdit
from qfluentwidgets.common.smooth_scroll import SmoothMode
from qfluentwidgets.components.widgets.scroll_area import SingleDirectionScrollArea

from settings.appearance import (
    store_warmed_animations_enabled,
    store_warmed_editor_smooth_scroll_enabled,
    store_warmed_smooth_scroll_enabled,
)
from ui.animation_policy import (
    apply_window_editor_smooth_scroll_policy,
    apply_window_smooth_scroll_policy,
)
from ui.smooth_scroll import (
    apply_editor_smooth_scroll_preference,
    install_global_smooth_scroll_policy,
    iter_managed_smooth_scroll_widgets,
)


def _delegate_of(widget):
    for attr in ("scrollDelegate", "scrollDelagate", "delegate"):
        delegate = getattr(widget, attr, None)
        if delegate is not None:
            return delegate
    return None


def _smooth_modes(widget) -> set:
    """Собирает все smooth-режимы виджета (delegate и/или прямой SmoothScroll)."""
    modes = set()
    delegate = _delegate_of(widget)
    if delegate is not None:
        modes.add(delegate.verticalSmoothScroll.smoothMode)
        modes.add(delegate.horizonSmoothScroll.smoothMode)
    smooth = getattr(widget, "smoothScroll", None)
    if smooth is not None:
        modes.add(smooth.smoothMode)
    return modes


class GlobalSmoothScrollPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        install_global_smooth_scroll_policy()

    def setUp(self) -> None:
        store_warmed_animations_enabled(True)
        store_warmed_smooth_scroll_enabled(False)
        store_warmed_editor_smooth_scroll_enabled(False)
        self._widgets: list = []

    def tearDown(self) -> None:
        for widget in self._widgets:
            widget.deleteLater()
        self._widgets.clear()

    def _track(self, widget):
        self._widgets.append(widget)
        return widget

    # --- AC1: creation-time preference ---

    def test_scroll_widgets_created_with_disabled_preference_get_no_smooth(self) -> None:
        for widget in (
            self._track(ScrollArea()),
            self._track(ListWidget()),
            self._track(SingleDirectionScrollArea()),
        ):
            self.assertEqual(
                _smooth_modes(widget),
                {SmoothMode.NO_SMOOTH},
                f"{type(widget).__name__} должен создаваться без плавной прокрутки",
            )

    def test_smooth_scroll_area_created_with_disabled_preference_disables_ani(self) -> None:
        widget = self._track(SmoothScrollArea())
        self.assertFalse(widget.delegate.useAni)
        self.assertTrue(widget.delegate._zapret_base_use_ani)
        self.assertEqual(_smooth_modes(widget), {SmoothMode.NO_SMOOTH})

    def test_scroll_widgets_created_with_enabled_preference_get_cosine(self) -> None:
        store_warmed_smooth_scroll_enabled(True)

        widget = self._track(ScrollArea())
        self.assertEqual(_smooth_modes(widget), {SmoothMode.COSINE})

        smooth_area = self._track(SmoothScrollArea())
        self.assertTrue(smooth_area.delegate.useAni)

    def test_created_widgets_are_registered(self) -> None:
        widget = self._track(ScrollArea())
        self.assertIn(widget, iter_managed_smooth_scroll_widgets())

    # --- AC2: live toggle covers registry (not only session.pages) ---

    def test_toggle_applies_to_registered_widgets_without_window_session(self) -> None:
        widget = self._track(ScrollArea())
        self.assertEqual(_smooth_modes(widget), {SmoothMode.NO_SMOOTH})

        # Плоское окно без ui_session — раньше такой виджет не попадал в обход.
        dummy_window = self._track(QWidget())

        apply_window_smooth_scroll_policy(dummy_window, True)
        self.assertEqual(_smooth_modes(widget), {SmoothMode.COSINE})

        apply_window_smooth_scroll_policy(dummy_window, False)
        self.assertEqual(_smooth_modes(widget), {SmoothMode.NO_SMOOTH})

    def test_toggle_restores_use_ani_base_value(self) -> None:
        widget = self._track(SmoothScrollArea())
        dummy_window = self._track(QWidget())

        apply_window_smooth_scroll_policy(dummy_window, True)
        self.assertTrue(widget.delegate.useAni)

        apply_window_smooth_scroll_policy(dummy_window, False)
        self.assertFalse(widget.delegate.useAni)

    # --- AC3: editors keep their own preference ---

    def test_editor_widget_ignores_page_toggle(self) -> None:
        editor = self._track(TextEdit())
        apply_editor_smooth_scroll_preference(editor)
        self.assertEqual(_smooth_modes(editor), {SmoothMode.NO_SMOOTH})

        dummy_window = self._track(QWidget())
        apply_window_smooth_scroll_policy(dummy_window, True)
        self.assertEqual(
            _smooth_modes(editor),
            {SmoothMode.NO_SMOOTH},
            "Переключатель страниц не должен трогать редакторы",
        )

    def test_editor_toggle_applies_to_registered_editors(self) -> None:
        editor = self._track(TextEdit())
        apply_editor_smooth_scroll_preference(editor)

        dummy_window = self._track(QWidget())
        store_warmed_editor_smooth_scroll_enabled(True)
        apply_window_editor_smooth_scroll_policy(dummy_window, True)
        self.assertEqual(_smooth_modes(editor), {SmoothMode.COSINE})

        store_warmed_editor_smooth_scroll_enabled(False)
        apply_window_editor_smooth_scroll_policy(dummy_window, False)
        self.assertEqual(_smooth_modes(editor), {SmoothMode.NO_SMOOTH})

    def test_editor_toggle_respects_animations_master_switch(self) -> None:
        editor = self._track(TextEdit())
        apply_editor_smooth_scroll_preference(editor)

        store_warmed_animations_enabled(False)
        store_warmed_editor_smooth_scroll_enabled(True)
        dummy_window = self._track(QWidget())
        apply_window_editor_smooth_scroll_policy(dummy_window, True)
        self.assertEqual(_smooth_modes(editor), {SmoothMode.NO_SMOOTH})

    # --- AC4: idempotent install ---

    def test_install_is_idempotent(self) -> None:
        from qfluentwidgets.common.smooth_scroll import SmoothScroll
        from qfluentwidgets.components.widgets.scroll_bar import SmoothScrollDelegate

        smooth_init_before = SmoothScroll.__init__
        delegate_init_before = SmoothScrollDelegate.__init__

        install_global_smooth_scroll_policy()

        self.assertIs(SmoothScroll.__init__, smooth_init_before)
        self.assertIs(SmoothScrollDelegate.__init__, delegate_init_before)


if __name__ == "__main__":
    unittest.main()
