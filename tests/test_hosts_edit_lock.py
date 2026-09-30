"""Правки hosts из разных потоков идут по очереди.

После переноса обновления адресов при запуске у hosts появилось два
писателя, работающих одновременно: очередь «hosts» и «одна кнопка». Оба
читают файл, правят копию и пишут её целиком, так что без замка правка
того, кто записал раньше, пропадала.
"""

import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import hosts.commands as hosts_commands  # noqa: E402
import hosts.hosts as hosts_module  # noqa: E402
from windows_features.state_media_blocker import RussianStateMediaBlockerManager  # noqa: E402


def _lock_is_free_for_other_thread() -> bool:
    result: list[bool] = []

    def probe() -> None:
        acquired = hosts_module.HOSTS_EDIT_LOCK.acquire(blocking=False)
        if acquired:
            hosts_module.HOSTS_EDIT_LOCK.release()
        result.append(acquired)

    thread = threading.Thread(target=probe)
    thread.start()
    thread.join(2)
    return bool(result and result[0])


class HostsEditLockTests(unittest.TestCase):
    def _manager(self):
        manager = hosts_module.HostsManager.__new__(hosts_module.HostsManager)
        manager.status_callback = None
        manager._last_status = None
        return manager

    def test_writer_waits_while_another_edit_holds_the_file(self) -> None:
        manager = self._manager()
        finished = threading.Event()

        def write() -> None:
            manager.clear_hosts_file()
            finished.set()

        with mock.patch.object(hosts_module.HostsManager, "is_hosts_file_accessible", return_value=False):
            with hosts_module.HOSTS_EDIT_LOCK:
                thread = threading.Thread(target=write)
                thread.start()
                self.assertFalse(finished.wait(0.2), "запись прошла, не дождавшись чужой правки")
            self.assertTrue(finished.wait(2))
            thread.join(2)

    def test_startup_refresh_can_reapply_inside_its_own_lock(self) -> None:
        manager = self._manager()
        with (
            mock.patch.object(hosts_module, "safe_read_hosts_file", return_value="127.0.0.1 localhost\n"),
            mock.patch.object(hosts_module, "_iter_managed_hosts_block_rows", return_value=[("claude.ai", "87.228.47.204")]),
            mock.patch.object(hosts_module, "is_ipv6_available", return_value=False),
            mock.patch.object(
                hosts_module,
                "_build_service_selection_rows",
                return_value=([("claude.ai", "87.228.47.201")], True),
            ),
            mock.patch.object(hosts_module.HostsManager, "apply_domain_ip_rows", return_value=True) as apply_rows,
        ):
            changed, _reason = manager.refresh_applied_service_selection({"Claude": "xbox_dns"}, has_saved_selection=True)

        # Если бы замок был обычным Lock, вложенный вызов записи повис бы здесь навсегда.
        self.assertTrue(changed)
        apply_rows.assert_called_once()

    def test_startup_refresh_reads_selection_under_the_lock(self) -> None:
        seen: list[bool] = []

        def load_selection() -> dict[str, str]:
            seen.append(_lock_is_free_for_other_thread())
            return {"Claude": "xbox_dns"}

        manager = mock.Mock()
        manager.refresh_applied_service_selection.return_value = (False, "адреса в hosts уже актуальны")
        with mock.patch.object(hosts_commands, "load_user_selection", side_effect=load_selection):
            hosts_commands.refresh_applied_selection(manager)

        self.assertEqual(seen, [False])

    def test_state_media_block_edits_hosts_under_the_lock(self) -> None:
        seen: list[bool] = []

        def read_hosts() -> str:
            seen.append(_lock_is_free_for_other_thread())
            return "127.0.0.1 localhost\n"

        def write_hosts(_content: str) -> bool:
            seen.append(_lock_is_free_for_other_thread())
            return True

        blocker = RussianStateMediaBlockerManager(read_hosts_file=read_hosts, write_hosts_file=write_hosts)
        with mock.patch.object(blocker, "set_blocked_memory", return_value=True):
            ok, _message = blocker.enable_blocking()

        self.assertTrue(ok)
        self.assertEqual(seen, [False, False])


if __name__ == "__main__":
    unittest.main()
