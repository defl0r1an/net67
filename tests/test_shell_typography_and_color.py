"""Цвет и шрифт: чтобы половины окна не выглядели из разных программ.

Три жалобы, три группы проверок.

«Правое меню всё ещё не того цвета». Карточки qfluentwidgets рисуют фон
сами, в обход таблицы стилей, — замерено: при заданном #2f3137 карточка
рисовалась цветом #3a3c41.

«Левое лучше сделать более светлым». Панель была с содержимым в один
тон, и граница между половинами держалась только на скруглении угла.

«Светлая тема полностью сломана». Оболочка ставила таблицу стилей один
раз при создании и на смену темы не реагировала: виджеты светлели,
оболочка оставалась тёмной.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _channels(value: str) -> tuple[int, int, int]:
    raw = str(value).strip().lstrip("#")
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def _luminance(value: str) -> float:
    """Относительная яркость по формуле WCAG."""
    parts = []
    for channel in _channels(value):
        c = channel / 255.0
        parts.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


def contrast(first: str, second: str) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class DepthTests(unittest.TestCase):
    """Слои должны различаться, и в понятном порядке."""

    def test_rail_is_lighter_than_content_in_dark_theme(self) -> None:
        """Ровно то, о чём просили: «левое лучше сделать более светлым»."""
        from shell.theme import DARK

        self.assertGreater(_luminance(DARK.rail), _luminance(DARK.content))

    def test_rail_stands_apart_in_light_theme_too(self) -> None:
        """В светлой теме «светлее» невозможно — панель отделяется вниз."""
        from shell.theme import LIGHT

        self.assertNotEqual(LIGHT.rail, LIGHT.content)

    def test_layers_do_not_collapse_into_one(self) -> None:
        """Одинаковые слои — это плоское окно без читаемой структуры."""
        from shell.theme import DARK, LIGHT

        for palette, name in ((DARK, "тёмная"), (LIGHT, "светлая")):
            with self.subTest(theme=name):
                layers = {palette.window, palette.content, palette.rail}
                self.assertEqual(len(layers), 3)

    def test_hover_is_visible_but_not_loud(self) -> None:
        from shell.theme import DARK

        step = contrast(DARK.surface_hover, DARK.surface)
        self.assertGreater(step, 1.1)
        self.assertLess(step, 2.5)


class ContrastTests(unittest.TestCase):
    """Текст обязан читаться. Порог 4.5 — требование WCAG AA."""

    def _pairs(self, palette):
        return (
            ("основной текст на карточке", palette.text, palette.surface),
            ("основной текст на фоне", palette.text, palette.content),
            ("приглушённый на карточке", palette.text_muted, palette.surface),
            ("пункт меню на панели", palette.text_muted, palette.rail),
            ("выбранный пункт", palette.on_accent, palette.accent),
        )

    def test_dark_theme_is_readable(self) -> None:
        from shell.theme import DARK

        for name, ink, background in self._pairs(DARK):
            with self.subTest(pair=name):
                self.assertGreaterEqual(contrast(ink, background), 4.5)

    def test_light_theme_is_readable(self) -> None:
        from shell.theme import LIGHT

        for name, ink, background in self._pairs(LIGHT):
            with self.subTest(pair=name):
                self.assertGreaterEqual(contrast(ink, background), 4.5)

    def test_dark_text_is_not_pure_white(self) -> None:
        """Чистый белый на графите даёт ореол вокруг букв."""
        from shell.theme import DARK

        self.assertNotEqual(DARK.text.lower(), "#ffffff")

    def test_light_text_is_not_pure_black(self) -> None:
        """Чистый чёрный на белом режет глаза — это и было в светлой теме."""
        from shell.theme import LIGHT

        self.assertNotEqual(LIGHT.text.lower(), "#000000")


class TypographyTests(unittest.TestCase):
    def test_scale_steps_are_ordered(self) -> None:
        from shell.theme import (
            FONT_BODY,
            FONT_CAPTION,
            FONT_DISPLAY,
            FONT_SUBTITLE,
            FONT_TITLE,
        )

        steps = [FONT_CAPTION, FONT_BODY, FONT_SUBTITLE, FONT_TITLE, FONT_DISPLAY]
        self.assertEqual(steps, sorted(steps))
        self.assertEqual(len(set(steps)), len(steps))

    def test_windows_font_comes_first(self) -> None:
        """Окно должно быть набрано тем же шрифтом, что и сама Windows."""
        from shell.theme import FONT_STACK

        self.assertTrue(FONT_STACK[0].startswith("Segoe UI"))

    def test_fallbacks_exist_for_other_systems(self) -> None:
        from shell.theme import FONT_STACK

        self.assertIn("sans-serif", FONT_STACK)

    def test_font_family_is_quoted_when_it_has_spaces(self) -> None:
        """Без кавычек Qt разбирает «Segoe UI» как два разных имени."""
        from shell.theme import font_family_css

        self.assertIn('"Segoe UI"', font_family_css())

    def test_typography_is_part_of_the_shell_stylesheet(self) -> None:
        from shell.theme import DARK, shell_qss

        qss = shell_qss(DARK)

        self.assertIn("font-family:", qss)
        self.assertIn("QWidget BodyLabel", qss)

    def test_sizes_are_not_scattered_by_hand_any_more(self) -> None:
        """Кегли берутся из шкалы, а не из случайных чисел в стилях."""
        import re

        from shell.theme import (
            FONT_BODY,
            FONT_CAPTION,
            FONT_DISPLAY,
            FONT_SUBTITLE,
            FONT_TITLE,
            DARK,
            shell_qss,
        )

        allowed = {FONT_CAPTION - 1, FONT_CAPTION, FONT_CAPTION + 1, FONT_BODY,
                   FONT_SUBTITLE, FONT_TITLE, FONT_DISPLAY}
        found = {int(value) for value in re.findall(r"font-size:\s*(\d+)px", shell_qss(DARK))}

        self.assertTrue(found <= allowed, f"кегли вне шкалы: {sorted(found - allowed)}")


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class CardPaintingTests(unittest.TestCase):
    """Карточки рисуют фон сами — значит, рисовать они должны наше."""

    def _painted(self, dark: bool) -> str:
        import qfluentwidgets
        from PyQt6.QtWidgets import QVBoxLayout, QWidget
        from qfluentwidgets import FluentIcon, SettingCard

        from shell.card_paint import install_card_painting
        from shell.theme import palette, shell_qss

        install_card_painting()
        qfluentwidgets.setTheme(
            qfluentwidgets.Theme.DARK if dark else qfluentwidgets.Theme.LIGHT
        )

        host = QWidget()
        host.setObjectName("net67Content")
        host.setStyleSheet(shell_qss(palette(dark)))
        layout = QVBoxLayout(host)
        layout.setContentsMargins(20, 20, 20, 20)
        card = SettingCard(FluentIcon.SETTING, "Заголовок", "Пояснение", host)
        layout.addWidget(card)
        host.resize(600, 320)
        host.show()
        _APP.processEvents()
        self.addCleanup(host.deleteLater)

        image = host.grab().toImage()
        point = card.mapTo(host, card.rect().topLeft())
        color = image.pixelColor(point.x() + 300, point.y() + 30)
        return f"#{color.red():02x}{color.green():02x}{color.blue():02x}"

    def test_card_uses_our_colour_in_dark_theme(self) -> None:
        from shell.theme import DARK

        self.assertEqual(self._painted(dark=True), DARK.surface)

    def test_card_uses_our_colour_in_light_theme(self) -> None:
        from shell.theme import LIGHT

        self.assertEqual(self._painted(dark=False), LIGHT.surface)

    def test_patching_twice_changes_nothing(self) -> None:
        from shell.card_paint import install_card_painting

        install_card_painting()

        self.assertEqual(install_card_painting(), ())

    def test_subclasses_are_patched_too(self) -> None:
        """SimpleCardWidget наследует CardWidget, но рисует себя сам.

        Проверка отметки через getattr нашла бы её у родителя, и
        наследник остался бы со своей отрисовкой.
        """
        import qfluentwidgets

        from shell.card_paint import install_card_painting

        install_card_painting()

        self.assertIn("_net67_card_paint", qfluentwidgets.SimpleCardWidget.__dict__)


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class SettingsGroupTests(unittest.TestCase):
    """Строки одной группы — одна карточка, а не пять отдельных блоков.

    Просьба была такая: «объединить их в одно цельное окно, в котором уже
    можно нажимать галочки». Пять переключателей подряд одинаковой высоты
    с зазорами читались как список без структуры.
    """

    def _group(self):
        import qfluentwidgets
        from PyQt6.QtWidgets import QVBoxLayout, QWidget
        from qfluentwidgets import FluentIcon, SettingCard, SettingCardGroup

        from shell.card_paint import install_card_painting
        from shell.theme import DARK

        install_card_painting()
        qfluentwidgets.setTheme(qfluentwidgets.Theme.DARK)

        host = QWidget()
        host.setObjectName("host")
        host.setAutoFillBackground(True)
        # Фон рисуем сами: у содержимого он прозрачный ради свечения.
        host.setStyleSheet(f"QWidget#host {{ background: {DARK.content}; }}")
        layout = QVBoxLayout(host)
        layout.setContentsMargins(20, 20, 20, 20)

        group = SettingCardGroup("Настройки", host)
        cards = [
            SettingCard(FluentIcon.SETTING, f"Строка {index}", "пояснение", group)
            for index in range(3)
        ]
        for card in cards:
            group.addSettingCard(card)
        layout.addWidget(group)
        layout.addStretch(1)

        host.resize(700, 420)
        host.show()
        for _ in range(4):
            _APP.processEvents()
        # Первая отрисовка схлопывает промежутки.
        host.grab()
        for _ in range(4):
            _APP.processEvents()
        self.addCleanup(host.deleteLater)
        return host, cards

    def test_rows_have_no_gap_between_them(self) -> None:
        """Зазор — это и есть «пять отдельных блоков»."""
        host, cards = self._group()
        _ = host

        tops = [card.mapTo(host, card.rect().topLeft()).y() for card in cards]
        gap = tops[1] - (tops[0] + cards[0].height())

        self.assertEqual(gap, 0)

    def test_seam_is_filled_not_see_through(self) -> None:
        """Между строками должна быть карточка, а не фон страницы."""
        from shell.theme import DARK

        host, cards = self._group()
        seam_y = cards[1].mapTo(host, cards[1].rect().topLeft()).y() - 1
        colour = host.grab().toImage().pixelColor(350, seam_y)

        page = int(DARK.content.lstrip("#")[0:2], 16)
        self.assertGreater(colour.red(), page)

    def test_outer_corner_is_rounded(self) -> None:
        """Внутренние углы не скругляем: на стыке остались бы засечки."""
        host, cards = self._group()
        top = cards[0].mapTo(host, cards[0].rect().topLeft()).y()
        image = host.grab().toImage()

        corner = image.pixelColor(21, top + 1)
        middle = image.pixelColor(350, top + 1)

        self.assertNotEqual(corner.rgb(), middle.rgb())


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class ThemeSwitchTests(unittest.TestCase):
    def _window(self):
        from shell.app_window import AppShellWindow

        window = AppShellWindow()
        # Окно надо показать. ThemeRefreshBinding намеренно откладывает
        # перерисовку спрятанных виджетов и выполняет её при показе:
        # перекрашивать то, чего нет на экране, — пустая работа на
        # каждый чих темы. Спрятанное окно эту логику и проверяло бы,
        # а не смену темы.
        window.show()
        _APP.processEvents()
        self.addCleanup(window.deleteLater)
        return window

    @staticmethod
    def _switch(theme_is_dark: bool) -> None:
        import qfluentwidgets

        qfluentwidgets.setTheme(
            qfluentwidgets.Theme.DARK if theme_is_dark else qfluentwidgets.Theme.LIGHT
        )
        # Перерисовка отложена на следующий оборот цикла событий, чтобы
        # десяток сигналов подряд не давал десяток перерисовок.
        for _ in range(4):
            _APP.processEvents()

    def test_shell_repaints_when_the_theme_changes(self) -> None:
        """Это и есть «светлая тема полностью сломана».

        Оболочка ставила таблицу стилей один раз при создании. Виджеты
        библиотеки светлели сами, оболочка оставалась тёмной — светлый
        текст на светлом фоне и графитовая панель рядом с белым.
        """
        from shell.theme import DARK, LIGHT

        self._switch(theme_is_dark=True)
        window = self._window()

        self._switch(theme_is_dark=False)
        self.assertIn(LIGHT.rail, window.styleSheet())

        self._switch(theme_is_dark=True)
        self.assertIn(DARK.rail, window.styleSheet())

    def test_window_starts_in_the_saved_theme(self) -> None:
        """Окно создаётся после setTheme, а не до, и обязано это учесть."""
        from shell.theme import LIGHT

        self._switch(theme_is_dark=False)
        window = self._window()

        self.assertIn(LIGHT.rail, window.styleSheet())

        self._switch(theme_is_dark=True)

    def test_subscription_goes_through_the_binding(self) -> None:
        """Прямая подписка на qconfig переживает виджет в сборке Nuitka.

        Соединение остаётся живым после удаления C++-объекта, и первая же
        смена темы после закрытия окна падает с RuntimeError. Binding
        отписывается сам по destroyed — это требование архитектуры, и
        отдельный страж следит за ним по всему проекту.
        """
        import inspect

        from shell import app_window

        source = inspect.getsource(app_window.AppShellWindow._subscribe_to_theme_changes)

        self.assertIn("ThemeRefreshBinding", source)
        self.assertNotIn("qconfig.themeChanged.connect", source)


if __name__ == "__main__":
    unittest.main()
