from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget


class RawPresetTextEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        self.app.closeAllWindows()
        self.app.processEvents()

    def test_enter_finds_next_match_and_shift_enter_finds_previous_match(self) -> None:
        from presets.ui.common.raw_preset_text_editor import RawPresetTextEditor

        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        editor = RawPresetTextEditor(
            parent,
            request_save=lambda *, publish_content_changed=False: True,
            set_footer=lambda _text: None,
            cleanup_in_progress=lambda: False,
        )
        self.addCleanup(editor.cleanup)
        editor.apply_loaded_text("alpha\nbeta\nalpha\nbeta\nalpha\n")
        editor.search_input.setText("alpha")
        self.app.processEvents()

        first_cursor = editor.editor.textCursor()
        self.assertEqual(first_cursor.selectedText(), "alpha")
        self.assertEqual(first_cursor.selectionStart(), 0)

        QTest.keyClick(editor.search_input, Qt.Key.Key_Return)
        second_cursor = editor.editor.textCursor()
        self.assertEqual(second_cursor.selectedText(), "alpha")
        self.assertEqual(second_cursor.selectionStart(), len("alpha\nbeta\n"))

        QTest.keyClick(editor.search_input, Qt.Key.Key_Return)
        third_cursor = editor.editor.textCursor()
        self.assertEqual(third_cursor.selectedText(), "alpha")
        self.assertEqual(third_cursor.selectionStart(), len("alpha\nbeta\nalpha\nbeta\n"))

        QTest.keyClick(editor.search_input, Qt.Key.Key_Return)
        wrapped_cursor = editor.editor.textCursor()
        self.assertEqual(wrapped_cursor.selectedText(), "alpha")
        self.assertEqual(wrapped_cursor.selectionStart(), 0)

        QTest.keyClick(editor.search_input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        previous_cursor = editor.editor.textCursor()
        self.assertEqual(previous_cursor.selectedText(), "alpha")
        self.assertEqual(previous_cursor.selectionStart(), len("alpha\nbeta\nalpha\nbeta\n"))

    def test_external_text_update_is_not_applied_over_local_unsaved_changes(self) -> None:
        from presets.ui.common.raw_preset_text_editor import RawPresetTextEditor

        footer_messages: list[str] = []
        save_requests: list[bool] = []
        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        editor = RawPresetTextEditor(
            parent,
            request_save=lambda *, publish_content_changed=False: save_requests.append(
                bool(publish_content_changed)
            ) or True,
            set_footer=footer_messages.append,
            cleanup_in_progress=lambda: False,
        )
        self.addCleanup(editor.cleanup)
        editor.apply_loaded_text("--new\nold\n")
        editor.editor.setPlainText("--new\nlocal edit\n")
        self.app.processEvents()

        applied = editor.apply_external_text_update("--new\nexternal edit\n")

        self.assertFalse(applied)
        self.assertEqual(editor.current_text(), "--new\nlocal edit\n")
        self.assertEqual(editor.editor.toPlainText(), "--new\nlocal edit\n")
        self.assertIn("не перезаписаны", footer_messages[-1])
        self.assertEqual(save_requests, [])

    def test_multiline_clipboard_paste_is_not_lost_from_text_cache(self) -> None:
        from presets.ui.common.raw_preset_text_editor import RawPresetTextEditor

        # Регрессия: вставка CRLF-многострочного текста в пустой редактор даёт
        # contentsChange (0, 1, N+1) — Qt учитывает финальный разделитель блока,
        # и инкрементальный патчинг кэша молча терял вставленный текст.
        # Кэш обязан совпадать с документом при сохранении.
        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        editor = RawPresetTextEditor(
            parent,
            request_save=lambda *, publish_content_changed=False: True,
            set_footer=lambda _text: None,
            cleanup_in_progress=lambda: False,
        )
        self.addCleanup(editor.cleanup)
        editor.apply_loaded_text("")

        self.app.clipboard().setText("--new\r\n--filter-tcp=443\r\n--hostlist=list.txt")
        editor.editor.paste()
        self.app.processEvents()

        document_text = editor.editor.toPlainText()
        self.assertEqual(document_text, "--new\n--filter-tcp=443\n--hostlist=list.txt")
        self.assertEqual(editor.current_text(), document_text)
        self.assertEqual(editor.resolve_save_text(None), document_text)

    def test_paste_over_selection_keeps_cache_in_sync_with_document(self) -> None:
        from presets.ui.common.raw_preset_text_editor import RawPresetTextEditor

        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        editor = RawPresetTextEditor(
            parent,
            request_save=lambda *, publish_content_changed=False: True,
            set_footer=lambda _text: None,
            cleanup_in_progress=lambda: False,
        )
        self.addCleanup(editor.cleanup)
        editor.apply_loaded_text("--old\n--filter-tcp=80\n")
        # Прогреваем мемо, чтобы поймать именно рассинхрон после вставки.
        self.assertEqual(editor.current_text(), "--old\n--filter-tcp=80\n")

        editor.editor.selectAll()
        self.app.clipboard().setText("--new\r\n--filter-tcp=443\r\n")
        editor.editor.paste()
        self.app.processEvents()

        document_text = editor.editor.toPlainText()
        self.assertEqual(document_text, "--new\n--filter-tcp=443\n")
        self.assertEqual(editor.current_text(), document_text)
        self.assertEqual(editor.resolve_save_text(None), document_text)


if __name__ == "__main__":
    unittest.main()
