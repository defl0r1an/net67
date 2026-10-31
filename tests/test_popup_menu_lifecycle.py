import unittest
from unittest.mock import patch

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QPoint, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

from ui.popup_menu import PopupMenuLifecycleFilter, exec_popup_menu


class _InstantMenu(QWidget):
    """Меню, которое закрывается сразу после показа."""

    def exec(self, _pos) -> None:  # noqa: A003 (Qt API)
        return None


class PopupMenuLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_menu_is_deleted_after_it_closes(self) -> None:
        owner = QWidget()
        menu = _InstantMenu(owner)

        with patch.object(menu, "deleteLater") as delete_later:
            exec_popup_menu(menu, QPoint(0, 0), owner=owner)

        delete_later.assert_called_once_with()
        owner.deleteLater()

    def test_reused_menu_keeps_actions_without_accumulating_callbacks(self) -> None:
        from qfluentwidgets import Action

        owner = QWidget()
        self.addCleanup(owner.deleteLater)
        menu = _InstantMenu(owner)
        action = Action("Показать", menu)
        menu.addAction(action)
        calls = []
        action.triggered.connect(lambda: calls.append(True))
        receiver_count = action.receivers(action.triggered)

        with patch.object(menu, "exec", side_effect=lambda _pos: action.trigger()):
            for _ in range(10):
                chosen = exec_popup_menu(menu, QPoint(0, 0), owner=owner,
                                         capture_action=True, delete_on_close=False)
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.assertFalse(sip.isdeleted(menu))
                self.assertFalse(sip.isdeleted(action))
                self.assertIs(chosen, action)
                self.assertEqual(action.receivers(action.triggered), receiver_count)
                self.assertEqual(menu.findChildren(PopupMenuLifecycleFilter), [])
                self.assertEqual(menu.findChildren(QEventLoop), [])
                self.assertEqual(menu.findChildren(QTimer), [])
        self.assertEqual(len(calls), 10)


if __name__ == "__main__":
    unittest.main()
