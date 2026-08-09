"""SoundCloud в редакторе hosts.

Просьба была: добавить сервис вниз списка и дать выбор DNS, как у
остальных. Здесь проверяется и то, и другое, плюс сам список адресов —
его человек прислал руками, и опечатка в домене тихо оставит кусок
сервиса нерабочим.

## Про адреса профилей

В каталоге восемь DNS-профилей. Замер по всем 821 домену показал, что
семь из них — это постоянный адрес прокси-фронтенда: у malw, malw v2,
play2go и fin ровно одно значение на весь каталог, у comss, zapret и
xbox old — одно значение с единичными исключениями. И только xbox_dns
у каждого домена свой: это настоящий адрес хоста.

Поэтому у SoundCloud заполнены семь профилей, а xbox_dns пропущен.
Загрузчик пропуск переживает — профиль без адреса просто не появится в
выборе, — а выдуманный адрес означал бы неверную строку в hosts у
двадцати человек.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


CATALOG_FILE = PROJECT_ROOT / "json" / "hosts_catalog" / "dns" / "061_soundcloud.json"

SERVICE_NAME = "SoundCloud"

#: Присланный список. Держим здесь целиком: тест должен ловить не только
#: «сервис есть», но и «ни один адрес не потерялся».
EXPECTED_HOSTS = (
    "soundcloud.com",
    "sndcdn.com",
    "soundcloud.app.goo.gl",
    "on.soundcloud.com",
    "secure.soundcloud.com",
    "api.soundcloud.com",
    "feeds.soundcloud.com",
    "media.soundcloud.com",
    "cf-media.sndcdn.com",
    "edge-api.soundcloud.com",
    "w1.sndcdn.com",
    "api-v2.soundcloud.com",
    "assets.soundcloud.com",
    "secure-media.soundcloud.com",
    "cf-hls-media.sndcdn.com",
    "mobi.soundcloud.com",
    "promote-v2.soundcloud.com",
    "charts.soundcloud.com",
    "developers.soundcloud.com",
    "checkout.soundcloud.com",
    "pre-pnd.soundcloud.com",
    "pnd.soundcloud.com",
    "help.soundcloud.com",
    "support.soundcloud.com",
    "playback.media-streaming.soundcloud.cloud",
    "soundcloud.cloud",
)


class CatalogFileTests(unittest.TestCase):
    def _payload(self) -> dict:
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))

    def test_file_exists_in_the_dns_part_of_the_catalog(self) -> None:
        """Не в hosts-части: там адрес один на всех, без выбора DNS."""
        self.assertTrue(CATALOG_FILE.is_file(), CATALOG_FILE)

    def test_every_address_from_the_list_is_present(self) -> None:
        hosts = [entry["host"] for entry in self._payload()["domains"]]

        self.assertEqual(hosts, list(EXPECTED_HOSTS))

    def test_duplicates_are_dropped(self) -> None:
        """В присланном списке дважды были sndcdn.com и cf-media.sndcdn.com.

        Повтор дал бы две одинаковые строки в hosts — файл это стерпит,
        но при снятии галочки удалилась бы только одна.
        """
        hosts = [entry["host"] for entry in self._payload()["domains"]]

        self.assertEqual(len(hosts), len(set(hosts)))

    def test_addresses_match_the_rest_of_the_catalog(self) -> None:
        """Адреса прокси взяты из каталога, а не придуманы.

        Сверяемся с соседним сервисом: если в каталоге сменится адрес
        фронтенда, тест покажет, что SoundCloud остался на старом.
        """
        neighbour = json.loads(
            (PROJECT_ROOT / "json" / "hosts_catalog" / "dns" / "055_workos.json").read_text(
                encoding="utf-8"
            )
        )
        reference = neighbour["domains"][0]["ips"]

        for entry in self._payload()["domains"]:
            with self.subTest(host=entry["host"]):
                for profile, ip in entry["ips"].items():
                    self.assertEqual(ip, reference[profile], profile)

    def test_xbox_dns_is_absent_on_purpose(self) -> None:
        """У этого профиля адрес свой у каждого домена — выдумать нельзя."""
        for entry in self._payload()["domains"]:
            with self.subTest(host=entry["host"]):
                self.assertNotIn("xbox_dns", entry["ips"])


class CatalogLoadTests(unittest.TestCase):
    def test_service_is_visible_to_the_page(self) -> None:
        from hosts.proxy_domains import get_all_services

        self.assertIn(SERVICE_NAME, get_all_services())

    def test_dns_choice_is_offered(self) -> None:
        """Просьба была именно про выбор из разных DNS."""
        from hosts.proxy_domains import get_service_available_dns_profiles

        profiles = get_service_available_dns_profiles(SERVICE_NAME)

        self.assertGreaterEqual(len(profiles), 7)
        self.assertNotIn("xbox_dns", profiles)

    def test_rows_are_built_for_every_domain(self) -> None:
        from hosts.proxy_domains import get_service_domain_ip_rows

        rows = get_service_domain_ip_rows(SERVICE_NAME, "zapret_dns")

        self.assertEqual(len(rows), len(EXPECTED_HOSTS))
        self.assertEqual(rows[0], ("soundcloud.com", "72.56.93.144"))


class PresentationTests(unittest.TestCase):
    def test_service_has_its_own_icon(self) -> None:
        """Без записи в списке сервис получил бы общий значок глобуса."""
        from hosts.proxy_domains import QUICK_SERVICES

        entry = {name: (icon, color) for icon, name, color in QUICK_SERVICES}[SERVICE_NAME]

        self.assertEqual(entry, ("fa5b.soundcloud", "#ff5500"))

    def test_service_sits_at_the_bottom_of_the_list(self) -> None:
        """Порядок в интерфейсе задаёт порядок QUICK_SERVICES."""
        from hosts.proxy_domains import QUICK_SERVICES

        self.assertEqual(QUICK_SERVICES[-1][1], SERVICE_NAME)


if __name__ == "__main__":
    unittest.main()
