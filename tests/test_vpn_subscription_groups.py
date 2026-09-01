# tests/test_vpn_subscription_groups.py
"""Подписки: группировка списка, трафик и обновление.

Проверяется то, что ломается молча. Группировка — это отображение
«строка списка ↔ сервер», и если оно разъедется, человек нажмёт на
Германию, а подключится к Нидерландам, причём страница ошибки не покажет.
Обновление подписки — это удаление чужих данных, и промах здесь стирает
серверы, добавленные руками.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vpn.link_store import replace_source  # noqa: E402
from vpn.links import LinkProfile  # noqa: E402
from vpn.subscriptions import (  # noqa: E402
    Subscription,
    describe_updated,
    group_by_subscription,
    parse_usage,
)


SUB = "https://sub.example.org/v2?key=abc"
OTHER = "https://other.example.net/sub"


#: Ссылка настоящая по строению: хранилище перечитывает `raw` при
#: загрузке, и заглушка вида «vless://A» вернулась бы оттуда ошибкой
#: «в ссылке нет порта».
LINK = "vless://11111111-2222-3333-4444-555555555555@node.example.org:443?type=tcp#{title}"


def server(title: str, source: str = "") -> LinkProfile:
    from urllib.parse import quote

    return LinkProfile(
        raw=LINK.format(title=quote(title)),
        title=title,
        scheme="vless",
        host="node.example.org",
        port=443,
        source=source,
    )


def subscription(**kwargs) -> Subscription:
    return Subscription(
        url=kwargs.pop("url", SUB),
        title=kwargs.pop("title", "GruVPN"),
        updated_at=kwargs.pop("updated_at", time.time()),
        **kwargs,
    )


class UsageTests(unittest.TestCase):
    """Разбор заголовка `subscription-userinfo`."""

    def test_reads_traffic_and_expiry(self) -> None:
        usage = parse_usage(
            "upload=1000000; download=312000000000; "
            "total=2048000000000; expire=1790000000"
        )
        self.assertEqual(usage.total, 2048000000000)
        self.assertEqual(usage.used, 312001000000)
        self.assertIn("из", usage.describe())
        self.assertIn("до ", usage.describe())

    def test_zero_total_means_unlimited(self) -> None:
        # Ноль в total — «без лимита», а не «нисколько». «0 из 0» было бы
        # неправдой про безлимитную подписку.
        usage = parse_usage("upload=0; download=5000; total=0")
        self.assertIsNone(usage.total)
        # «из» проверяем с пробелами: слово «израсходовано» начинается с
        # тех же букв, и без пробелов проверка ловила сама себя.
        self.assertNotIn(" из ", usage.describe())

    def test_garbage_is_survived(self) -> None:
        usage = parse_usage("совсем не тот заголовок")
        self.assertEqual(usage.describe(), "")

    def test_empty_header_says_nothing(self) -> None:
        self.assertEqual(parse_usage("").describe(), "")


class GroupingTests(unittest.TestCase):
    """Деление списка на подгруппы."""

    def test_single_manual_group_has_no_header(self) -> None:
        # Шапка над списком, у которого нет соседей, — потраченная строка.
        groups = group_by_subscription([server("A"), server("B")], [])
        self.assertEqual(groups, [("", "", [0, 1])])

    def test_empty_list_gives_no_groups(self) -> None:
        self.assertEqual(group_by_subscription([], []), [])

    def test_subscription_header_carries_traffic(self) -> None:
        info = subscription(usage=parse_usage("download=1073741824; total=10737418240"))
        groups = group_by_subscription([server("A", SUB), server("B", SUB)], [info])

        self.assertEqual(len(groups), 1)
        key, header, members = groups[0]
        self.assertEqual(key, SUB, "ключ группы — адрес подписки")
        self.assertEqual(members, [0, 1])
        self.assertIn("GruVPN", header)
        self.assertIn("2 серверов", header)
        self.assertIn("из", header)

    def test_manual_servers_get_their_own_group(self) -> None:
        profiles = [server("A", SUB), server("Мой", ""), server("B", SUB)]
        groups = group_by_subscription(profiles, [subscription()])

        headers = [header for _key, header, _members in groups]
        self.assertTrue(any("GruVPN" in text for text in headers))
        self.assertTrue(any("Мои серверы" in text for text in headers))

    def test_unknown_subscription_falls_back_to_host(self) -> None:
        # Серверы с меткой есть, записи о подписке нет — так выглядит
        # список, собранный до того, как подписки начали сохраняться.
        groups = group_by_subscription([server("A", SUB), server("Мой")], [])
        self.assertTrue(any("sub.example.org" in header for _key, header, _m in groups))

    def test_every_server_appears_exactly_once(self) -> None:
        """Главное свойство: связь строка↔сервер обязана быть взаимно однозначной.

        Порядок при группировке меняется, и если хоть один сервер
        потеряется или задвоится, выбор в списке начнёт подключать не к
        тому серверу — молча.
        """
        profiles = [
            server("A", SUB),
            server("Мой", ""),
            server("B", OTHER),
            server("C", SUB),
            server("Второй мой", ""),
        ]
        subs = [subscription(), subscription(url=OTHER, title="Другая")]

        seen: list[int] = []
        for _key, _header, members in group_by_subscription(profiles, subs):
            seen.extend(members)

        self.assertEqual(sorted(seen), list(range(len(profiles))))
        self.assertEqual(len(seen), len(set(seen)))

    def test_group_key_survives_a_changed_header(self) -> None:
        """Ключ не должен зависеть от того, что написано в заголовке.

        Заголовок меняется при каждом обновлении подписки — там и
        трафик, и «обновлено пять минут назад». Если сворачивание
        привязать к нему, свёрнутая группа разворачивалась бы сама
        после каждого обновления.
        """
        profiles = [server("A", SUB), server("Мой")]

        first = group_by_subscription(profiles, [subscription(updated_at=time.time() - 7200)])
        second = group_by_subscription(profiles, [subscription(updated_at=time.time())])

        self.assertNotEqual(first[0][1], second[0][1], "заголовок обязан был измениться")
        self.assertEqual(first[0][0], second[0][0], "ключ группы менялся вместе с заголовком")

    def test_group_order_follows_first_appearance(self) -> None:
        # Иначе группы прыгали бы местами при каждом обновлении.
        profiles = [server("Мой"), server("A", SUB)]
        headers = [h for _k, h, _m in group_by_subscription(profiles, [subscription()])]
        self.assertIn("Мои серверы", headers[0])
        self.assertIn("GruVPN", headers[1])


class DescribeUpdatedTests(unittest.TestCase):
    def test_never_updated(self) -> None:
        self.assertEqual(describe_updated(0), "ещё не обновлялась")

    def test_just_now(self) -> None:
        self.assertEqual(describe_updated(time.time()), "обновлено только что")

    def test_hours_ago(self) -> None:
        self.assertIn("ч назад", describe_updated(time.time() - 3600 * 5))


class RefreshTests(unittest.TestCase):
    """Обновление подписки заменяет её серверы, а не досыпает поверх."""

    def test_removed_server_disappears(self) -> None:
        existing = [server("A", SUB), server("B", SUB)]
        added = [server("A", SUB), server("C", SUB)]

        titles = [p.title for p in replace_source(existing, added, [SUB])]
        self.assertEqual(titles, ["A", "C"])
        self.assertNotIn("B", titles)

    def test_manual_and_foreign_servers_survive(self) -> None:
        existing = [server("A", SUB), server("Мой", ""), server("Чужой", OTHER)]
        result = replace_source(existing, added=[server("C", SUB)], sources=[SUB])

        titles = [p.title for p in result]
        self.assertIn("Мой", titles)
        self.assertIn("Чужой", titles)
        self.assertIn("C", titles)
        self.assertNotIn("A", titles)

    def test_empty_source_list_changes_nothing_but_merges(self) -> None:
        existing = [server("A", SUB)]
        titles = [p.title for p in replace_source(existing, [server("B", SUB)], [])]
        self.assertEqual(titles, ["A", "B"])

    def test_source_survives_the_store(self) -> None:
        """Метка подписки обязана пережить запись в файл и чтение обратно.

        Не переживёт — группировка развалится при следующем запуске:
        серверы вернутся без источника и лягут в «Мои серверы».
        """
        import tempfile

        from vpn.link_store import load_links, save_links

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved, message = save_links(root, [server("A", SUB), server("Мой", "")])
            self.assertTrue(saved, message)

            restored, errors = load_links(root)
            self.assertEqual(errors, [])
            sources = {p.title: p.source for p in restored}
            self.assertEqual(sources.get("A"), SUB)
            self.assertEqual(sources.get("Мой"), "")


if __name__ == "__main__":
    unittest.main()
