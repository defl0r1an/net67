import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

from ui.close_dialog import CloseDialog


# Имя приложения берётся из branding, а не вписано строкой. Этот тест
# уже один раз протух: в нём осталось прежнее «ZapretGUI», хотя всё
# приложение давно переименовано, и падал он не на ошибке, а на своей
# устарелости.
from branding import APP_NAME  # noqa: E402

class CloseDialogAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _parent(self) -> QWidget:
        parent = QWidget()
        parent.resize(640, 480)
        parent.show()
        self.addCleanup(parent.deleteLater)
        return parent

    def test_close_actions_are_named_for_screen_reader_when_dpi_is_running(self) -> None:
        dialog = CloseDialog(self._parent(), launch_running=True)
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.titleLabel.accessibleName(), "Диалог: Закрыть приложение")
        self.assertEqual(dialog.titleLabel.property("screenReaderStateText"), "Диалог: Закрыть приложение")
        self.assertEqual(dialog.bodyLabel.accessibleName(), "Описание закрытия: DPI запущен")
        self.assertEqual(dialog.bodyLabel.property("screenReaderStateText"), "Описание закрытия: DPI запущен")
        self.assertIn("продолжит работать", dialog.bodyLabel.accessibleDescription())
        self.assertEqual(dialog.trayButton.accessibleName(), f"Свернуть {APP_NAME} в трей")
        self.assertEqual(dialog.trayButton.property("screenReaderStateText"), f"Свернуть {APP_NAME} в трей")
        self.assertIn("оставляет окно доступным из трея", dialog.trayButton.accessibleDescription())
        self.assertEqual(dialog.guiOnlyButton.accessibleName(), f"Закрыть только окно {APP_NAME}")
        self.assertEqual(dialog.guiOnlyButton.property("screenReaderStateText"), f"Закрыть только окно {APP_NAME}")
        self.assertIn("DPI продолжит работать", dialog.guiOnlyButton.accessibleDescription())
        self.assertEqual(dialog.stopDpiButton.accessibleName(), f"Закрыть {APP_NAME} и остановить DPI")
        self.assertEqual(dialog.stopDpiButton.property("screenReaderStateText"), f"Закрыть {APP_NAME} и остановить DPI")
        self.assertIn("остановит DPI", dialog.stopDpiButton.accessibleDescription())
        self.assertEqual(dialog.cancelLinkButton.accessibleName(), f"Отменить закрытие {APP_NAME}")
        self.assertEqual(dialog.cancelLinkButton.property("screenReaderStateText"), f"Отменить закрытие {APP_NAME}")

    def test_unavailable_stop_action_has_text_state_for_screen_reader(self) -> None:
        dialog = CloseDialog(self._parent(), launch_running=False)
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.bodyLabel.accessibleName(), "Описание закрытия: DPI не запущен")
        self.assertEqual(dialog.bodyLabel.property("screenReaderStateText"), "Описание закрытия: DPI не запущен")
        self.assertEqual(dialog.trayButton.property("screenReaderStateText"), f"Свернуть {APP_NAME} в трей")
        self.assertEqual(dialog.guiOnlyButton.property("screenReaderStateText"), f"Закрыть только окно {APP_NAME}")
        self.assertFalse(dialog.stopDpiButton.isVisibleTo(dialog))
        self.assertEqual(dialog.cancelLinkButton.property("screenReaderStateText"), f"Отменить закрытие {APP_NAME}")


if __name__ == "__main__":
    unittest.main()
