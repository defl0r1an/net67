from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

from presets.ui.zapret2.preset_dialogs import PresetNameDialog


class Zapret2PresetDialogAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _parent(self) -> QWidget:
        parent = QWidget()
        parent.resize(640, 480)
        parent.show()
        self.addCleanup(parent.deleteLater)
        return parent

    def test_create_dialog_has_screen_reader_text(self) -> None:
        dialog = PresetNameDialog("create", parent=self._parent())
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.titleLabel.accessibleName(), "Диалог: Создать пресет")
        self.assertIn("создания preset", dialog.titleLabel.accessibleDescription())
        self.assertEqual(dialog.name_edit.accessibleName(), "Название нового preset")
        self.assertIn("Введите название", dialog.name_edit.accessibleDescription())
        self.assertEqual(dialog.yesButton.accessibleName(), "Создать preset")
        self.assertEqual(dialog.yesButton.property("screenReaderStateText"), "Создать preset")
        self.assertIn("Создаёт новый preset", dialog.yesButton.accessibleDescription())
        self.assertEqual(dialog.cancelButton.accessibleName(), "Отменить создание preset")
        self.assertEqual(dialog.cancelButton.property("screenReaderStateText"), "Отменить создание preset")

        self.assertFalse(dialog.validate())

        self.assertEqual(dialog._error_label.accessibleName(), "Ошибка: Введите название пресета")
        self.assertEqual(
            dialog._error_label.property("screenReaderStateText"),
            "Ошибка: Введите название пресета",
        )

    def test_rename_dialog_has_screen_reader_text(self) -> None:
        dialog = PresetNameDialog("rename", old_name="Дом", parent=self._parent())
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.titleLabel.accessibleName(), "Диалог: Переименовать пресет")
        self.assertIn("переименования preset", dialog.titleLabel.accessibleDescription())
        self.assertEqual(dialog.current_name_label.accessibleName(), "Текущее имя preset: Дом")
        self.assertIn("старое имя", dialog.current_name_label.accessibleDescription())
        self.assertEqual(dialog.name_edit.accessibleName(), "Новое название preset")
        self.assertIn("Текущее имя: Дом", dialog.name_edit.accessibleDescription())
        self.assertEqual(dialog.yesButton.accessibleName(), "Переименовать preset")
        self.assertEqual(dialog.yesButton.property("screenReaderStateText"), "Переименовать preset")
        self.assertIn("Меняет имя preset", dialog.yesButton.accessibleDescription())
        self.assertEqual(dialog.cancelButton.accessibleName(), "Отменить переименование preset")
        self.assertEqual(dialog.cancelButton.property("screenReaderStateText"), "Отменить переименование preset")


if __name__ == "__main__":
    unittest.main()
