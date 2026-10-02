"""Пресет WhatsApp покрывает и чаты, и звонки.

Раньше в этом файле жили ещё проверки ожидания выгрузки драйвера
WinDivert («включил, выключил, включил снова — и не работает»). Ту
функцию заменил движок winws_runtime/engine: он ждёт до трёх секунд,
пока драйвер довыгрузится, а если его держит чужая программа — честно
говорит об этом, а не стартует поверх. Проверки переехали вместе с
кодом: tests/test_engine_driver.py (test_unloading_driver_gets_time_to_finish,
test_stop_pending_blocks_start_and_names_the_service).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class WhatsAppPresetCoverageTests(unittest.TestCase):
    """WhatsApp должен работать без VPN от главной кнопки.

    Переписка ходит по TCP с именем в SNI — её ловил профиль по hostlist.
    Но у мессенджера много соединений вообще без SNI, а звонки и медиа
    идут по UDP. Без профилей по списку адресов и по UDP включение
    защиты чинило только чат.
    """

    PRESET = PROJECT_SRC / "presets" / "builtin" / "winws2" / "Стандартный 1.txt"

    def _text(self) -> str:
        return self.PRESET.read_text(encoding="utf-8")

    def test_preset_exists(self) -> None:
        self.assertTrue(self.PRESET.is_file())

    def test_hostlist_profile_is_there(self) -> None:
        self.assertIn("--hostlist=lists/whatsapp.txt", self._text())

    def test_ipset_profile_covers_connections_without_sni(self) -> None:
        text = self._text()

        self.assertIn("--ipset=lists/ipset-whatsapp.txt", text)
        # Имя профиля берётся из каталога, иначе страница «Профили
        # пресета» не сопоставит его со стратегией.
        blocks = [b for b in text.split("--new") if "ipset-whatsapp.txt" in b and "--filter-tcp" in b]
        self.assertTrue(blocks, "нет TCP-профиля WhatsApp по адресам")

    def test_udp_profile_covers_calls_and_media(self) -> None:
        text = self._text()
        blocks = text.split("--new")
        udp = [b for b in blocks if "--name=WhatsApp UDP wide" in b]

        self.assertTrue(udp, "нет UDP-профиля WhatsApp — звонки не заработают")
        block = udp[0]
        self.assertIn("--filter-udp=", block)
        self.assertIn("--ipset=lists/ipset-whatsapp.txt", block)

    def test_udp_ports_are_inside_the_windivert_filter(self) -> None:
        """Профиль не увидит ни пакета, если порты не открыты в заголовке."""
        text = self._text()

        self.assertIn("--wf-udp-out=443-65535", text)

    def test_referenced_lists_are_shipped(self) -> None:
        import re

        repo_root = PROJECT_SRC.parent
        for name in re.findall(r"--(?:hostlist|ipset)=lists/([^\s]+)", self._text()):
            with self.subTest(list=name):
                self.assertTrue(
                    (repo_root / "lists" / name).is_file(),
                    f"список {name} не входит в поставку",
                )


if __name__ == "__main__":
    unittest.main()
