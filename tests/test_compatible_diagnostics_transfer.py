"""Переходы диагностики не запускают сеть и не обходят общий писатель hosts."""
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget


class TransferUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_opening_dns_tab_does_not_start_a_check(self):
        from test_blockcheck_page_accessibility import _make_page
        page = _make_page()
        page._dns = Mock()
        self.addCleanup(page.cleanup)
        self.addCleanup(page.deleteLater)
        page.show()
        QTest.qWait(20)
        page.switch_to_tab(page.TAB_DNS_SERVERS)
        self.assertIsNotNone(page._dns_servers_tab_page)
        page._dns.create_server_check_worker.assert_not_called()
        self.assertTrue(page._dns_servers_tab_page.start_button.isEnabled())

    def test_known_domain_opens_its_service_without_a_manual_write(self):
        from dns.domain_lookup import DomainLookupReport
        from dns.ui.domain_lookup_page import DomainLookupPage
        open_service = Mock()
        page = DomainLookupPage(dns_feature=Mock(), open_hosts_service=open_service)
        self.addCleanup(page.cleanup)
        self.addCleanup(page.deleteLater)
        page._show_report(DomainLookupReport(target='www.youtube.com', kind='domain', primary_ip='1.1.1.1', hosts_service='YouTube', finished=True))
        with patch('app.feature_facades.hosts.create_domain_hosts_worker') as writer:
            page.add_to_hosts_btn.click()
        open_service.assert_called_once_with('YouTube')
        writer.assert_not_called()

    def test_kind_tile_can_be_opened_with_the_keyboard(self):
        from blockcheck.ui.block_kinds_view import KindTile, SiteGroup
        tile = KindTile(SiteGroup('sni', 'По имени', ('example.com',)))
        self.addCleanup(tile.deleteLater)
        opened = []
        tile.opened.connect(opened.append)
        QTest.keyClick(tile, Qt.Key.Key_Return)
        self.assertEqual(opened, ['sni'])
        self.assertNotEqual(tile.focusPolicy(), Qt.FocusPolicy.NoFocus)

    def test_matrix_keyboard_selects_the_next_service(self):
        from blockcheck.ui.server_matrix import ServerMatrix, ServerRow
        matrix = ServerMatrix(['UDP'], [ServerRow('Первый', '1.1.1.1', ('ok',)), ServerRow('Второй', '2.2.2.2', ('ok',))])
        self.addCleanup(matrix.deleteLater)
        opened = []
        matrix.opened.connect(opened.append)
        QTest.keyClick(matrix, Qt.Key.Key_Down)
        QTest.keyClick(matrix, Qt.Key.Key_Space)
        self.assertEqual(opened, [1])

    def test_reveal_waits_for_the_common_entry_animation(self):
        from ui.widgets.reveal import Reveal
        widget = QWidget()
        self.addCleanup(widget.deleteLater)
        reveal = Reveal(widget)
        with patch('ui.widgets.stagger_float_in.is_floating_in', return_value=True):
            reveal._start_when_landed()
        self.assertTrue(reveal._wait.isActive())
        reveal._wait.stop()


class AddressCancellationTests(unittest.TestCase):
    def test_address_commit_and_refresh_share_the_hosts_lock(self):
        from hosts import commands
        from hosts.address_engine import EngineReport
        from hosts.address_worker import HostsAddressCheckWorker
        from hosts.hosts import HOSTS_EDIT_LOCK
        from hosts.state import HostsCommandResult
        owned = []
        worker = HostsAddressCheckWorker(1)
        self.addCleanup(worker.deleteLater)
        self.addCleanup(lambda: setattr(commands, '_OVERLAY_BEFORE_REFRESH', None))
        with (
            patch.object(commands, 'check_addresses', return_value=({}, EngineReport())) as check,
            patch('hosts.proxy_domains.get_engine_overlay', return_value={}),
            patch('hosts.proxy_domains.set_engine_overlay', side_effect=lambda _value: owned.append(HOSTS_EDIT_LOCK._is_owned())),
            patch.object(commands, 'refresh_applied_selection', side_effect=lambda: owned.append(HOSTS_EDIT_LOCK._is_owned()) or HostsCommandResult(True)),
            patch.object(commands, 'load_page_snapshot', return_value=None),
        ):
            worker.run()
        self.assertEqual(owned, [True, True])
        self.assertFalse(check.call_args.kwargs['commit'])

    def test_cancelled_check_does_not_probe_or_save(self):
        from hosts import commands
        with patch('hosts.address_probe.check_address') as probe, patch('hosts.proxy_domains.set_engine_overlay') as save:
            self.assertIsNone(commands.check_addresses(should_stop=lambda: True))
        probe.assert_not_called()
        save.assert_not_called()

    def test_manual_check_discards_the_living_address_cache(self):
        from hosts import commands
        commands._PROBE_CACHE[('1.1.1.1', 'example.com', '')] = (1, object())
        self.addCleanup(commands._PROBE_CACHE.clear)
        with patch.object(commands, '_check_addresses', return_value=None):
            commands.check_addresses(fresh=True)
        self.assertEqual(commands._PROBE_CACHE, {})
