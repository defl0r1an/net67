"""Обновление блока net67 при запуске не путает строки человека с устаревшими.

Строку с пометкой ``net67:manual`` добавляет кнопка на вкладке «Проверка
домена», каталог её не порождает. Пока сравнение шло по всему блоку, блок с
актуальными адресами и одной такой строкой на каждом запуске считался
«устаревшим» и переприменялся.
"""

import unittest
from unittest import mock

from hosts import hosts as hosts_module


def _content(*rows: str) -> str:
    return (
        "127.0.0.1 localhost\n"
        f"{hosts_module._MANAGED_HOSTS_BEGIN}\n"
        f"{hosts_module._MANAGED_HOSTS_NOTICE}\n"
        + "".join(f"{row}\n" for row in rows)
        + f"{hosts_module._MANAGED_HOSTS_END}\n"
    )


class ManualRowsStartupRefreshTests(unittest.TestCase):
    def _refresh(self, content: str):
        manager = hosts_module.HostsManager.__new__(hosts_module.HostsManager)
        manager._last_status = None
        manager.status_callback = lambda _message: None
        applied: list[dict] = []
        with mock.patch.object(hosts_module, "safe_read_hosts_file", return_value=content), \
             mock.patch.object(
                 hosts_module,
                 "_build_service_selection_rows",
                 return_value=([("alpha.example", "1.1.1.1")], True),
             ), \
             mock.patch.object(hosts_module, "is_ipv6_available", return_value=True), \
             mock.patch.object(
                 hosts_module.HostsManager,
                 "apply_service_dns_selections",
                 lambda _self, selection: applied.append(selection) or True,
             ):
            result = manager.refresh_applied_service_selection({"Alpha": "p1"}, has_saved_selection=True)
        return result, applied

    def test_manual_row_does_not_make_current_block_stale(self) -> None:
        result, applied = self._refresh(_content("5.6.7.8 example.org # net67:manual", "1.1.1.1 alpha.example"))
        self.assertEqual(result, (False, "адреса в hosts уже актуальны"))
        self.assertEqual(applied, [])

    def test_stale_tile_row_is_still_refreshed(self) -> None:
        result, applied = self._refresh(_content("5.6.7.8 example.org # net67:manual", "9.9.9.9 alpha.example"))
        self.assertEqual(result, (True, "адреса в hosts устарели"))
        self.assertEqual(applied, [{"Alpha": "p1"}])


if __name__ == "__main__":
    unittest.main()
