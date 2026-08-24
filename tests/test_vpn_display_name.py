"""Имя профиля в списке — для обоих родов профилей.

Список на странице VPN один, а профили в нём двух видов: конфигурация
WireGuard и сервер, полученный из ссылки. Имя у них называется
по-разному — `name` и `title`, — и обращение к первому напрямую роняло
страницу целиком:

    AttributeError: 'LinkProfile' object has no attribute 'name'

Падало не при добавлении, а при показе. То есть подписка скачивалась,
серверы разбирались и сохранялись в файл, а окно обрывалось на попытке
их нарисовать — человек видел красное окно с трассировкой и пустой
список, хотя серверы уже лежали на диске.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class DisplayNameTests(unittest.TestCase):
    def test_link_profile_shows_its_title(self) -> None:
        from vpn.links import parse_link
        from vpn.profiles import display_name

        profile = parse_link(
            "vless://11111111-2222-3333-4444-555555555555@a.example:443?security=tls#Берлин"
        )

        self.assertEqual(display_name(profile), "Берлин")

    def test_link_without_a_name_falls_back_to_the_host(self) -> None:
        """Имя в ссылке необязательно, и «Профиль без имени» тут хуже хоста."""
        from vpn.links import parse_link
        from vpn.profiles import display_name

        profile = parse_link("trojan://secret@b.example:8443")

        self.assertEqual(display_name(profile), "b.example")

    def test_wireguard_profile_still_shows_its_name(self) -> None:
        from vpn.profiles import display_name

        profile = SimpleNamespace(name="Рабочий", endpoint_host="wg.example")

        self.assertEqual(display_name(profile), "Рабочий")

    def test_wireguard_without_a_name_falls_back_to_the_host(self) -> None:
        from vpn.profiles import display_name

        profile = SimpleNamespace(name="", endpoint_host="wg.example")

        self.assertEqual(display_name(profile), "wg.example")

    def test_nameless_and_hostless_profile_does_not_crash(self) -> None:
        """Список должен нарисоваться даже на битой записи."""
        from vpn.profiles import display_name

        self.assertEqual(display_name(SimpleNamespace()), "Профиль без имени")

    def test_whole_subscription_can_be_displayed(self) -> None:
        """Тот самый путь, на котором обрывалось окно."""
        from vpn.links import parse_subscription
        from vpn.profiles import display_name

        body = (
            "vless://11111111-2222-3333-4444-555555555555@a.example:443?security=tls#Берлин\n"
            "trojan://secret@b.example:8443#Прага\n"
            "ss://YWVzLTI1Ni1nY206cGFzcw==@c.example:8388#Вена"
        )
        profiles, _errors = parse_subscription(body)

        self.assertEqual(
            [display_name(item) for item in profiles], ["Берлин", "Прага", "Вена"]
        )


if __name__ == "__main__":
    unittest.main()
