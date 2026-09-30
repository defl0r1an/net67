"""Встроенный «Стандартный 1» обходит DPI для Claude, а не пропускает его.

Claude ходит через подмену адреса в hosts: claude.ai указывает на прокси
XBOX DNS. Этого хватало, пока провайдер не начал рвать TLS по имени:
28 сентября 2026 без VPN

    curl -I --resolve claude.ai:443:87.228.47.204 https://claude.ai/
    curl: (35) Recv failure: Connection was reset

TCP к прокси открывается, соединение режут на ClientHello — это DPI, а
не блокировка адреса. Профиля для lists/claude.txt в пресете не было,
трафик уходил без обхода, и Claude работал только с VPN.

Профиль выключен по умолчанию (--skip) — так решил владелец: у кого
Claude работает через одну подмену адреса, обход для него не нужен.
Включается одним тумблером на странице «Профили пресета».
"""

import unittest
from pathlib import Path

PRESET = Path(__file__).resolve().parents[1] / "src" / "presets" / "builtin" / "winws2" / "Стандартный 1.txt"


def _profiles(text: str) -> list[list[str]]:
    blocks: list[list[str]] = [[]]
    for raw in text.splitlines():
        line = raw.strip()
        if line == "--new":
            blocks.append([])
        elif line.startswith("--"):
            blocks[-1].append(line)
    return blocks


class StandardPresetClaudeTests(unittest.TestCase):
    def test_claude_profile_desyncs_tls(self) -> None:
        profiles = [p for p in _profiles(PRESET.read_text(encoding="utf-8")) if "--hostlist=lists/claude.txt" in p]
        self.assertEqual(len(profiles), 1)
        desync = [line for line in profiles[0] if line.startswith("--lua-desync=")]
        self.assertTrue(desync)
        self.assertNotIn("--lua-desync=pass", desync)

    def test_claude_profile_is_off_by_default(self) -> None:
        profiles = [p for p in _profiles(PRESET.read_text(encoding="utf-8")) if "--hostlist=lists/claude.txt" in p]
        self.assertIn("--skip", profiles[0])


if __name__ == "__main__":
    unittest.main()
