"""Кнопка «Расширенные настройки» показывает уже созданные пункты.

Два бага, из-за которых кнопка «НИЧЕ не делала» и оставляла в сайдбаре
одни заголовки групп без строк под ними:

1. _add_sidebar_group пропускал невидимые страницы через continue, поэтому
   в простом виде расширенные пункты не создавались вообще. Показывать
   переключателю было нечего.
2. Переключатель обновлял только схему, а apply_nav_visibility_filter
   берёт минимум схемы и кэша session.nav_mode_visibility, посчитанного
   при старте в прежнем режиме.

Тест разбирает исходники, потому что обе функции работают с живыми
виджетами Qt и в headless-окружении не поднимаются.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
SIDEBAR_BUILDER = PROJECT_SRC / "ui" / "navigation" / "sidebar_builder.py"
ADVANCED_TOGGLE = PROJECT_SRC / "ui" / "navigation" / "advanced_toggle.py"


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"в {path.name} нет функции {name}")


class SidebarGroupBuildTests(unittest.TestCase):
    def test_group_skips_only_foreign_engine_pages(self) -> None:
        """Пропуск допустим лишь для страниц другого движка.

        Раскладка группы содержит страницы обоих движков: «Мои пресеты»
        режима v1 и одноимённую страницу v2. Их нельзя создавать обе —
        в панели появлялись дубли с одинаковыми подписями.

        А вот пункты, скрытые простым видом, создавать обязательно:
        переключатель режима меняет видимость уже существующих, и без
        них под заголовками групп оставалась пустота.
        """
        function = _function(SIDEBAR_BUILDER, "_add_sidebar_group")
        source = ast.unparse(function)

        self.assertIn(
            "is_page_allowed_for_method",
            source,
            "фильтровать нужно строго по движку",
        )
        # get_nav_visibility(advanced=True) для этого не годится: главные
        # страницы режимов она показывает всегда, и в панели появлялись
        # «Управление net67 v1» и «Оркестратор» одновременно с v2.
        self.assertNotIn("get_nav_visibility", source)

    def test_group_passes_visibility_instead_of_skipping(self) -> None:
        function = _function(SIDEBAR_BUILDER, "_add_sidebar_group")
        source = ast.unparse(function)

        self.assertIn("add_nav_item", source)
        self.assertIn("initial_visible=", source)


class AdvancedToggleTests(unittest.TestCase):
    def test_toggle_refreshes_visibility_cache_before_filtering(self) -> None:
        function = _function(ADVANCED_TOGGLE, "toggle_advanced_mode")
        source = ast.unparse(function)

        self.assertIn("refresh_nav_mode_visibility_cache", source)
        self.assertIn("apply_nav_visibility_filter", source)
        self.assertLess(
            source.index("refresh_nav_mode_visibility_cache(window"),
            source.index("apply_nav_visibility_filter(window"),
            "кэш надо обновить до фильтрации, иначе пункты останутся скрытыми",
        )

    def test_toggle_passes_new_mode_explicitly(self) -> None:
        """advanced=None означает «взять сохранённое», а его читают лениво."""
        function = _function(ADVANCED_TOGGLE, "toggle_advanced_mode")
        source = ast.unparse(function)

        self.assertIn("advanced=next_value", source)

    def test_cache_refresh_is_public(self) -> None:
        import ast as _ast

        tree = _ast.parse(SIDEBAR_BUILDER.read_text(encoding="utf-8"))
        names = {
            node.name
            for node in _ast.walk(tree)
            if isinstance(node, _ast.FunctionDef)
        }

        self.assertIn("refresh_nav_mode_visibility_cache", names)
        self.assertIn(
            '"refresh_nav_mode_visibility_cache"',
            SIDEBAR_BUILDER.read_text(encoding="utf-8"),
            "функция должна быть в __all__",
        )


class SimpleModeSchemaTests(unittest.TestCase):
    @staticmethod
    def _load_schema():
        """Грузит schema.py файлом, минуя пакет ui.navigation.

        ui/navigation/__init__.py тянет search.py, а тот — QtGui, которого
        в headless-окружении нет. Сама schema.py от Qt не зависит.
        """
        import importlib.util
        import sys

        if str(PROJECT_SRC) not in sys.path:
            sys.path.insert(0, str(PROJECT_SRC))

        path = PROJECT_SRC / "ui" / "navigation" / "schema.py"
        spec = importlib.util.spec_from_file_location("nav_schema_under_test", path)
        module = importlib.util.module_from_spec(spec)
        # @dataclass ищет модуль в sys.modules, чтобы разрешить аннотации.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_simple_mode_keeps_mode_entry_page(self) -> None:
        """В простом виде главная страница режима остаётся видимой."""
        import sys

        if str(PROJECT_SRC) not in sys.path:
            sys.path.insert(0, str(PROJECT_SRC))

        from app.page_names import PageName
        from settings.mode import ZAPRET2_MODE

        get_nav_visibility = self._load_schema().get_nav_visibility

        simple = get_nav_visibility(ZAPRET2_MODE, advanced=False)
        advanced = get_nav_visibility(ZAPRET2_MODE, advanced=True)

        self.assertTrue(simple.get(PageName.ZAPRET2_MODE_CONTROL))
        # «Оформление» здесь когда-то было второй страницей простого
        # вида. Раздел убрали из навигации, а затем удалили и саму
        # страницу — сверять теперь нечего, самой записи в схеме нет.

        visible_simple = {page for page, shown in simple.items() if shown}
        visible_advanced = {page for page, shown in advanced.items() if shown}

        self.assertLess(
            len(visible_simple),
            len(visible_advanced),
            "простой вид обязан показывать меньше разделов",
        )
        self.assertTrue(
            visible_simple.issubset(visible_advanced),
            "расширенный вид должен включать всё, что видно в простом",
        )



class SidebarHidesInSimpleModeTests(unittest.TestCase):
    """В простом виде панель прячется целиком, а не пустеет.

    Промежуточно я оставлял панель на месте, убирая из неё пункты. Это
    оказалось худшим из двух вариантов: слева висела тёмная полоса в
    288 пикселей, и человек читал её как поломку. Ради двух пунктов
    столько места не нужно — возврат к полному интерфейсу живёт кнопкой
    на самой странице.
    """

    def test_simple_mode_hides_the_panel(self) -> None:
        import inspect

        from ui.navigation.advanced_toggle import apply_sidebar_width_for_mode

        source = inspect.getsource(apply_sidebar_width_for_mode)

        self.assertIn("nav.setVisible(advanced)", source)

    def test_startup_restores_the_panel_size(self) -> None:
        """Сворачивание оставляет панели нулевую ширину.

        Без восстановления окно, запущенное сразу в расширенном режиме,
        открылось бы с пустой полосой слева — ровно та поломка, из-за
        которой выезд панели и переписан на изменение размера.
        """
        import inspect

        from ui.navigation.advanced_toggle import apply_sidebar_width_for_mode

        source = inspect.getsource(apply_sidebar_width_for_mode)

        self.assertIn("apply_panel_state", source)

    def test_manual_toggle_goes_through_the_animation(self) -> None:
        """Видимостью распоряжается анимация, иначе движения не видно."""
        import inspect

        from ui.navigation import advanced_toggle

        source = inspect.getsource(advanced_toggle.toggle_advanced_mode)

        self.assertIn("_slide_navigation_panel", source)
        self.assertNotIn("apply_sidebar_width_for_mode(window", source)

    def test_page_keeps_a_way_back(self) -> None:
        """Спрятанная панель не должна уносить с собой возврат."""
        from presets.ui.control import simple_view

        self.assertTrue(hasattr(simple_view, "attach_advanced_button"))

if __name__ == "__main__":
    unittest.main()
