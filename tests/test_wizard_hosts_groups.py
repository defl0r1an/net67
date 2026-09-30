"""Галочки мастера обязаны покрывать каталог целиком.

Проверка появилась после настоящей ошибки. В мастере стоял список из
пяти нейросетей, вписанный руками, а в каталоге их десять — Grok, Manus,
Meta AI, Trae.ai и Windsurf не попадали в hosts никогда, и заметить это
можно было только сверив два списка глазами.

Отсюда три правила, каждое закрывает свой способ снова разойтись:
каждый сервис ровно в одной группе, «Нейросети» совпадают с разделом
«ИИ» на странице, профиль у всех один и тот же.
"""

from __future__ import annotations

import unittest

from hosts.page_plans import is_ai_service
from hosts.proxy_domains import get_all_services, get_service_available_dns_profiles, prefer_measured_profiles
from wizard.plans import (
    HOSTS_GROUPS,
    PREFERRED_DNS_PROFILE,
    catalog_services,
    default_hosts_groups,
    group_services,
    hosts_service_profiles,
)


class CatalogCoverageTests(unittest.TestCase):
    def test_every_service_belongs_to_exactly_one_group(self) -> None:
        """Ни один сервис не потерян и не задвоен.

        Потерянный не попадёт в hosts, и человек не поймёт почему:
        галочка стоит, сервис не работает. Задвоенный попадёт дважды с
        разными профилями — какой победит, решит порядок обхода.
        """
        owner: dict[str, str] = {}
        for group in HOSTS_GROUPS:
            for service in group_services(group.key):
                previous = owner.get(service)
                self.assertIsNone(
                    previous,
                    f"{service} лежит и в «{previous}», и в «{group.key}»",
                )
                owner[service] = group.key

        catalog = set(catalog_services())
        self.assertTrue(catalog, "каталог сервисов пуст — проверять нечего")
        self.assertEqual(
            catalog - set(owner),
            set(),
            "эти сервисы не попали ни в одну галочку мастера",
        )

    def test_ai_group_matches_the_services_page(self) -> None:
        """«Нейросети» в мастере и раздел «ИИ» на странице — одно и то же."""
        from_page = {name for name in catalog_services() if is_ai_service(name)}
        self.assertEqual(set(group_services("ai")), from_page)

    def test_rest_group_is_not_empty_by_accident(self) -> None:
        """Остаток существует, но не подменяет собой весь каталог."""
        rest = set(group_services("rest"))
        self.assertLess(
            len(rest),
            len(catalog_services()) // 2,
            "в «Остальное» уехала половина каталога — группы выше перестали ловить",
        )


class ProfileTests(unittest.TestCase):
    def test_selected_services_get_the_preferred_profile(self) -> None:
        """Везде, где он есть, ставится один и тот же профиль.

        Разные резолверы отдают разные адреса, и вперемешку они
        устаревают вразнобой: тогда по поломке нельзя понять, что именно
        протухло.
        """
        chosen = hosts_service_profiles([g.key for g in HOSTS_GROUPS])
        self.assertTrue(chosen, "ни один сервис не выбран — проверять нечего")

        for service, profile in chosen.items():
            # Профиль, через который главный сайт в замере не открылся,
            # сама программа не ставит (prefer_measured_profiles).
            available = prefer_measured_profiles(service, get_service_available_dns_profiles(service) or [])
            if PREFERRED_DNS_PROFILE in available:
                self.assertEqual(
                    profile,
                    PREFERRED_DNS_PROFILE,
                    f"{service}: взят {profile}, хотя {PREFERRED_DNS_PROFILE} доступен",
                )

    def test_defaults_cover_the_ai_section(self) -> None:
        """Сразу отмечено то же, что включает hosts/defaults.py."""
        self.assertIn("ai", default_hosts_groups())


class GroupShapeTests(unittest.TestCase):
    def test_group_count_stays_scannable(self) -> None:
        """Экран остаётся списком галочек, а не каталогом.

        Смысл экрана в том, что его читают целиком за один взгляд.
        Больше шести пунктов — и человек начинает пролистывать.
        """
        self.assertLessEqual(len(HOSTS_GROUPS), 6)

    def test_every_group_has_examples(self) -> None:
        """Без примеров заголовок вроде «Работа и разработка» не значит ничего."""
        for group in HOSTS_GROUPS:
            self.assertTrue(group.examples.strip(), f"{group.key}: нет примеров")

    def test_examples_start_with_a_capital(self) -> None:
        """Подписи начинаются с заглавной — все шесть.

        У четырёх групп подпись начинается с названия сервиса и выходит
        заглавной сама собой, а две написаны словами — и первыми же
        уехали со строчной. В столбце из шести строк это видно сразу:
        четыре ровные, две просевшие.
        """
        for group in HOSTS_GROUPS:
            first = group.examples.strip()[:1]
            self.assertTrue(
                first.isupper(),
                f"{group.key}: подпись начинается со строчной — «{group.examples}»",
            )


if __name__ == "__main__":
    unittest.main()
