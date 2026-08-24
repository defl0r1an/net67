"""Кнопка отражает автозапуск обхода и надёжная проверка прав админа.

Две жалобы человека.

1. Автозапуск обхода поднимает обход ещё до появления кнопки на главной,
   а кнопка этого не замечала: обход работал, а под кругом висело «Обход
   выключен». Кнопка теперь при появлении сверяется с рантаймом и
   показывает «включено», если обход идёт. Запускает по-прежнему
   координатор — в том числе в свёрнутом окне.

2. Отключение Windows Defender всегда упиралось в «Требуются права
   администратора»: проверку делал IsUserAnAdmin, который у повышенного
   процесса иногда возвращает 0. Теперь права читаются по токену.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oneclick.autostart import initial_button_state  # noqa: E402
from oneclick.state import OneClickState  # noqa: E402


class InitialButtonStateTests(unittest.TestCase):
    def test_running_bypass_shows_running(self) -> None:
        self.assertIs(
            initial_button_state(bypass_running=True), OneClickState.RUNNING
        )

    def test_idle_bypass_shows_off(self) -> None:
        self.assertIs(
            initial_button_state(bypass_running=False), OneClickState.OFF
        )


class ButtonReflectsButDoesNotDoubleStartTests(unittest.TestCase):
    def _button_source(self, name: str) -> str:
        path = SRC / "oneclick" / "ui" / "button.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.unparse(node)
        raise AssertionError(f"{name} не найден в кнопке")

    def test_initial_sync_reflects_state_only(self) -> None:
        src = self._button_source("_sync_initial_state")
        self.assertIn("initial_button_state", src)
        self.assertIn("is_any_running", src)

    def test_initial_sync_does_not_start_a_worker(self) -> None:
        """Кнопка при появлении не запускает обход — это делает координатор."""
        src = self._button_source("_sync_initial_state")
        self.assertNotIn("_start_worker", src)
        self.assertNotIn("_OneClickWorker", src)


class AdminRightsTests(unittest.TestCase):
    def test_token_yes_means_admin(self) -> None:
        mod = _reload_admin_rights()
        mod._elevation_from_token = lambda: True
        mod._is_user_an_admin = lambda: False  # старая врёт «нет»
        self.assertTrue(mod.is_admin(), "токен сказал «повышен» — этого достаточно")

    def test_token_no_but_legacy_yes_means_admin(self) -> None:
        mod = _reload_admin_rights()
        mod._elevation_from_token = lambda: False
        mod._is_user_an_admin = lambda: True
        self.assertTrue(mod.is_admin())

    def test_both_no_means_not_admin(self) -> None:
        mod = _reload_admin_rights()
        mod._elevation_from_token = lambda: False
        mod._is_user_an_admin = lambda: False
        self.assertFalse(mod.is_admin())

    def test_token_unknown_falls_back_to_legacy(self) -> None:
        mod = _reload_admin_rights()
        mod._elevation_from_token = lambda: None
        mod._is_user_an_admin = lambda: True
        self.assertTrue(mod.is_admin())

    def test_defender_command_uses_the_robust_check(self) -> None:
        path = SRC / "program_settings" / "commands.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "is_user_admin":
                body = ast.unparse(node)
                self.assertIn("admin_rights", body)
                self.assertNotIn("IsUserAnAdmin", body)
                return
        self.fail("is_user_admin не найдена")


def _reload_admin_rights():
    import importlib

    import startup.admin_rights as mod

    return importlib.reload(mod)


if __name__ == "__main__":
    unittest.main()
