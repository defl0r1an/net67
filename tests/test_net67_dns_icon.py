"""Значок профиля «net67 DNS»: цифры логотипа, серый по теме, приглушение не теряется."""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from hosts.ui import profile_icons
from profile.ui import profile_icon as icon_module


class Net67DnsIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_grey_depends_on_theme(self) -> None:
        with mock.patch.object(profile_icons, "_is_dark_theme", return_value=True):
            self.assertEqual(profile_icons.profile_icon("net67_dns", 6), ("img:net67:67", "#C9CDD3"))
        with mock.patch.object(profile_icons, "_is_dark_theme", return_value=False):
            self.assertEqual(profile_icons.profile_icon("net67_dns", 6), ("img:net67:67", "#8A9099"))

    def test_other_profiles_keep_their_colour(self) -> None:
        self.assertEqual(profile_icons.profile_icon("geohide", 0), ("fa5s.globe-europe", "#8B5CF6"))

    def test_mask_draws_digits_not_fallback_initials(self) -> None:
        pixmap = icon_module.profile_icon_pixmap("img:net67:67", color="#C9CDD3", size=18)
        image = pixmap.toImage()
        opaque = [
            image.pixelColor(x, y)
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 200
        ]
        self.assertTrue(opaque)
        # Цвет — из аргумента, а не кружок-заглушка с буквами.
        self.assertTrue(all(abs(c.red() - 0xC9) <= 2 for c in opaque))

    def test_muted_colour_keeps_its_transparency(self) -> None:
        muted = QColor(255, 255, 255, 110).name(QColor.NameFormat.HexArgb)
        self.assertEqual(icon_module._valid_hex_color(muted), muted)
        pixmap = icon_module.profile_icon_pixmap("img:net67:67", color=muted, size=18)
        image = pixmap.toImage()
        alphas = {image.pixelColor(x, y).alpha() for y in range(image.height()) for x in range(image.width())}
        # Раньше прозрачность терялась, и невыбранный значок горел сплошным белым.
        self.assertLessEqual(max(alphas), 111)


if __name__ == "__main__":
    unittest.main()
