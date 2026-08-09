"""Перечень сторонних лицензий должен быть полным.

Файл `THIRD_PARTY_LICENSES.md` — не формальность. Часть заимствований
требует сохранять уведомления при распространении, а PyQt6 вдобавок
влияет на то, под какой лицензией может выходить сам net67.

Проверка простая: каждое заимствование, которое реально попадает в
собранное приложение, должно быть в перечне названо. Забыть его легко —
особенно то, что лежит бинарником в папке и не встречается в исходниках.
"""

from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTICE = PROJECT_ROOT / "THIRD_PARTY_LICENSES.md"


#: Что обязано быть упомянуто. Слева — заимствование, справа — по чему
#: его узнать в тексте.
REQUIRED = {
    "движок обхода": ("winws", "bol-van"),
    "перехват пакетов": ("WinDivert", "LGPL"),
    "клиент туннеля": ("AmneziaWG", "MIT"),
    "ядро ссылок": ("Xray", "MPL"),
    "оформление": ("Nora", "Sandakan Nipunajith"),
    "библиотека интерфейса": ("PyQt6", "GPL"),
    "значки": ("QtAwesome",),
    "шрифт знака": ("Barlow Condensed", "OFL"),
}


class NoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = NOTICE.read_text(encoding="utf-8")

    def test_notice_exists(self) -> None:
        self.assertTrue(NOTICE.is_file(), NOTICE)

    def test_every_borrowing_is_named(self) -> None:
        for what, markers in REQUIRED.items():
            for marker in markers:
                with self.subTest(what=what, marker=marker):
                    self.assertIn(marker, self.text)

    def test_pyqt_licence_choice_is_spelled_out(self) -> None:
        """PyQt6 — GPL либо платная лицензия, третьего нет.

        Это решение владельца продукта, и оно должно стоять в тексте
        явно, а не подразумеваться строкой в таблице.
        """
        self.assertIn("Требует решения", self.text)
        self.assertIn("Riverbank", self.text)

    def test_engine_attribution_is_kept_in_the_presets(self) -> None:
        """Авторство bol-van в файлах стратегий трогать нельзя.

        Вырезать его — ровно то, чего лицензия не разрешает, и соблазн
        велик: строки выглядят как чужое имя в нашем продукте.
        """
        catalogs = PROJECT_ROOT / "src" / "profile" / "strategy_catalogs"
        found = False
        for path in catalogs.rglob("*.txt"):
            if "bol-van" in path.read_text(encoding="utf-8", errors="replace"):
                found = True
                break

        self.assertTrue(found, "авторство движка пропало из каталогов стратегий")

    def test_open_questions_are_listed(self) -> None:
        """Публиковать с незакрытыми вопросами нельзя, и они перечислены."""
        self.assertIn("Что нужно сделать до публикации", self.text)
        self.assertIn("LICENSE", self.text)


if __name__ == "__main__":
    unittest.main()
