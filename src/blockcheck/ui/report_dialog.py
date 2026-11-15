"""Окно с подробным техническим отчётом BlockCheck.

Отчёт открывается по кнопке, а не висит на странице: новичку он не нужен, а
поддержке — нужен целиком (адреса, ответы DNS, время ответа каждого сервера).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout
from qfluentwidgets import BodyLabel, PushButton

from ui.accessibility import set_control_accessibility
from ui.log_report_dialog import LogReportDialog


class BlockcheckReportDialog(LogReportDialog):
    """Показывает текст отчёта; «Скопировать» кладёт его в буфер обмена."""

    def __init__(self, text: str, parent=None, *, preset_action=None, open_profile=None) -> None:
        super().__init__(
            title="Подробный отчёт BlockCheck",
            text=text,
            empty_text="Проверка ещё не запускалась.",
            description="Технические подробности проверки: адреса, ответы DNS и время ответа серверов.",
            parent=parent,
        )
        if preset_action is not None and open_profile is not None:
            row = QHBoxLayout()
            label = BodyLabel(f"Профиль пресета: {preset_action['label']}", self)
            label.setWordWrap(True)
            button = PushButton("Открыть профиль", self)
            set_control_accessibility(button, name=f"Открыть профиль «{preset_action['label']}»")
            row.addWidget(label, 1, Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
            self.viewLayout.insertLayout(1, row)
            self._profile_button = button
            self._profile_label = label
            self._profile_action = preset_action["action"]
            self._open_profile = open_profile
            button.clicked.connect(self._open_report_profile)

    def _open_report_profile(self) -> None:
        if self._open_profile(self._profile_action):
            self.accept()
        else:
            self._profile_label.setText("Профиль уже нельзя открыть из этого отчёта. Повторите проверку.")
            self._profile_button.setEnabled(False)


def show_report_dialog(parent, text: str, *, preset_action=None, open_profile=None) -> None:
    BlockcheckReportDialog(text, parent, preset_action=preset_action, open_profile=open_profile).exec()
