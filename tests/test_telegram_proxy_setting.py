# tests/test_telegram_proxy_setting.py
"""Настройка «прокси Telegram вместе с обходом»: место и восстановление.

Настройка сохранялась, но нигде не читалась при построении страницы.
Тумблер после перезапуска показывал «выкл.», сколько бы раз его ни
включали, а прокси при этом исправно поднимался. То есть тумблер врал
ровно наоборот — худший из возможных случаев: человек видит «выключено»
и жмёт, чтобы включить, а тем самым выключает.

Проверяется здесь не отрисовка, а два свойства, из-за которых это и
произошло: настройка попадает в снимок, и снимок доезжает до тумблера.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.runtime.program_settings_runtime_service import (  # noqa: E402
    ProgramSettingsSnapshot,
)
from presets.ui.control.control_page_runtime_shared import (  # noqa: E402
    apply_program_settings_toggles,
)


class FakeToggle:
    def __init__(self, checked: bool = False):
        self.checked = bool(checked)

    def isChecked(self) -> bool:
        return self.checked

    def setChecked(self, value, block_signals: bool = False) -> None:
        self.checked = bool(value)


def snapshot(**kwargs) -> ProgramSettingsSnapshot:
    values = {
        "auto_dpi_enabled": False,
        "gui_autostart_enabled": False,
        "tray_close_mode": "normal",
        "defender_disabled": False,
        "max_blocked": False,
        "russian_state_media_blocked": False,
        "telegram_proxy_with_bypass": False,
    }
    values.update(kwargs)
    return ProgramSettingsSnapshot(revision=tuple(values.values()), **values)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_carries_the_setting(self) -> None:
        self.assertTrue(snapshot(telegram_proxy_with_bypass=True).telegram_proxy_with_bypass)

    def test_setting_takes_part_in_the_revision(self) -> None:
        """Иначе смена настройки не считалась бы изменением снимка.

        Подписчики сравнивают именно `revision`: не попадёт туда — и
        страница не узнает, что настройку переключили в другом месте.
        """
        off = snapshot(telegram_proxy_with_bypass=False)
        on = snapshot(telegram_proxy_with_bypass=True)
        self.assertNotEqual(off.revision, on.revision)

    def test_read_from_settings(self) -> None:
        from core.runtime.program_settings_runtime_service import (
            ProgramSettingsRuntimeService,
        )
        import inspect

        source = inspect.getsource(ProgramSettingsRuntimeService._read_fast_snapshot)
        self.assertIn("telegram_proxy_with_bypass", source, "настройка не читается из файла")


class ApplyTests(unittest.TestCase):
    """Снимок обязан доезжать до тумблера."""

    def test_enabled_setting_turns_the_toggle_on(self) -> None:
        toggle = FakeToggle(False)
        apply_program_settings_toggles(
            snapshot(telegram_proxy_with_bypass=True),
            telegram_proxy_toggle=toggle,
        )
        self.assertTrue(toggle.checked)

    def test_disabled_setting_turns_the_toggle_off(self) -> None:
        toggle = FakeToggle(True)
        apply_program_settings_toggles(
            snapshot(telegram_proxy_with_bypass=False),
            telegram_proxy_toggle=toggle,
        )
        self.assertFalse(toggle.checked)

    def test_missing_toggle_is_survived(self) -> None:
        """Страница строится по частям, и тумблера может ещё не быть."""
        apply_program_settings_toggles(snapshot(telegram_proxy_with_bypass=True))

    def test_old_snapshot_without_the_field_does_not_break(self) -> None:
        """Снимок может прийти из чужого места и не знать про поле."""
        class Bare:
            pass

        toggle = FakeToggle(True)
        apply_program_settings_toggles(Bare(), telegram_proxy_toggle=toggle)
        self.assertFalse(toggle.checked, "отсутствие поля читается как «выключено»")


class PlacementTests(unittest.TestCase):
    """Тумблер стоит в «Настройках программы», а не в дополнительных."""

    #: Файл читается текстом, а не импортируется.
    #:
    #: Импорт потянул бы за собой Qt с графическими библиотеками, а
    #: проверка тут — про то, в какую карточку кладут строку. Ради неё
    #: требовать рабочий экран незачем: тест обязан идти и в сборочной
    #: машине без него.
    SOURCE = (
        Path(__file__).resolve().parents[1]
        / "src" / "presets" / "ui" / "control" / "zapret2" / "sections_build.py"
    )

    def _source(self) -> str:
        return self.SOURCE.read_text(encoding="utf-8")

    def test_added_to_the_program_settings_card(self) -> None:
        source = self._source()
        self.assertIn("program_settings_card.addSettingCard(telegram_proxy_toggle)", source)

    def test_not_in_the_advanced_rows(self) -> None:
        source = self._source()
        start = source.index("toggle_rows=[")
        rows = source[start : source.index("]", start)]
        self.assertNotIn("telegram_proxy_toggle", rows, "тумблер остался в дополнительных")

    def test_built_before_the_card_is_filled(self) -> None:
        """Порядок важен: карточка заполняется сразу после сборки строк."""
        source = self._source()
        self.assertLess(
            source.index("telegram_proxy_toggle = ("),
            source.index("program_settings_card.addSettingCard(gui_autostart_toggle)"),
        )

    def test_hidden_in_the_simple_view(self) -> None:
        from presets.ui.control.simple_view import HIDDEN_SETTING_ROWS

        self.assertIn("telegram_proxy_toggle", HIDDEN_SETTING_ROWS)

    def test_the_file_under_test_actually_exists(self) -> None:
        """Иначе перенос файла превратил бы проверки выше в пустые."""
        self.assertTrue(self.SOURCE.is_file(), f"не найден {self.SOURCE}")


if __name__ == "__main__":
    unittest.main()
