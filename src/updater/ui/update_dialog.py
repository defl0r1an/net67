"""Окно «Доступно обновление» и окно «Что нового».

Об обновлении спрашивало окошко в одну строку: «Выпущена версия X.
Установить?». Что в ней нового, сколько версий человек пропустил и
откуда она взялась, узнать было негде, а отказаться можно было только
«до следующего запуска».

- ``UpdateOfferDialog`` — предложение обновиться: вкладка «Что нового»
  (изменения всех пропущенных версий и пара предыдущих), вкладка
  «Подробности», кнопки «Обновить», «Позже», «Пропустить версию» и
  «Открыть в браузере».
- ``WhatsNewDialog`` — только почитать: показывается один раз после
  установки новой версии.

Окна ничего не скачивают и не сохраняют: только показывают и говорят,
что нажали. Что делать дальше, решает тот, кто их открыл.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    PrimaryPushButton,
    PushButton,
    SegmentedWidget,
    SubtitleLabel,
    TextBrowser,
    TransparentPushButton,
)

from ui.accessibility import set_control_accessibility, set_state_text
from ui.fluent_dialog import MessageBoxBase
from ui.segmented_accessibility import set_segmented_items_accessibility
from ui.theme import get_theme_tokens
from ui.theme_refresh import ThemeRefreshBinding
from ui.widgets.fun import Mascot
from ui.widgets.fun.mascot import MOOD_HAPPY, MOOD_IDLE
from updater import release_notes

RESULT_INSTALL = "install"
RESULT_LATER = "later"
RESULT_SKIP = "skip"

_LOGO_SIZE = 44
_MIN_WIDTH = 640
_MAX_WIDTH = 1080
_MIN_TEXT_HEIGHT = 240
_MAX_TEXT_HEIGHT = 600


def _text_area_size(parent) -> tuple[int, int]:
    """Окно занимает большую часть окна программы, но в разумных пределах."""
    try:
        window = parent.window() if parent is not None else None
        host_width = int(window.width()) if window is not None else 0
        host_height = int(window.height()) if window is not None else 0
    except Exception:
        host_width = host_height = 0
    width = max(_MIN_WIDTH, min(_MAX_WIDTH, int(host_width * 0.72)))
    # Высота — для текста: шапка и кнопки добавляются сверху.
    height = max(_MIN_TEXT_HEIGHT, min(_MAX_TEXT_HEIGHT, int(host_height * 0.78) - 260))
    return width, height


class _ReleaseDialogBase(MessageBoxBase):
    """Шапка со значком, поле с текстом выпусков и ряд своих кнопок."""

    link_clicked = pyqtSignal(str)

    def __init__(self, parent) -> None:
        if parent is not None and not parent.isWindow():
            parent = parent.window()
        super().__init__(parent)
        self._history: tuple = ()
        self.setClosableOnMaskClicked(False)

        # Стандартные «ОК/Отмена» не нужны: у окна свой ряд кнопок.
        self.yesButton.hide()
        self.cancelButton.hide()
        self.buttonLayout.removeWidget(self.yesButton)
        self.buttonLayout.removeWidget(self.cancelButton)

        header = QHBoxLayout()
        header.setSpacing(14)
        self.mascot = Mascot(self.widget, size=_LOGO_SIZE)
        header.addWidget(self.mascot, 0, Qt.AlignmentFlag.AlignTop)
        # Виджет значка выше самого значка: над ним запас на прыжок. Текст
        # начинается с того же запаса и держится по центру высоты значка —
        # так заголовок стоит вровень с логотипом на любом масштабе.
        titles_column = QVBoxLayout()
        titles_column.setContentsMargins(0, 0, 0, 0)
        titles_column.setSpacing(0)
        titles_column.addSpacing(self.mascot.headroom())
        self.titles_box = QWidget(self.widget)
        # Без этого контейнер получает фон от стиля окна и лежит под
        # заголовком тёмной плашкой.
        self.titles_box.setObjectName("updateDialogTitles")
        self.titles_box.setStyleSheet("QWidget#updateDialogTitles { background: transparent; }")
        self.titles_box.setMinimumHeight(self.mascot.side())
        titles = QVBoxLayout(self.titles_box)
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(2)
        titles.addStretch(1)
        self.title_label = SubtitleLabel("", self.titles_box)
        self.title_label.setWordWrap(True)
        titles.addWidget(self.title_label)
        self.subtitle_label = CaptionLabel("", self.titles_box)
        self.subtitle_label.setWordWrap(True)
        titles.addWidget(self.subtitle_label)
        titles.addStretch(1)
        titles_column.addWidget(self.titles_box)
        titles_column.addStretch(1)
        header.addLayout(titles_column, 1)
        self.viewLayout.addLayout(header)

        self.browser = TextBrowser(self.widget)
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(lambda url: self.link_clicked.emit(url.toString()))
        width, height = _text_area_size(parent)
        self.widget.setMinimumWidth(width)
        self.browser.setMinimumHeight(height)
        set_control_accessibility(
            self.browser,
            name="Список изменений",
            description="Что изменилось в каждой версии, от новой к старой. Ссылки открываются в браузере.",
        )

        self._buttons_left = QHBoxLayout()
        self._buttons_left.setSpacing(6)
        self._buttons_right = QHBoxLayout()
        self._buttons_right.setSpacing(10)
        self.buttonLayout.addLayout(self._buttons_left)
        self.buttonLayout.addStretch(1)
        self.buttonLayout.addLayout(self._buttons_right)

        self._theme_refresh = ThemeRefreshBinding(self, self._apply_theme_refresh)

    def _make_button(self, cls, text: str, *, icon=None, description: str, on_click, name: str = ""):
        button = cls(text, self.buttonGroup) if icon is None else cls(icon, text, self.buttonGroup)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        set_control_accessibility(button, name=name or text, description=description)
        button.clicked.connect(on_click)
        return button

    def set_history(self, history) -> None:
        self._history = tuple(item for item in history or () if isinstance(item, dict))
        self._render_history()

    def _render_history(self) -> None:
        tokens = get_theme_tokens()
        self.browser.setHtml(
            release_notes.history_html(self._history, accent_hex=tokens.accent_hex, muted_hex=tokens.fg_muted)
        )
        plain = " ".join(
            f"Версия {item.get('version', '')}: {' '.join(str(item.get('notes') or '').split())}" for item in self._history
        )
        set_state_text(self.browser, plain or "Описание изменений не опубликовано.")

    def _apply_theme_refresh(self, tokens=None, force: bool = False) -> None:
        _ = (tokens, force)
        self._render_history()


class UpdateOfferDialog(_ReleaseDialogBase):
    """Предложение обновиться. После закрытия ответ лежит в ``result_action``."""

    def __init__(
        self,
        parent,
        *,
        current_version: str,
        target_version: str,
        history=(),
        source: str = "",
        release_url: str = "",
        file_name: str = "",
        file_size: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.result_action = RESULT_LATER
        self._current = str(current_version or "")
        self._target = str(target_version or "")
        self._source = str(source or "")
        self._release_url = str(release_url or "")
        self._file_name = str(file_name or "")
        self._file_size = int(file_size or 0)

        self.title_label.setText("Доступно обновление")

        self.tabs = SegmentedWidget(self.widget)
        self.tabs.addItem(routeKey="changes", text=" Что нового", onClick=lambda: self.stack.setCurrentIndex(0))
        self.tabs.addItem(routeKey="details", text=" Подробности", onClick=lambda: self.stack.setCurrentIndex(1))
        self.tabs.setCurrentItem("changes")
        set_segmented_items_accessibility(
            self.tabs,
            name="Разделы окна обновления",
            labels={"changes": "Что нового", "details": "Подробности"},
        )
        self.viewLayout.addWidget(self.tabs, 0, Qt.AlignmentFlag.AlignLeft)

        self.stack = QStackedWidget(self.widget)
        self.stack.addWidget(self.browser)
        self.details_widget = QWidget(self.widget)
        self.details_widget.setObjectName("updateDialogDetails")
        self.details_widget.setStyleSheet("QWidget#updateDialogDetails { background: transparent; }")
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(4, 8, 4, 8)
        details_layout.setSpacing(10)
        self.details_label = BodyLabel("", self.details_widget)
        self.details_label.setWordWrap(True)
        self.details_label.setTextFormat(Qt.TextFormat.RichText)
        details_layout.addWidget(self.details_label)
        details_layout.addStretch(1)
        self.stack.addWidget(self.details_widget)
        self.viewLayout.addWidget(self.stack, 1)

        self.browser_btn = self._make_button(
            TransparentPushButton,
            "Открыть в браузере",
            icon=FluentIcon.GLOBE,
            description="Открывает страницу этого выпуска на GitHub.",
            on_click=self._on_browser,
        )
        self.browser_btn.setVisible(bool(self._release_url))
        self._buttons_left.addWidget(self.browser_btn)

        self.skip_btn = self._make_button(
            PushButton,
            "Пропустить версию",
            description="При запуске больше не напоминать об этой версии. Следующая версия снова покажет окно.",
            on_click=lambda: self._finish(RESULT_SKIP),
        )
        self.later_btn = self._make_button(
            PushButton,
            "Позже",
            name="Отложить обновление",
            description="Закрывает окно. Обновление напомнит о себе при следующем запуске.",
            on_click=lambda: self._finish(RESULT_LATER),
        )
        self.install_btn = self._make_button(
            PrimaryPushButton,
            "Обновить",
            icon=FluentIcon.DOWNLOAD,
            name="Скачать и установить обновление",
            description="Скачивает новую версию и запускает установщик. Программа закроется и откроется снова.",
            on_click=lambda: self._finish(RESULT_INSTALL),
        )
        for button in (self.skip_btn, self.later_btn, self.install_btn):
            self._buttons_right.addWidget(button)

        self.set_history(history)
        self._render_header()
        self._render_details()
        # Фокус — на главной кнопке, а не на поле текста: Enter обновляет.
        self.install_btn.setFocus()

    def _finish(self, action: str) -> None:
        self.result_action = action
        if action == RESULT_INSTALL:
            self.accept()
        else:
            self.reject()

    def _on_browser(self) -> None:
        if self._release_url:
            self.link_clicked.emit(self._release_url)

    def _render_header(self) -> None:
        parts = [f"v{self._current}  →  v{self._target}"]
        count = release_notes.count_new_versions(self._history)
        if count > 1:
            parts.append(f"версий в обновлении: {count}")
        if self._source:
            parts.append(f"источник: {self._source}")
        subtitle = "   ·   ".join(parts)
        self.subtitle_label.setText(subtitle)
        set_control_accessibility(
            self.widget,
            name="Доступно обновление",
            description="Окно обновления: список изменений, подробности и кнопки установки.",
        )
        set_state_text(self.widget, f"Доступно обновление. {subtitle}")

    def _render_details(self) -> None:
        rows = [
            ("Установлена", f"v{self._current}"),
            ("Новая версия", f"v{self._target}"),
            ("Источник", self._source or "—"),
            ("Версий в обновлении", str(max(release_notes.count_new_versions(self._history), 1))),
        ]
        if self._file_name:
            rows.append(("Файл", self._file_name))
        if self._file_size > 0:
            rows.append(("Размер", f"{self._file_size / (1024 * 1024):.1f} МБ"))
        muted = get_theme_tokens().fg_muted
        self.details_label.setText(
            "".join(
                f"<p style='margin: 0 0 8px 0;'><span style='color: {muted};'>{name}:</span>&nbsp; <b>{value}</b></p>"
                for name, value in rows
            )
        )
        set_state_text(self.details_label, "; ".join(f"{name}: {value}" for name, value in rows))

    def _apply_theme_refresh(self, tokens=None, force: bool = False) -> None:
        super()._apply_theme_refresh(tokens, force)
        self._render_details()


class WhatsNewDialog(_ReleaseDialogBase):
    """«Что нового» в установленной версии: только почитать."""

    def __init__(self, parent, *, version: str, history=()) -> None:
        super().__init__(parent)
        self._version = str(version or "")
        self.title_label.setText(f"Что нового в v{self._version}")
        self.viewLayout.addWidget(self.browser, 1)
        self.mascot.set_mood(MOOD_HAPPY)

        self._url = ""
        self.browser_btn = self._make_button(
            TransparentPushButton,
            "Открыть в браузере",
            icon=FluentIcon.GLOBE,
            description="Открывает страницу этого выпуска на GitHub.",
            on_click=lambda: self._url and self.link_clicked.emit(self._url),
        )
        self._buttons_left.addWidget(self.browser_btn)
        self.ok_btn = self._make_button(
            PrimaryPushButton,
            "Понятно",
            icon=FluentIcon.ACCEPT,
            name="Закрыть «Что нового»",
            description="Закрывает окно со списком изменений.",
            on_click=self.accept,
        )
        self._buttons_right.addWidget(self.ok_btn)
        self.set_history(history)
        self.ok_btn.setFocus()

    def set_history(self, history) -> None:
        super().set_history(history)
        count = release_notes.count_new_versions(self._history)
        self.subtitle_label.setText(
            f"Изменения за {count} {release_notes.versions_word(count)}" if count > 1 else "Список изменений этого выпуска"
        )
        self._url = next((str(item.get("url") or "") for item in self._history if item.get("url")), "")
        self.browser_btn.setVisible(bool(self._url))


def open_url_in_background(url: str) -> None:
    """Ссылка из окна открывается в фоне: запуск браузера не держит интерфейс."""
    import threading

    from log.log import log

    def run() -> None:
        try:
            from app.external_actions import open_url

            result = open_url(str(url or ""))
            if not getattr(result, "ok", True):
                log(f"Не удалось открыть ссылку {url}: {getattr(result, 'error', '')}", "WARNING")
        except Exception as exc:
            log(f"Не удалось открыть ссылку {url}: {exc}", "WARNING")

    threading.Thread(target=run, name="update-dialog-open-url", daemon=True).start()


def ask_update(parent, **kwargs) -> str:
    """Показывает предложение обновиться и возвращает, что выбрал человек."""
    dialog = UpdateOfferDialog(parent, **kwargs)
    dialog.link_clicked.connect(open_url_in_background)
    dialog.mascot.set_mood(MOOD_IDLE)
    dialog.exec()
    action = dialog.result_action
    dialog.deleteLater()
    return action


def show_whats_new(parent, *, version: str, history=()) -> WhatsNewDialog:
    """Открывает «Что нового» поверх окна программы и возвращает окно."""
    dialog = WhatsNewDialog(parent, version=version, history=history)
    dialog.link_clicked.connect(open_url_in_background)
    dialog.finished.connect(lambda _code: dialog.deleteLater())
    dialog.open()
    return dialog


__all__ = [
    "RESULT_INSTALL",
    "RESULT_LATER",
    "RESULT_SKIP",
    "UpdateOfferDialog",
    "WhatsNewDialog",
    "ask_update",
    "open_url_in_background",
    "show_whats_new",
]
