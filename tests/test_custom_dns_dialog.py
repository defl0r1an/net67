from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget


class CustomDnsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_creates_one_custom_dns_entry(self) -> None:
        from dns.ui.custom_dns_dialog import CustomDnsDialog

        parent = QWidget()
        parent.resize(640, 480)
        dialog = CustomDnsDialog(parent)

        self.assertEqual(dialog.titleLabel.text(), "Добавить свой DNS")
        self.assertEqual(dialog.yesButton.text(), "Добавить")
        self.assertFalse(hasattr(dialog, "serversList"))
        self.assertFalse(hasattr(dialog, "ipv6PrimaryEdit"))

        dialog.nameEdit.setText("Мой DNS")
        dialog.primaryEdit.setText("8.8.8.8")
        dialog.secondaryEdit.setText("1.1.1.1")

        self.assertTrue(dialog.validate())
        self.assertEqual(dialog.server()["name"], "Мой DNS")
        self.assertEqual(dialog.server()["ipv4"], ["8.8.8.8", "1.1.1.1"])
        self.assertEqual(dialog.servers(), [dialog.server()])

    def test_dialog_creates_ipv6_dns_when_ipv6_is_available(self) -> None:
        from dns.ui.custom_dns_dialog import CustomDnsDialog

        parent = QWidget()
        parent.resize(640, 480)
        dialog = CustomDnsDialog(parent, ipv6_available=True)

        self.assertTrue(hasattr(dialog, "ipv6PrimaryEdit"))
        self.assertIn("IPv6", dialog.ipv6PrimaryEdit.placeholderText())

        dialog.nameEdit.setText("Мой IPv6 DNS")
        dialog.ipv6PrimaryEdit.setText("2001:4860:4860::8888")
        dialog.ipv6SecondaryEdit.setText("2001:4860:4860::8844")

        self.assertTrue(dialog.validate())
        self.assertEqual(dialog.server()["ipv4"], [])
        self.assertEqual(
            dialog.server()["ipv6"],
            ["2001:4860:4860::8888", "2001:4860:4860::8844"],
        )

    def test_dialog_rejects_invalid_ipv6_when_ipv6_is_available(self) -> None:
        from dns.ui.custom_dns_dialog import CustomDnsDialog

        parent = QWidget()
        parent.resize(640, 480)
        dialog = CustomDnsDialog(parent, ipv6_available=True)

        dialog.nameEdit.setText("Мой IPv6 DNS")
        dialog.ipv6PrimaryEdit.setText("bad")

        self.assertFalse(dialog.validate())
        self.assertIn("IPv6", dialog.warningLabel.text())

    def test_dialog_edits_one_existing_custom_dns_entry(self) -> None:
        from dns.ui.custom_dns_dialog import CustomDnsDialog

        parent = QWidget()
        parent.resize(640, 480)
        dialog = CustomDnsDialog(
            parent,
            server={"id": "cloudflare", "name": "Cloudflare", "ipv4": ["1.1.1.1"], "ipv6": []},
        )

        self.assertEqual(dialog.titleLabel.text(), "Редактировать свой DNS")
        self.assertEqual(dialog.yesButton.text(), "Сохранить")
        self.assertEqual(dialog.nameEdit.text(), "Cloudflare")
        self.assertEqual(dialog.primaryEdit.text(), "1.1.1.1")

        dialog.nameEdit.setText("Рабочий DNS")
        dialog.primaryEdit.setText("9.9.9.9")

        self.assertTrue(dialog.validate())
        self.assertEqual(dialog.server()["id"], "cloudflare")
        self.assertEqual(dialog.server()["name"], "Рабочий DNS")
        self.assertEqual(dialog.server()["ipv4"], ["9.9.9.9"])

    def test_dialog_edits_existing_ipv6_dns_even_when_ipv6_detection_is_late(self) -> None:
        from dns.ui.custom_dns_dialog import CustomDnsDialog

        parent = QWidget()
        parent.resize(640, 480)
        dialog = CustomDnsDialog(
            parent,
            server={
                "id": "v6",
                "name": "IPv6 DNS",
                "ipv4": [],
                "ipv6": ["2001:4860:4860::8888"],
            },
        )

        self.assertTrue(hasattr(dialog, "ipv6PrimaryEdit"))
        self.assertEqual(dialog.ipv6PrimaryEdit.text(), "2001:4860:4860::8888")

        dialog.ipv6PrimaryEdit.setText("2606:4700:4700::1111")

        self.assertTrue(dialog.validate())
        self.assertEqual(dialog.server()["ipv4"], [])
        self.assertEqual(dialog.server()["ipv6"], ["2606:4700:4700::1111"])


    def test_dialog_requires_name_and_primary_dns(self) -> None:
        from dns.ui.custom_dns_dialog import CustomDnsDialog

        parent = QWidget()
        parent.resize(640, 480)
        dialog = CustomDnsDialog(parent)

        self.assertFalse(dialog.validate())
        self.assertIn("название", dialog.warningLabel.text().lower())

        dialog.nameEdit.setText("Мой DNS")

        self.assertFalse(dialog.validate())
        self.assertIn("основной DNS", dialog.warningLabel.text())

    def test_dialog_rejects_invalid_ipv4_addresses(self) -> None:
        from dns.ui.custom_dns_dialog import CustomDnsDialog

        parent = QWidget()
        parent.resize(640, 480)
        dialog = CustomDnsDialog(parent)

        dialog.nameEdit.setText("Мой DNS")
        dialog.primaryEdit.setText("bad")

        self.assertFalse(dialog.validate())
        self.assertIn("IPv4", dialog.warningLabel.text())

        dialog.primaryEdit.setText("8.8.8.8")
        dialog.secondaryEdit.setText("bad")

        self.assertFalse(dialog.validate())
        self.assertIn("IPv4", dialog.warningLabel.text())


if __name__ == "__main__":
    unittest.main()
