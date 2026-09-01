# tests/test_telegram_proxy_consent.py
"""Прокси Telegram поднимается только с разрешения человека.

Поломка была замкнутой, и выбраться из неё было нельзя.

Кнопка «Включить» строила план из ответов мастера первого запуска. Галка
«Мессенджеры» отмечена там по умолчанию — значит план всегда содержал
шаг с прокси. Шаг, в свою очередь, вызывал `set_enabled(True)`, то есть
сам включал настройку, которую человек выключил.

Итог: тумблер «Прокси Telegram вместе с обходом» стоит в «выкл.»,
Telegram при каждом включении обхода выпрыгивает поверх работы с
вопросом про прокси, а в файле настроек прокси снова включён. Выключить
его было невозможно в принципе — следующее нажатие возвращало всё назад.

Здесь проверяется правило, а не отдельный вызов: разрешение даёт
человек, программа его читает и не переписывает.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


class RequestTests(unittest.TestCase):
    """План кнопки «Включить» подчиняется тумблеру, а не мастеру."""

    def _request(self, *, setting: bool, services=("messengers",)):
        from wizard import apply as wizard_apply

        with patch.object(
            wizard_apply, "_telegram_proxy_with_bypass_enabled", return_value=setting
        ), patch("settings.store.get_wizard_services", return_value=list(services)):
            return wizard_apply.build_request_from_settings()

    def test_setting_off_skips_the_step_even_with_messengers_ticked(self) -> None:
        self.assertFalse(self._request(setting=False).needs_telegram_proxy)

    def test_setting_on_enables_the_step(self) -> None:
        self.assertTrue(self._request(setting=True).needs_telegram_proxy)

    def test_setting_on_works_even_without_messengers(self) -> None:
        """Тумблер — самостоятельное разрешение, а не уточнение к мастеру."""
        self.assertTrue(self._request(setting=True, services=()).needs_telegram_proxy)

    def test_other_parts_of_the_request_survive(self) -> None:
        """Подмена шага не должна терять остальной план."""
        request = self._request(setting=False, services=("video",))
        self.assertIn("video", request.services)

    def test_broken_settings_mean_no_proxy(self) -> None:
        """Не смогли прочитать настройку — значит разрешения нет."""
        from wizard import apply as wizard_apply

        with patch("settings.store.get_program_settings", side_effect=OSError("нет файла")):
            self.assertFalse(wizard_apply._telegram_proxy_with_bypass_enabled())


class NoSilentWriteTests(unittest.TestCase):
    """Шаг не имеет права включать настройку за человека."""

    SOURCE = REPO_ROOT / "src" / "oneclick" / "deps.py"

    def test_the_file_exists(self) -> None:
        self.assertTrue(self.SOURCE.is_file(), f"не найден {self.SOURCE}")

    def test_start_step_never_enables_the_setting(self) -> None:
        source = self.SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)

        start = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_start_telegram_proxy"
        )

        calls = [
            node.func.id
            for node in ast.walk(start)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertNotIn(
            "set_enabled",
            calls,
            "шаг снова включает настройку сам — выключить прокси станет нельзя",
        )

    def test_stop_step_may_still_disable_it(self) -> None:
        """Выключение — другое дело: там человек и просит выключить."""
        source = self.SOURCE.read_text(encoding="utf-8")
        self.assertIn("set_enabled(False)", source)


class WizardWritesConsentTests(unittest.TestCase):
    """Отметил «Мессенджеры» в мастере — тумблер это показывает."""

    def _run(self, selection):
        from wizard.apply import WizardWriters, apply_wizard

        written: dict = {}

        def remember(name):
            def write(value):
                written[name] = value
                return ""

            return write

        apply_wizard(
            selection=selection,
            autostart_with_windows=False,
            minimize_to_tray=False,
            writers=WizardWriters(
                set_gui_autostart_enabled=remember("autostart"),
                set_dpi_autostart=remember("dpi"),
                set_tray_close_mode=remember("tray"),
                apply_hosts=lambda entries: "",
                set_wizard_services=remember("services"),
                set_wizard_completed=remember("completed"),
                set_telegram_proxy_with_bypass=remember("tg_proxy"),
            ),
        )
        return written

    def test_messengers_turn_the_setting_on(self) -> None:
        self.assertTrue(self._run({"messengers"})["tg_proxy"])

    def test_without_messengers_the_setting_stays_off(self) -> None:
        self.assertFalse(self._run({"video"})["tg_proxy"])

    def test_the_setting_is_written_every_time(self) -> None:
        """Мастер проходят и повторно — прежнее согласие не должно залипать."""
        self.assertIn("tg_proxy", self._run(set()))


if __name__ == "__main__":
    unittest.main()
