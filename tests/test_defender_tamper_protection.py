"""Отключение Defender честно считается с защитой от подделки.

Пока включена защита от подделки (Tamper Protection), Windows не даёт
отключить Defender из программы: записи в реестр возвращают «Отказано в
доступе». Раньше кнопка всё равно рапортовала «16/20 успешно», а Defender
оставался жив — «работает не до конца».

Обходить защиту от подделки программа не должна: снять её может только
сам человек в «Безопасности Windows». Поэтому кнопка ведёт его туда и не
врёт про успех.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _FakeManager:
    def __init__(self, *, tamper, disable_ok=True, **_kwargs) -> None:
        # tamper — список ответов is_tamper_protection_enabled по вызовам.
        self._tamper = list(tamper)
        self._disable_ok = disable_ok
        self.opened = 0
        self.disabled_called = 0

    def is_tamper_protection_enabled(self):
        return self._tamper.pop(0) if self._tamper else None

    def open_tamper_protection_settings(self):
        self.opened += 1
        return True

    def disable_defender(self):
        self.disabled_called += 1
        return (self._disable_ok, 20 if self._disable_ok else 16)


class TamperProtectionFlowTests(unittest.TestCase):
    def _run_disable(self, manager: _FakeManager):
        from program_settings import commands

        with (
            patch("windows_features.defender_manager.WindowsDefenderManager", return_value=manager),
            patch("windows_features.defender_manager.set_defender_disabled"),
        ):
            return commands.set_defender_disabled(True)

    def test_tamper_on_guides_the_user_and_does_not_pretend(self) -> None:
        manager = _FakeManager(tamper=[True])
        result = self._run_disable(manager)

        self.assertEqual(manager.disabled_called, 0)  # в стену не молотим
        self.assertEqual(manager.opened, 1)           # открыли «Безопасность Windows»
        self.assertEqual(result.level, "warning")
        self.assertIn("защит", result.content.lower())
        self.assertIs(result.revert_checked, False)   # переключатель вернулся: Defender жив

    def test_tamper_off_and_really_disabled_is_success(self) -> None:
        manager = _FakeManager(tamper=[False], disable_ok=True)
        result = self._run_disable(manager)

        self.assertEqual(manager.disabled_called, 1)
        self.assertEqual(manager.opened, 0)
        self.assertEqual(result.level, "success")

    def test_tamper_flipped_back_mid_operation_guides_again(self) -> None:
        # Перед отключением защиты не было, а сработать не вышло и защита
        # снова включена — ведём к ней, а не пишем глухое «ошибка».
        manager = _FakeManager(tamper=[False, True], disable_ok=False)
        result = self._run_disable(manager)

        self.assertEqual(manager.disabled_called, 1)
        self.assertEqual(manager.opened, 1)
        self.assertEqual(result.level, "warning")
        self.assertIs(result.revert_checked, False)

    def test_failure_without_tamper_is_an_honest_error(self) -> None:
        manager = _FakeManager(tamper=[False, False], disable_ok=False)
        result = self._run_disable(manager)

        self.assertEqual(result.level, "error")
        self.assertIn("не удалось", result.title.lower())
        self.assertIs(result.revert_checked, False)


class ManagerHonestyTests(unittest.TestCase):
    def _manager(self):
        from windows_features.defender_manager import WindowsDefenderManager

        return WindowsDefenderManager()

    def test_disable_reports_failure_when_realtime_stays_on(self) -> None:
        manager = self._manager()
        with (
            patch.object(manager, "_run_reg_command", return_value=True),
            patch("subprocess.run"),
            patch.object(manager, "is_realtime_protection_active", return_value=True),
        ):
            disabled, _count = manager.disable_defender()
        self.assertFalse(disabled)

    def test_disable_reports_success_when_realtime_went_off(self) -> None:
        manager = self._manager()
        with (
            patch.object(manager, "_run_reg_command", return_value=True),
            patch("subprocess.run"),
            patch.object(manager, "is_realtime_protection_active", return_value=False),
        ):
            disabled, _count = manager.disable_defender()
        self.assertTrue(disabled)

    def test_status_parsing_true_false_unknown(self) -> None:
        manager = self._manager()
        from unittest.mock import MagicMock

        for text, expected in (("True\n", True), ("False\r\n", False), ("", None), ("weird", None)):
            with patch("subprocess.run", return_value=MagicMock(stdout=text)):
                self.assertIs(manager.is_tamper_protection_enabled(), expected)


if __name__ == "__main__":
    unittest.main()
