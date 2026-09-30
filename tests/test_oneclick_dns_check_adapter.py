"""«Одна кнопка» решает о смене DNS по новой проверке подмены.

Старая проверка (blockcheck.dns_integrity) исходный проект удалил, и
«одна кнопка» падала бы на импорте. Новая отдаёт по каждому домену
состояние ok / spoofed / local / unknown; здесь проверяется перевод этого
отчёта в итоги, которые читает should_change_dns.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oneclick.plans import integrity_from_dns_check, should_change_dns  # noqa: E402


def _report(**states):
    return {"domains": {domain.replace("_", "."): {"state": state} for domain, state in states.items()}}


class DnsCheckAdapterTests(unittest.TestCase):
    def test_spoofed_domain_triggers_dns_change(self) -> None:
        results = integrity_from_dns_check(_report(youtube_com="spoofed", discord_com="ok"))

        change, reason = should_change_dns(results)

        self.assertTrue(change)
        self.assertIn("youtube.com", reason)

    def test_honest_dns_is_left_alone(self) -> None:
        change, _reason = should_change_dns(integrity_from_dns_check(_report(youtube_com="ok", discord_com="ok")))

        self.assertFalse(change)

    def test_unverifiable_and_local_answers_are_not_spoofing(self) -> None:
        # «unknown» бывает на CDN, «local» — адрес из своего hosts. Менять
        # DNS человеку из-за них — ровно то, от чего защищает should_change_dns.
        results = integrity_from_dns_check(_report(youtube_com="unknown", discord_com="local"))

        change, reason = should_change_dns(results)

        self.assertFalse(change)
        self.assertIn("не удалось проверить", reason)

    def test_empty_or_stopped_check_changes_nothing(self) -> None:
        for report in (None, {}, {"summary": {"dns_poisoning_detected": False}, "stopped": True}):
            with self.subTest(report=report):
                self.assertEqual(integrity_from_dns_check(report), [])
                self.assertFalse(should_change_dns(integrity_from_dns_check(report))[0])


if __name__ == "__main__":
    unittest.main()
