import os
import unittest
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

            mock_add.assert_called_once_with(mock_mgr.return_value, "example.com", "93.184.216.34")
            self.assertFalse(page.add_to_hosts_btn.isEnabled())
            self.assertIn("Добавлено", page.add_to_hosts_btn.text())
            mock_info.assert_called_once()

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

            # Теперь кликаем по плитке и применяем обычные строки сервиса
            self.assertTrue(manager.apply_domain_ip_rows([("youtube.com", "9.8.7.6")]))
            lines = written_content["text"].splitlines(keepends=True)
            manual_rows = _managed_manual_rows(lines)
            self.assertEqual(manual_rows, [("custom.test", "1.2.3.4")])
            self.assertIn("youtube.com", written_content["text"])
            self.assertIn("custom.test", written_content["text"])
