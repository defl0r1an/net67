"""Новая оболочка net67: своё окно, своя навигация, свои полосы прокрутки.

Прежняя оболочка была окном qfluentwidgets, и правки поверх неё давали
«почти как было»: чужое оформление возвращалось при каждой перерисовке.
Здесь оболочка своя, и эти тесты стерегут именно то, ради чего её писали.
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


class PaletteTests(unittest.TestCase):
    """Палитра выросла из Nora, но теперь это лестница слоёв.

    Сначала здесь стояла проверка «всё серое»: оформление задумывалось
    строго чёрно-серо-белым. Потом облик взяли у Nora целиком, и проверка
    стала сверять цвета с её styles.css значение в значение.

    Теперь она сверяет другое. Человек попросил развести половины окна:
    «правое меню всё ещё не того цвета», «левое лучше сделать более
    светлым». Панель и содержимое в Nora одного тона (#2f3137), и слепое
    следование её значениям как раз и давало плоское окно, в котором
    половины различались только скруглением угла.

    Поэтому проверяется не совпадение с источником, а свойства, ради
    которых палитра существует: слои различимы, порядок глубины
    осмысленный, акцент остался сиреневым от Nora. Контраст и
    читаемость — в test_shell_typography_and_color.
    """

    def test_accent_is_grey(self) -> None:
        """Сиреневый акцент Nora заменён на серый по прямой просьбе.

        Было `--dark-text-color-highlight-2: 244 98% 80%` — #a19afe.
        Каналы обязаны быть равными: неравные дают цветной налёт после
        того, как тёмная тема qfluentwidgets осветлит акцент. Это уже
        случалось — #6e6e76 с синим каналом выше на восемь единиц давал
        заметный лиловый оттенок на белой кнопке.
        """
        from shell.theme import DARK, LIGHT

        for palette, name in ((DARK, "тёмная"), (LIGHT, "светлая")):
            with self.subTest(theme=name):
                red, green, blue = (
                    int(palette.accent.lstrip("#")[index : index + 2], 16)
                    for index in (0, 2, 4)
                )
                self.assertEqual({red, green, blue}, {red})

    def test_every_colour_is_strictly_neutral(self) -> None:
        """«Серо-бело-чёрный» — значит без единого подтона.

        Раньше фон был графитовым, с синим каналом выше красного на
        четыре единицы: так он выглядел у Nora, откуда бралась палитра.
        На большой площади подтон заметен, и требование сменилось на
        строго нейтральное. Проверяем все цвета сразу, а не только
        акцент: один цветной слой среди нейтральных выдаёт себя тем
        сильнее, чем ровнее остальные.
        """
        import dataclasses

        from shell.theme import DARK, LIGHT

        for palette, theme in ((DARK, "тёмная"), (LIGHT, "светлая")):
            for field in dataclasses.fields(palette):
                value = getattr(palette, field.name)
                red, green, blue = (
                    int(str(value).lstrip("#")[index : index + 2], 16)
                    for index in (0, 2, 4)
                )
                with self.subTest(theme=theme, field=field.name, value=value):
                    self.assertEqual({red, green, blue}, {red})

    def test_dark_background_is_not_pure_black(self) -> None:
        """На чистом чёрном пропадают границы, а белый текст режет глаза."""
        from shell.theme import DARK

        self.assertNotEqual(DARK.window.lower(), "#000000")
        self.assertLess(int(DARK.window.lstrip("#")[0:2], 16), 0x30)

    def test_third_party_notice_is_kept(self) -> None:
        """MIT требует сохранять уведомление об авторских правах."""
        notice = Path(__file__).resolve().parents[1] / "THIRD_PARTY_LICENSES.md"

        self.assertTrue(notice.is_file(), "уведомление о лицензии Nora потеряно")
        text = notice.read_text(encoding="utf-8")
        self.assertIn("Sandakan Nipunajith", text)
        self.assertIn("MIT License", text)

    def test_light_theme_really_inverts(self) -> None:
        from shell.theme import DARK, LIGHT

        dark_bg = int(DARK.window.lstrip("#")[0:2], 16)
        light_bg = int(LIGHT.window.lstrip("#")[0:2], 16)

        self.assertGreater(light_bg, dark_bg + 0x80)


class AccentAgreementTests(unittest.TestCase):
    """Акцент оболочки и акцент приложения должны совпадать.

    Правая часть собрана из виджетов qfluentwidgets, и цвет они берут не
    из моих стилей, а из своего themeColor — его задаёт branding. Пока
    там стоял серый, выделенный пункт панели был сиреневым, а кнопка
    рядом бирюзовой, и это было видно на каждом экране.
    """

    @staticmethod
    def _channels(value: str):
        raw = str(value).lstrip("#")
        return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))

    def test_branding_accent_is_the_same_hue_as_the_shell(self) -> None:
        import colorsys

        from branding import PALETTE_LIGHT
        from shell.theme import DARK

        def hue(value: str) -> float:
            red, green, blue = (channel / 255.0 for channel in self._channels(value))
            return colorsys.rgb_to_hsv(red, green, blue)[0] * 360.0

        # Тёмная тема qfluentwidgets осветляет акцент, поэтому светлота
        # различается намеренно. Совпадать обязан тон.
        self.assertLess(abs(hue(PALETTE_LIGHT.accent) - hue(DARK.accent)), 12.0)

    def test_accent_is_not_the_old_cyan(self) -> None:
        """Бирюза — умолчание самой библиотеки, а не выбор приложения."""
        from branding import PALETTE_LIGHT

        red, green, blue = self._channels(PALETTE_LIGHT.accent)

        self.assertFalse(green > red and blue > red, "акцент снова сине-зелёный")


class ScrollbarTests(unittest.TestCase):
    def test_scrollbars_are_custom(self) -> None:
        """Системная полоса в тёмном окне выглядит вставкой из другой программы."""
        from shell.theme import DARK, scrollbar_qss

        qss = scrollbar_qss(DARK)

        self.assertIn("QScrollBar:vertical", qss)
        self.assertIn("QScrollBar:horizontal", qss)
        self.assertIn(DARK.scrollbar_handle, qss)

    def test_arrow_buttons_are_removed(self) -> None:
        """С ненулевой высотой на концах полосы остаются пустые квадраты."""
        from shell.theme import DARK, scrollbar_qss

        qss = scrollbar_qss(DARK)

        self.assertIn("QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical", qss)
        self.assertIn("height: 0px", qss)

    def test_scrollbar_is_thin(self) -> None:
        """Полоса сообщает положение, а не претендует на внимание."""
        from shell.theme import SCROLLBAR_WIDTH

        self.assertLessEqual(SCROLLBAR_WIDTH, 8)


class GeometryTests(unittest.TestCase):
    """Пропорции боковой панели взяты из Nora."""

    def test_rail_width_matches_the_source(self) -> None:
        """`w-[30%] !max-w-[18rem]` — то есть 288 пикселей."""
        from shell.theme import RAIL_WIDTH

        self.assertEqual(RAIL_WIDTH, 288)

    def test_rail_has_a_rounded_top_corner(self) -> None:
        """`rounded-tr-2xl` — 16 пикселей. Именно это отличает панель.

        Без скругления она читается как обычное прямоугольное меню.
        """
        from shell.theme import DARK, RAIL_CORNER_RADIUS, shell_qss

        self.assertEqual(RAIL_CORNER_RADIUS, 16)
        self.assertIn(f"border-top-right-radius: {RAIL_CORNER_RADIUS}px", shell_qss(DARK))

    def test_selected_item_is_filled_with_the_accent(self) -> None:
        """В Nora выбранный пункт залит, а не подчёркнут полоской."""
        from shell.theme import DARK, shell_qss

        qss = shell_qss(DARK)
        checked = qss[qss.index("QPushButton#net67NavItem:checked") :]
        checked = checked[: checked.index("}")]

        self.assertIn(DARK.accent, checked)


try:
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - среда без Qt
    _APP = None
    _QT_ERROR = exc
else:
    _QT_ERROR = None


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class WindowTests(unittest.TestCase):
    def _entries(self):
        from shell.window import NavEntry

        return [
            NavEntry("home", "Защита", simple=True),
            NavEntry("presets", "Мои пресеты", "Настройки"),
            NavEntry("logs", "Логи", "Проверка"),
        ]

    def _window(self):
        from PyQt6.QtWidgets import QLabel

        from shell.window import ShellWindow

        window = ShellWindow(title="net67", entries=self._entries())
        for entry in self._entries():
            window.add_page(entry.key, QLabel(entry.title))
        self.addCleanup(window.deleteLater)
        return window

    def test_window_has_no_system_frame(self) -> None:
        """Иначе поверх графитового заголовка остаётся светлая полоса Windows."""
        from PyQt6.QtCore import Qt

        window = self._window()

        self.assertTrue(bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint))

    def test_navigation_switches_pages(self) -> None:
        window = self._window()

        window.show_page("logs")

        self.assertEqual(window.content.currentWidget().text(), "Логи")

    def test_simple_mode_hides_advanced_items(self) -> None:
        window = self._window()
        window.show()

        window.set_advanced(False)

        self.assertTrue(window.rail._buttons["home"].isVisible())
        self.assertFalse(window.rail._buttons["presets"].isVisible())

    def test_empty_group_heading_disappears_too(self) -> None:
        """Иначе над пустотой висит подпись, и раздел кажется сломанным."""
        window = self._window()
        window.show()

        window.set_advanced(False)

        self.assertFalse(window.rail._group_labels["Настройки"].isVisible())

    def test_advanced_mode_brings_everything_back(self) -> None:
        window = self._window()
        window.show()

        window.set_advanced(False)
        window.set_advanced(True)

        self.assertTrue(window.rail._buttons["presets"].isVisible())
        self.assertTrue(window.rail._group_labels["Настройки"].isVisible())

    def test_only_one_item_stays_selected(self) -> None:
        window = self._window()

        window.show_page("presets")
        window.show_page("logs")

        checked = [key for key, button in window.rail._buttons.items() if button.isChecked()]
        self.assertEqual(checked, ["logs"])

    def test_theme_switch_repaints_the_shell(self) -> None:
        from shell.theme import LIGHT

        window = self._window()

        window.apply_theme(dark=False)

        self.assertIn(LIGHT.window, window.styleSheet())

    def test_window_buttons_exist(self) -> None:
        """Системной рамки нет — свернуть и закрыть должны быть свои."""
        from PyQt6.QtWidgets import QPushButton

        window = self._window()
        names = {
            button.objectName()
            for button in window.title_bar.findChildren(QPushButton)
        }

        self.assertIn("net67WindowButton", names)
        self.assertIn("net67CloseButton", names)


@unittest.skipIf(_QT_ERROR is not None, f"Qt недоступен: {_QT_ERROR}")
class TitleBarLayoutTests(unittest.TestCase):
    """Кнопки окна должны оставаться неразрывной тройкой справа.

    На экране было видно: «свернуть» и «развернуть» уехали в середину
    полосы, а «закрыть» осталась справа. Причина не в вёрстке заголовка,
    а в строке поиска: attach_sidebar_search_to_titlebar вставляет её в
    ту же раскладку по индексу `count() - 1`, то есть предпоследним
    элементом, и сразу за ней добавляет растяжку. С тремя отдельными
    кнопками поиск оказывался между «развернуть» и «закрыть», а растяжка
    их растаскивала.

    Здесь повторяется ровно эта пара вставок.
    """

    def _title_bar(self):
        from shell.window import TitleBar

        bar = TitleBar("net67")
        self.addCleanup(bar.deleteLater)
        return bar

    def test_buttons_live_in_one_container(self) -> None:
        bar = self._title_bar()

        self.assertEqual(len(bar.window_buttons), 3)
        for button in bar.window_buttons:
            with self.subTest(button=button.objectName()):
                self.assertIs(button.parent(), bar.buttons_host)

    def test_search_insert_does_not_split_them(self) -> None:
        from PyQt6.QtWidgets import QLabel

        bar = self._title_bar()
        layout = bar.hBoxLayout
        search = QLabel("поиск", bar)

        # Ровно то, что делает attach_sidebar_search_to_titlebar.
        layout.insertWidget(max(0, layout.count() - 1), search)
        layout.insertStretch(layout.indexOf(search) + 1, 1)

        self.assertLess(layout.indexOf(search), layout.indexOf(bar.buttons_host))

    def test_buttons_stay_last_in_the_bar(self) -> None:
        bar = self._title_bar()
        layout = bar.hBoxLayout

        self.assertEqual(layout.indexOf(bar.buttons_host), layout.count() - 1)

    def test_buttons_keep_a_single_row_width(self) -> None:
        """Контейнер ровно по трём кнопкам: лишняя ширина съедает поиск."""
        from shell.window import TITLE_BAR_HEIGHT, WINDOW_BUTTON_SIZE

        bar = self._title_bar()

        self.assertEqual(bar.buttons_host.width(), (WINDOW_BUTTON_SIZE + 12) * 3)
        self.assertEqual(bar.buttons_host.height(), TITLE_BAR_HEIGHT)


if __name__ == "__main__":
    unittest.main()
