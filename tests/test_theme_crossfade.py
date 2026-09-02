"""Переход между темами: снимок старого вида поверх окна.

Переключение светлой и тёмной темы шло рывком, и рывок был неопрятным.
Тема применяется не одним действием: свои виджеты qfluentwidgets
перекрашивает сразу, а локальные стили страниц догоняют через цикл
событий и по одной — окно успевало побывать наполовину светлым,
наполовину тёмным.

Снимок закрывает этот промежуток, и здесь проверяется ровно то, что
делает его снимком, а не украшением: он держится непрозрачным, пока
идёт перекраска; он один, сколько бы раз тему ни переключали; он
пропускает мышь; он убирается сам; и его нет вовсе, если человек
отключил анимации.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class VeilOpacityTests(unittest.TestCase):
    """Форма затухания — чистая функция, Qt для неё не нужен."""

    def _opacity(self, progress: float) -> float:
        from ui.theme_crossfade import veil_opacity

        return veil_opacity(progress)

    def test_holds_opaque_while_the_repaint_lands(self) -> None:
        """Начни снимок таять сразу — из-под него проступит полусобранная тема."""
        from ui.theme_crossfade import CROSSFADE_HOLD

        self.assertEqual(self._opacity(0.0), 1.0)
        self.assertEqual(self._opacity(CROSSFADE_HOLD), 1.0)

    def test_fades_all_the_way_out(self) -> None:
        """Недотаявший снимок — это навсегда мутное окно."""
        self.assertEqual(self._opacity(1.0), 0.0)

    def test_fade_is_monotone(self) -> None:
        """Возврат яркости посреди перехода читается как мигание."""
        values = [self._opacity(step / 20.0) for step in range(21)]

        self.assertEqual(values, sorted(values, reverse=True))

    def test_out_of_range_is_clamped(self) -> None:
        """Анимация выдаёт доли пути, но подстраховка дешевле разбора."""
        self.assertEqual(self._opacity(-1.0), 1.0)
        self.assertEqual(self._opacity(2.0), 0.0)


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class CrossfadeTests(unittest.TestCase):
    def _window(self):
        from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

        window = QWidget()
        window.resize(420, 320)
        layout = QVBoxLayout(window)
        layout.addWidget(QLabel("net67"))
        window.setStyleSheet("background: #202225; color: #ffffff;")
        self.addCleanup(window.deleteLater)
        return window

    def _shown_window(self):
        window = self._window()
        window.show()
        _APP.processEvents()
        return window

    @staticmethod
    def _veils(window):
        from PyQt6.QtWidgets import QLabel

        return [
            child
            for child in window.findChildren(QLabel)
            if child.objectName() == "net67ThemeCrossfade"
        ]

    def test_hidden_window_gets_no_veil(self) -> None:
        """Прикрывать нечего, а снимок скрытого окна ещё и пустой."""
        from ui.theme_crossfade import crossfade_theme_change

        self.assertFalse(crossfade_theme_change(self._window()))

    def test_veil_covers_the_window(self) -> None:
        """Снимок меньше окна оставил бы видимой полосу с рывком."""
        from ui.theme_crossfade import crossfade_theme_change

        window = self._shown_window()

        self.assertTrue(crossfade_theme_change(window))
        self.assertEqual(window._net67_theme_veil.geometry(), window.rect())

    def test_veil_lets_clicks_through(self) -> None:
        """Под снимком живое окно: нажатие во время перехода должно дойти до кнопки."""
        from PyQt6.QtCore import Qt

        from ui.theme_crossfade import crossfade_theme_change

        window = self._shown_window()
        crossfade_theme_change(window)

        self.assertTrue(
            window._net67_theme_veil.testAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
        )

    def test_veil_stays_opaque_at_the_start(self) -> None:
        """Та самая полка, ради которой переход и затевался."""
        from ui.theme_crossfade import CROSSFADE_MS, crossfade_theme_change

        window = self._shown_window()
        crossfade_theme_change(window)
        effect = window._net67_theme_veil.graphicsEffect()

        opacity = 1.0
        deadline = time.time() + CROSSFADE_MS / 1000.0 * 0.15
        while time.time() < deadline:
            _APP.processEvents()
            opacity = effect.opacity()
            time.sleep(0.005)

        self.assertGreater(opacity, 0.98)

    def test_second_switch_replaces_the_first_veil(self) -> None:
        """Иначе быстрое переключение туда-обратно копит стопку картинок."""
        from ui.theme_crossfade import crossfade_theme_change

        window = self._shown_window()
        crossfade_theme_change(window)
        first = window._net67_theme_veil

        crossfade_theme_change(window)

        self.assertIsNot(window._net67_theme_veil, first)
        self.assertEqual(len(self._veils(window)), 1)

    def test_veil_removes_itself(self) -> None:
        """Оставленный слой удорожает каждую последующую перерисовку окна."""
        from ui.theme_crossfade import crossfade_theme_change

        window = self._shown_window()
        crossfade_theme_change(window)

        deadline = time.time() + 1.5
        while time.time() < deadline and window._net67_theme_veil is not None:
            _APP.processEvents()
            time.sleep(0.01)
        _APP.processEvents()

        self.assertIsNone(window._net67_theme_veil)
        self.assertEqual(self._veils(window), [])

    def test_disabled_animations_leave_the_window_alone(self) -> None:
        """Человек выключил анимации — тема применяется как раньше, без картинки."""
        from ui import animation_policy
        from ui.theme_crossfade import crossfade_theme_change

        window = self._shown_window()
        original = animation_policy.are_animations_enabled
        animation_policy.are_animations_enabled = lambda: False
        self.addCleanup(setattr, animation_policy, "are_animations_enabled", original)

        self.assertFalse(crossfade_theme_change(window))
        self.assertEqual(self._veils(window), [])


class ThemeHookTests(unittest.TestCase):
    def test_crossfade_runs_only_on_a_real_theme_change(self) -> None:
        """Тот же режим применяется и при смене акцента, и на старте.

        Снимок там прикрывает не переход, а ничего — и стоит окну лишнего
        кадра на каждое обновление акцента.
        """
        source = (PROJECT_SRC / "ui" / "theme.py").read_text(encoding="utf-8")
        head, _, tail = source.partition("crossfade_theme_change")

        self.assertTrue(tail, "вызов перехода пропал из theme.py")
        self.assertIn("if clean != _normalize_theme_name(self.current_theme", head)


if __name__ == "__main__":
    unittest.main()
