"""Большая кнопка VPN и компактный выбор охвата."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel

from ui.accessibility import set_control_accessibility
from ui.fluent_widgets import set_tooltip
from ui.widgets.aligned_switch import AlignedSwitchButton
from vpn.ui.connect_button import VpnButtonState, VpnConnectButton


class LargeVpnButton(VpnConnectButton):
    def __init__(self, parent=None):
        self._custom_title = ""
        super().__init__(parent)

    def set_state(self, state):
        if state != self.state():
            self._custom_title = ""
        super().set_state(state)

    def title(self):
        if self._custom_title:
            return self._custom_title
        if self.state() is VpnButtonState.CONNECTING:
            return "Отменить"
        return super().title()

    def text(self):
        return self.title()

    def setText(self, text):  # noqa: N802
        self._custom_title = str(text)
        self.setAccessibleName(self.title())


class ScopeSelector(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(BodyLabel("Весь компьютер", self))
        self.switch = AlignedSwitchButton(self)
        self.switch.setOnText("")
        self.switch.setOffText("")
        self.switch.checkedChanged.connect(self.toggled.emit)
        layout.addWidget(self.switch)
        hint = "Выключено: прокси приложений Windows. Включено: туннель для всего компьютера, нужны права администратора."
        set_control_accessibility(self.switch, name="Весь компьютер", description=hint)
        self.setAccessibleName("Весь компьютер")
        set_tooltip(self, hint)

    def setChecked(self, enabled, block_signals=False):  # noqa: N802
        old = self.blockSignals(block_signals)
        self.switch.setChecked(bool(enabled))
        self.blockSignals(old)

    def isChecked(self):  # noqa: N802
        return self.switch.isChecked()
