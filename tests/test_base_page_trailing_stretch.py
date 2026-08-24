"""Замыкающее растяжение не должно отбирать высоту у списков.

BasePage добавляет в конец страницы растяжение, чтобы содержимое
прижималось к верху: без него QVBoxLayout раздавал лишнюю высоту между
карточками и на полупустых страницах заголовок с подзаголовком
разъезжались на половину окна.

Но растяжение с коэффициентом 1 делит лишнюю высоту с любым другим
элементом, который тоже её просит. На «Настройке пресета» список
профилей добавлен с stretch=1, вкладки BlockCheck — виджеты с политикой
Expanding. Замер до правки: список получал 381 пиксель из 900, а нижние
519 оставались пустыми. Именно это и было видно на скриншотах как
«половина страницы пустая».

Проверка идёт на настоящем Qt в offscreen-режиме: посчитать раскладку
на бумаге нельзя, распределение лишней высоты в QBoxLayout зависит от
суммы коэффициентов и политик размера одновременно.
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

try:
    from PyQt6.QtWidgets import QApplication, QSizePolicy, QWidget

    _app = QApplication.instance() or QApplication([])
    from ui.pages.base_page import BasePage
except Exception as exc:  # pragma: no cover - среда без Qt
    _app = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


#: Высота окна в замерах. Достаточно большая, чтобы лишняя высота была.
VIEW_HEIGHT = 900


@unittest.skipIf(_IMPORT_ERROR is not None, f"Qt недоступен: {_IMPORT_ERROR}")
class TrailingStretchTests(unittest.TestCase):
    def _shown(self, page) -> None:
        page.resize(1000, VIEW_HEIGHT)
        page.show()
        _app.processEvents()
        page.vBoxLayout.activate()
        _app.processEvents()

    def test_plain_cards_keep_natural_height(self) -> None:
        """Ради этого растяжение и вводилось — карточку не растягивает."""
        page = BasePage("Тест", "Подзаголовок")
        card = QWidget()
        card.setFixedHeight(80)
        page.add_widget(card)
        self._shown(page)

        self.assertTrue(page._trailing_stretch_expands)
        self.assertEqual(card.height(), 80)

    def test_stretched_child_gets_the_height(self) -> None:
        """Список профилей: add_widget(..., 1) на «Настройке пресета»."""
        page = BasePage("Тест", "Подзаголовок")
        host = QWidget()
        host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        page.layout.addWidget(host, 1)
        self._shown(page)

        self.assertFalse(page._trailing_stretch_expands)
        # Половина окна — это ровно та поломка, которую чиним.
        self.assertGreater(host.height(), VIEW_HEIGHT * 0.75)

    def test_expanding_child_gets_the_height(self) -> None:
        """Вкладки BlockCheck: вложенная страница — QScrollArea, Expanding."""
        page = BasePage("Тест", "Подзаголовок")
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        page.add_widget(tab)
        self._shown(page)

        self.assertFalse(page._trailing_stretch_expands)
        self.assertGreater(tab.height(), VIEW_HEIGHT * 0.75)

    def test_hidden_child_does_not_count(self) -> None:
        """BlockCheck держит все вкладки в раскладке и прячет лишние."""
        page = BasePage("Тест", "Подзаголовок")
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        page.add_widget(tab)
        self._shown(page)

        tab.setVisible(False)
        _app.processEvents()
        page.vBoxLayout.activate()
        _app.processEvents()
        self.assertTrue(page._trailing_stretch_expands)

        tab.setVisible(True)
        _app.processEvents()
        page.vBoxLayout.activate()
        _app.processEvents()
        self.assertFalse(page._trailing_stretch_expands)
        self.assertGreater(tab.height(), VIEW_HEIGHT * 0.75)

    def test_lazy_child_lands_above_the_stretch(self) -> None:
        """Вкладку создают при первом открытии — уже после показа страницы."""
        page = BasePage("Тест", "Подзаголовок")
        self._shown(page)

        late = QWidget()
        late.setFixedHeight(60)
        page.add_widget(late)
        page.vBoxLayout.activate()
        _app.processEvents()

        layout = page.vBoxLayout
        last = layout.itemAt(layout.count() - 1)
        self.assertIsNone(last.widget(), "растяжение обязано оставаться последним")
        self.assertLess(late.y(), VIEW_HEIGHT, "содержимое не должно уезжать под растяжение")


if __name__ == "__main__":
    unittest.main()
