"""Раздел пункта определяется страницей, а не соседним заголовком.

Панель раскладывала пункты по «текущему разделу» — тому, чей заголовок
добавили последним. Пока пункты идут подряд, группа за группой, это
верно. Но панель вставляет их и по индексу, и позже: скрытые страницы
дозаводятся отдельным проходом, а при смене режима заголовки второй раз
не создаются, и «текущий раздел» остаётся от прошлой сборки.

Так BlockCheck, разбор лога winws, логи и конфигурации оказались во
вкладке «Инструменты», а «Диагностика» осталась пустой — при том, что в
схеме навигации всё расписано верно. Проверка стережёт, что раздел
берётся из схемы.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class NavGroupByRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        from shell import nav_compat

        self.nav_compat = nav_compat
        # Карта кэшируется на весь запуск; сбрасываем, чтобы проверка
        # видела свежую схему, а не остаток от соседнего теста.
        nav_compat._GROUP_BY_ROUTE = None
        self.addCleanup(setattr, nav_compat, "_GROUP_BY_ROUTE", None)

    def test_diagnostics_pages_do_not_fall_into_tools(self) -> None:
        mapping = self.nav_compat._group_by_route()

        self.assertEqual(mapping.get("BlockcheckPage"), "diagnostics")
        self.assertEqual(mapping.get("WinwsLogAnalyzerPage"), "diagnostics")

    def test_tools_section_holds_only_its_own_pages(self) -> None:
        mapping = self.nav_compat._group_by_route()

        tools = {route for route, group in mapping.items() if group == "system"}

        self.assertEqual(
            tools,
            {"NetworkPage", "HostsPage", "TelegramProxyPage", "VpnPage"},
        )

    def test_appearance_pages_are_shown_inside_diagnostics(self) -> None:
        # Слияние разделов остаётся: «Оформление» отдельной вкладкой не
        # показывается, его страницы живут в «Диагностике».
        mapping = self.nav_compat._group_by_route()

        self.assertEqual(mapping.get("LogsPage"), "diagnostics")
        self.assertEqual(mapping.get("ConfigsPage"), "diagnostics")


if __name__ == "__main__":
    unittest.main()
