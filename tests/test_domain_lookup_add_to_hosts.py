import os
import unittest
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from dns import domain_lookup as engine
from dns.ui.domain_lookup_page import DomainLookupPage


class DomainLookupAddToHostsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_add_to_hosts_button_is_visible_and_calls_manager(self) -> None:
        page = DomainLookupPage(parent=None, dns_feature=Mock())
        self.addCleanup(page.deleteLater)

        # Без отчета кнопка скрыта
        self.assertFalse(page.add_to_hosts_btn.isVisible())

        # Отчет с чистым IP для домена
        report = engine.DomainLookupReport(
            target="example.com",
            kind=engine.KIND_DOMAIN,
            primary_ip="93.184.216.34",
            answers=(),
            finished=True,
        )
        page._show_report(report)
        self.assertFalse(page.add_to_hosts_btn.isHidden())
        self.assertTrue(page.add_to_hosts_btn.isEnabled())


        # Нажатие кнопки вызывает add_domain_ip_entry
        fake_result = Mock(success=True)
        with patch("hosts.public.create_hosts_runtime", return_value=Mock()) as mock_mgr, \
             patch("hosts.public.add_domain_ip_entry", return_value=fake_result) as mock_add, \
             patch("ui.fluent_widgets.InfoBarHelper.success") as mock_info:
            page._on_add_to_hosts()
            deadline = time.monotonic() + 2
            while page._hosts_lane.is_busy() and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.005)
            QApplication.processEvents()

            mock_add.assert_called_once_with(mock_mgr.return_value, "example.com", "93.184.216.34")
            self.assertFalse(page.add_to_hosts_btn.isEnabled())
            self.assertIn("Добавлено", page.add_to_hosts_btn.text())
            mock_info.assert_called_once()

    def test_slow_hosts_write_does_not_block_window_or_write_twice(self) -> None:
        page = DomainLookupPage(parent=None, dns_feature=Mock())
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.cleanup)
        page._show_report(engine.DomainLookupReport(target="example.com", kind=engine.KIND_DOMAIN, primary_ip="1.2.3.4"))
        started, release = threading.Event(), threading.Event()
        calls = []
        gui_thread = threading.get_ident()

        def write(domain, ip):
            calls.append(threading.get_ident())
            started.set()
            release.wait(2)
            return Mock(success=True)

        with patch("app.feature_facades.hosts.add_domain_to_hosts", side_effect=write), \
             patch("ui.fluent_widgets.InfoBarHelper.success"):
            before = time.monotonic()
            page._on_add_to_hosts()
            page._on_add_to_hosts()
            self.assertLess(time.monotonic() - before, 0.2)
            self.assertTrue(started.wait(1))
            self.assertEqual(len(calls), 1)
            self.assertNotEqual(calls[0], gui_thread)
            release.set()
            deadline = time.monotonic() + 2
            while page._hosts_lane.is_busy() and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.005)

    def test_invalid_entry_cannot_add_extra_hosts_rows(self) -> None:
        from hosts.hosts import HostsManager

        manager = HostsManager()
        with patch("hosts.hosts.safe_write_hosts_file") as write:
            for domain, ip in (("example.com\nextra.test", "1.2.3.4"), ("example.com", "1.2.3.4\n5.6.7.8 extra.test")):
                self.assertFalse(manager.add_domain_ip_entry(domain, ip))
        write.assert_not_called()

    def test_manual_row_preserved_after_apply_domain_ip_rows(self) -> None:
        from hosts.hosts import HostsManager, _managed_manual_rows

        written_content = {}
        def fake_read():
            return written_content.get("text", "")
        def fake_write(text):
            written_content["text"] = text
            return True

        with patch("hosts.hosts.safe_read_hosts_file", side_effect=fake_read), \
             patch("hosts.hosts.safe_write_hosts_file", side_effect=fake_write), \
             patch.object(HostsManager, "is_hosts_file_accessible", return_value=True):
            manager = HostsManager()
            # Добавляем ручную запись через проверку домена
            self.assertTrue(manager.add_domain_ip_entry("custom.test", "1.2.3.4"))
            self.assertIn("custom.test", written_content["text"])
            self.assertIn("net67:manual", written_content["text"])
            self.assertTrue(manager.apply_domain_ip_rows([("youtube.com", "9.8.7.6")]))
            manual_rows = _managed_manual_rows(written_content["text"].splitlines(keepends=True))
            self.assertEqual(manual_rows, [("custom.test", "1.2.3.4")])
            self.assertIn("youtube.com", written_content["text"])

    def test_real_file_keeps_manual_row_and_unrelated_rows(self) -> None:
        from hosts import hosts

        with TemporaryDirectory() as directory:
            path = Path(directory) / "hosts"
            path.write_text("127.0.0.1 localhost\n9.8.7.6 unrelated.test\n", encoding="utf-8")
            with patch.object(hosts, "HOSTS_PATH", path), \
                 patch.object(hosts.HostsManager, "is_hosts_file_accessible", return_value=True), \
                 patch.object(hosts, "is_ipv6_available", return_value=True):
                manager = hosts.HostsManager()
                self.assertTrue(manager.add_domain_ip_entry("custom.test", "1.2.3.4"))
                self.assertTrue(manager.apply_domain_ip_rows([("youtube.com", "4.3.2.1")]))
                self.assertTrue(manager.apply_domain_ip_rows([]))
            content = path.read_text(encoding="utf-8-sig")
            self.assertIn("1.2.3.4 custom.test # net67:manual", content)
            self.assertIn("9.8.7.6 unrelated.test", content)
            self.assertNotIn("youtube.com", content)
