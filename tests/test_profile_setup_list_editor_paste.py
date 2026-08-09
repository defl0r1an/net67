"""Регресс: вставка многострочного текста из буфера обмена в редакторы profile.

Исторический баг: снапшот текста редактора собирался инкрементальным патчингом
по QTextDocument.contentsChange. Qt учитывает финальный разделитель блока
документа в charsAdded/charsRemoved (вставка CRLF-списка в пустой редактор даёт
событие (0, 1, N+1) при N вставленных символах), из-за чего позиция конца
выделения выходила за последнюю валидную, QTextCursor.setPosition молча не
срабатывал и вставленный текст терялся из снапшота. Валидация ругалась на
фантомные строки («Строка 1: 80» при корректном 80.250.169.3), а автосейв мог
записать битый снапшот на диск.

Контракт после исправления: документ QPlainTextEdit — единственный источник
правды; текст для валидации и сохранения всегда равен toPlainText().
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QPlainTextEdit

from profile.list_file_editor import validate_profile_list_file_text
from profile.ui.profile_setup_page import ProfileSetupPageBase

IPSET_CRLF = (
    "80.250.169.3\r\n"
    "2606:4700::6811:cf05\r\n"
    "151.101.129.55\r\n"
    "2a02:26f0:d0::214:fe61\r\n"
)


def _paste(editor: QPlainTextEdit, clipboard_text: str) -> None:
    mime = QMimeData()
    mime.setText(clipboard_text)
    editor.insertFromMimeData(mime)


class ProfileListEditorPasteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _make_page(self, initial: str = "") -> tuple[ProfileSetupPageBase, QPlainTextEdit]:
        editor = QPlainTextEdit()
        editor.setPlainText(initial)
        page = ProfileSetupPageBase.__new__(ProfileSetupPageBase)
        page._list_file_text = editor
        page._list_file_text_snapshot = initial
        page._list_file_text_dirty = False
        # Как в проде: любое изменение текста инвалидирует мемо
        # (_on_list_file_text_changed выставляет _list_file_text_dirty).
        editor.textChanged.connect(
            lambda: setattr(page, "_list_file_text_dirty", True)
        )
        return page, editor

    def test_crlf_paste_into_empty_editor_validates_editor_text(self) -> None:
        page, editor = self._make_page("")
        _paste(editor, IPSET_CRLF)

        request = ProfileSetupPageBase._resolve_list_file_validation_request(
            page, {"kind": "ipset", "text": None}
        )

        self.assertEqual(request["text"], editor.toPlainText())
        self.assertEqual(validate_profile_list_file_text("ipset", request["text"]), ())

    def test_crlf_paste_over_selection_validates_editor_text(self) -> None:
        page, editor = self._make_page("1.2.3.4\n5.6.7.8\n")
        editor.selectAll()
        _paste(editor, IPSET_CRLF)

        request = ProfileSetupPageBase._resolve_list_file_validation_request(
            page, {"kind": "ipset", "text": None}
        )

        self.assertEqual(request["text"], editor.toPlainText())
        self.assertEqual(validate_profile_list_file_text("ipset", request["text"]), ())

    def test_paste_at_start_then_typing_validates_editor_text(self) -> None:
        # Исторически: после «потерянной» вставки последующий ручной ввод
        # патчил снапшот по смещённым позициям и разрезал первую строку
        # («Строка 1: 80»). Теперь любой сценарий обязан сойтись с редактором.
        page, editor = self._make_page("94.26.249.192")
        cursor = editor.textCursor()
        cursor.setPosition(0)
        editor.setTextCursor(cursor)
        _paste(editor, IPSET_CRLF)
        end = editor.textCursor()
        end.movePosition(QTextCursor.MoveOperation.End)
        end.insertText("\n139.100.194.145")

        request = ProfileSetupPageBase._resolve_list_file_validation_request(
            page, {"kind": "ipset", "text": None}
        )

        self.assertEqual(request["text"], editor.toPlainText())
        self.assertEqual(validate_profile_list_file_text("ipset", request["text"]), ())

    def test_unsaved_text_after_paste_matches_editor(self) -> None:
        # Автосейв обязан отправлять на диск ровно то, что видит пользователь.
        page, editor = self._make_page("")
        page._list_file_server_text_snapshot = ""
        _paste(editor, IPSET_CRLF)

        unsaved = ProfileSetupPageBase._unsaved_list_file_text(page)

        self.assertEqual(unsaved, editor.toPlainText())

    def test_raw_profile_text_after_paste_matches_editor(self) -> None:
        editor = QPlainTextEdit()
        editor.setPlainText("--old")
        page = ProfileSetupPageBase.__new__(ProfileSetupPageBase)
        page._raw_profile_text = editor
        page._raw_profile_text_cache = "--old"
        editor.textChanged.connect(
            lambda: ProfileSetupPageBase._on_raw_profile_text_changed(page)
        )
        editor.selectAll()
        _paste(editor, "--new\r\n--lua-desync=split\r\n")

        text = ProfileSetupPageBase._resolve_raw_profile_save_text(page, None)

        self.assertEqual(text, editor.toPlainText())


if __name__ == "__main__":
    unittest.main()
