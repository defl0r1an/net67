from __future__ import annotations

import unittest
from unittest.mock import patch

from windows_features.state_media_blocker import (
    RussianStateMediaBlockerManager,
    build_hosts_content_with_state_media_block,
    get_state_media_domains,
)


class StateMediaBlockerTests(unittest.TestCase):
    def test_build_hosts_content_adds_expected_domains_once(self) -> None:
        content = "127.0.0.1 localhost\n"

        first = build_hosts_content_with_state_media_block(content, enabled=True)
        second = build_hosts_content_with_state_media_block(first, enabled=True)

        self.assertEqual(first, second)
        self.assertIn("127.0.0.1 tass.ru", first)
        self.assertIn("::1 russian.rt.com", first)
        self.assertIn("127.0.0.1 1tv.ru", first)
        self.assertEqual(first.count("net67:russian-state-media-block begin"), 1)
        # Метка уходит в системный hosts, который человек открывает
        # блокнотом. Имя исходного проекта там оставалось до последнего.
        self.assertNotIn("zapretgui", first)

    def test_build_hosts_content_removes_only_own_block(self) -> None:
        content = "\n".join(
            [
                "127.0.0.1 localhost",
                "# user row",
                "127.0.0.1 example.test",
                "",
            ]
        )
        blocked = build_hosts_content_with_state_media_block(content, enabled=True)

        restored = build_hosts_content_with_state_media_block(blocked, enabled=False)

        self.assertIn("127.0.0.1 localhost", restored)
        self.assertIn("127.0.0.1 example.test", restored)
        self.assertNotIn("tass.ru", restored)
        self.assertNotIn("net67:russian-state-media-block", restored)

    def test_block_written_by_the_previous_name_is_still_removed(self) -> None:
        """Иначе старый блок остался бы в hosts навсегда.

        Метку переименовали, а у тех, кто включал блокировку раньше, в
        hosts лежит блок со старым именем. Снятие блокировки искало бы
        только новую метку и прошло бы мимо — домены остались бы
        перенаправленными в никуда, и найти виноватого было бы нечем.
        """
        legacy = "\n".join(
            [
                "127.0.0.1 localhost",
                "# >>> zapretgui:russian-state-media-block begin >>>",
                "127.0.0.1 tass.ru",
                "::1 tass.ru",
                "# <<< zapretgui:russian-state-media-block end <<<",
                "127.0.0.1 example.test",
                "",
            ]
        )

        restored = build_hosts_content_with_state_media_block(legacy, enabled=False)

        self.assertNotIn("tass.ru", restored)
        self.assertNotIn("zapretgui", restored)
        self.assertIn("127.0.0.1 localhost", restored)
        self.assertIn("127.0.0.1 example.test", restored)

    def test_legacy_block_is_replaced_not_doubled(self) -> None:
        """Включение поверх старого блока не должно давать два блока."""
        legacy = "\n".join(
            [
                "127.0.0.1 localhost",
                "# >>> zapretgui:russian-state-media-block begin >>>",
                "127.0.0.1 tass.ru",
                "# <<< zapretgui:russian-state-media-block end <<<",
                "",
            ]
        )

        blocked = build_hosts_content_with_state_media_block(legacy, enabled=True)

        self.assertEqual(blocked.count("127.0.0.1 tass.ru"), 1)
        self.assertNotIn("zapretgui", blocked)

    def test_manager_writes_hosts_and_persists_memory(self) -> None:
        written: list[str] = []
        manager = RussianStateMediaBlockerManager(
            read_hosts_file=lambda: "127.0.0.1 localhost\n",
            write_hosts_file=lambda content: written.append(content) is None or True,
        )

        with patch("settings.store.set_russian_state_media_blocked", return_value=True) as save:
            success, message = manager.enable_blocking()

        self.assertTrue(success)
        self.assertIn("включена", message)
        self.assertEqual(save.call_args.args, (True,))
        self.assertIn("127.0.0.1 rg.ru", written[-1])

    def test_domain_list_has_no_duplicates(self) -> None:
        domains = get_state_media_domains()

        self.assertEqual(len(domains), len(set(domains)))
        self.assertIn("tass.ru", domains)
        self.assertIn("vesti.ru", domains)


if __name__ == "__main__":
    unittest.main()
