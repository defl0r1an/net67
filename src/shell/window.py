"""Оболочка net67, написанная с нуля.

Своё окно: свой заголовок, своя навигация, свои полосы прокрутки. Прежняя
оболочка была окном qfluentwidgets, и правки поверх неё давали «почти как
было» — часть чужого оформления пролезала обратно при каждой перерисовке.

Что здесь принципиально.

Окно без системной рамки. Иначе поверх графитового заголовка остаётся
светлая полоса Windows, и приложение выглядит собранным из двух половин.
За перетаскивание и изменение размера отвечаем сами.

Навигация — обычные кнопки в вертикальной рейке. Ни один виджет здесь не
наследуется от чужой библиотеки: цвет, отступы и выделение заданы в
theme.py и меняются в одном месте.

Страницы кладутся в QStackedWidget как есть. Переписывать сорок готовых
страниц ради оболочки бессмысленно: они получают новую палитру и новые
полосы прокрутки, оставаясь рабочими.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from qframelesswindow import TitleBar as FramelessTitleBar

from shell.theme import (
    RAIL_ITEM_GAP,
    RAIL_PADDING_BOTTOM,
    RAIL_PADDING_TOP,
    RAIL_WIDTH,
    palette,
    shell_qss,
)
from ui.accessibility import enable_keyboard_click, set_control_accessibility


#: Высота своей полосы заголовка.
TITLE_BAR_HEIGHT = 38

#: Размер кнопок управления окном.
WINDOW_BUTTON_SIZE = 30


@dataclass(frozen=True, slots=True)
class NavEntry:
    """Пункт навигации."""

    key: str
    title: str
    #: Раздел-заголовок над пунктом. Пустая строка — без заголовка.
    group: str = ""
    #: Виден ли пункт в простом режиме.
    simple: bool = False


class TitleBar(FramelessTitleBar):
    """Своя полоса заголовка поверх нативной безрамочной.

    Наследуемся от полосы qframelesswindow, а не пишем свою на QWidget.
    Перетаскивание окна, двойной клик и подгонка под развёрнутое
    состояние там уже сделаны нативными сообщениями Windows — своя
    реализация поверх этого приводила к падению приложения с access
    violation прямо в show().

    Оставляем только вид: имя слева, три свои кнопки справа.
    """

    minimizeRequested = pyqtSignal()
    maximizeRequested = pyqtSignal()
    closeRequested = pyqtSignal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("net67TitleBar")
        self.setFixedHeight(TITLE_BAR_HEIGHT)

        # Кнопки библиотеки убираем с глаз, но оставляем в живых.
        #
        # Три попытки, две неверные — записываю, чтобы не повторить.
        #
        # setParent(None) не «убирает виджет», а делает его окном
        # верхнего уровня со своей рамкой от Windows. Замер при запуске
        # показывал четыре окна вместо одного: наше и три кнопки по
        # 46x32 — спрятанные, но живые, и при старте они успевали
        # мигнуть на экране чужим окошком.
        #
        # deleteLater убрал мигание, но сломал окно: библиотека сама
        # обращается к maxBtn при каждой смене состояния окна, и после
        # удаления это падало прямо в обработчике события —
        #
        #     RuntimeError: wrapped C/C++ object of type MaximizeButton
        #     has been deleted
        #
        # Верное решение простое: спрятать и вынуть из раскладки. Тогда
        # кнопки не видны, не занимают места и не становятся окнами, а
        # библиотека продолжает их находить.
        for name in ("minBtn", "maxBtn", "closeBtn"):
            button = getattr(self, name, None)
            if button is None:
                continue
            layout = getattr(self, "hBoxLayout", None)
            if layout is not None:
                layout.removeWidget(button)
            button.hide()
            button.setFixedSize(0, 0)

        # Берём раскладку библиотеки, а не заводим свою: у TitleBar она
        # уже есть, вторая вызывает предупреждение Qt и не применяется.
        # На неё же смотрит refresh_titlebar_layout при показе окна.
        layout = self.hBoxLayout
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(8)

        # Название с версией стоит первым и никуда не уезжает.
        #
        # Раньше оно всплывало к середине: строку поиска убрали, а она
        # держала раскладку — за ней шла растяжка, и без неё название
        # оставалось между двумя пустотами. Вставляем по индексу 0 и
        # прижимаем влево явно, чтобы следующий виджет в заголовке не
        # сдвинул его снова.
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("net67Title")
        layout.insertWidget(0, self.title_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)

        # Кнопки окна живут в отдельном контейнере, а не лежат в общей
        # раскладке по одной. Причина не в красоте: строку поиска
        # приложение вставляет в эту же раскладку по индексу
        # `count() - 1`, то есть предпоследним, и следом добавляет
        # растяжку. С тремя отдельными кнопками поиск оказывался между
        # «развернуть» и «закрыть», а растяжка их растаскивала — свернуть
        # и развернуть уезжали в середину полосы, закрыть оставалась
        # справа. Ровно это и было видно на экране.
        #
        # Контейнер — один элемент раскладки, вставить что-то внутрь него
        # снаружи нельзя, и тройка кнопок остаётся неразрывной.
        self.buttons_host = QWidget(self)
        self.buttons_host.setObjectName("net67WindowButtons")
        buttons_row = QHBoxLayout(self.buttons_host)
        buttons_row.setContentsMargins(0, 0, 0, 0)
        buttons_row.setSpacing(0)

        # Кнопки окна рисуются символом, а не текстом, поэтому имя для
        # программ экранного доступа приходится задавать явно: «–» они
        # прочитают как «тире», а не как «свернуть».
        self.window_buttons: list[QPushButton] = []
        for object_name, glyph, caption, signal in (
            ("net67WindowButton", "–", "Свернуть окно", self.minimizeRequested),
            ("net67WindowButton", "□", "Развернуть окно", self.maximizeRequested),
            ("net67CloseButton", "✕", "Закрыть окно", self.closeRequested),
        ):
            button = QPushButton(glyph, self.buttons_host)
            button.setObjectName(object_name)
            button.setFixedSize(WINDOW_BUTTON_SIZE + 12, TITLE_BAR_HEIGHT)
            button.setCursor(Qt.CursorShape.ArrowCursor)
            button.clicked.connect(signal.emit)
            set_control_accessibility(button, name=caption, description=caption)
            enable_keyboard_click(button)
            buttons_row.addWidget(button)
            self.window_buttons.append(button)

        self.buttons_host.setFixedSize(
            (WINDOW_BUTTON_SIZE + 12) * len(self.window_buttons), TITLE_BAR_HEIGHT
        )
        layout.addWidget(self.buttons_host)


class NavigationRail(QWidget):
    """Вертикальная навигация. Свои кнопки, без чужих виджетов."""

    selected = pyqtSignal(str)

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.setObjectName("net67Rail")
        self.setFixedWidth(RAIL_WIDTH)

        self._buttons: dict[str, QPushButton] = {}
        self._group_labels: dict[str, QLabel] = {}
        self._entries = tuple(entries)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        # Отступы и промежуток — как в боковой панели Nora: pt-4 pb-2
        # и gap-1 между пунктами.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, RAIL_PADDING_TOP, 0, RAIL_PADDING_BOTTOM)
        layout.setSpacing(RAIL_ITEM_GAP)

        seen_groups: set[str] = set()
        for entry in self._entries:
            if entry.group and entry.group not in seen_groups:
                seen_groups.add(entry.group)
                label = QLabel(entry.group)
                label.setObjectName("net67SectionLabel")
                label.setContentsMargins(26, 14, 26, 2)
                layout.addWidget(label)
                self._group_labels[entry.group] = label

            button = QPushButton(entry.title)
            button.setObjectName("net67NavItem")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, key=entry.key: self.selected.emit(key))
            set_control_accessibility(
                button,
                name=entry.title,
                description=f"Открыть раздел «{entry.title}»",
            )
            enable_keyboard_click(button)
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[entry.key] = button

        layout.addStretch(1)

    def set_current(self, key: str) -> None:
        button = self._buttons.get(str(key))
        if button is not None:
            button.setChecked(True)
            # Состояние словами: по одной подсветке слева программа
            # экранного доступа не поймёт, какой раздел открыт.
            for key_name, item in self._buttons.items():
                entry_title = item.text()
                state = "открыт" if item is button else "не открыт"
                set_control_accessibility(
                    item,
                    name=entry_title,
                    description=f"Раздел «{entry_title}», {state}",
                )

    def apply_mode(self, *, advanced: bool) -> None:
        """Прячет расширенные пункты в простом режиме.

        Заголовок раздела прячется вместе с его пунктами: иначе над
        пустотой повисает подпись, и человек думает, что раздел сломан.
        """
        visible_groups: set[str] = set()
        for entry in self._entries:
            button = self._buttons.get(entry.key)
            if button is None:
                continue
            visible = advanced or entry.simple
            button.setVisible(visible)
            if visible and entry.group:
                visible_groups.add(entry.group)
        for group, label in self._group_labels.items():
            label.setVisible(group in visible_groups)


class ShellWindow(QWidget):
    """Главное окно: заголовок, навигация, стопка страниц."""

    def __init__(self, *, title: str, entries, dark: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("net67Window")
        self.setWindowTitle(title)
        # Без системной рамки: иначе поверх графитового заголовка
        # остаётся светлая полоса Windows.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        self._dark = bool(dark)
        self._entries = tuple(entries)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.title_bar = TitleBar(title, self)
        self.title_bar.minimizeRequested.connect(self.showMinimized)
        self.title_bar.maximizeRequested.connect(self._toggle_maximized)
        self.title_bar.closeRequested.connect(self.close)
        root.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.rail = NavigationRail(self._entries, self)
        self.rail.selected.connect(self.show_page)
        body.addWidget(self.rail)

        self.content = QStackedWidget(self)
        self.content.setObjectName("net67Content")
        body.addWidget(self.content, 1)

        root.addLayout(body, 1)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 2, 2)
        grip_row.addStretch(1)
        grip_row.addWidget(QSizeGrip(self), 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(grip_row)

        self._pages: dict[str, QWidget] = {}
        self.apply_theme(dark=self._dark)

    # ──────────────────────────────────────────────────────────────────

    def apply_theme(self, *, dark: bool) -> None:
        self._dark = bool(dark)
        self.setStyleSheet(shell_qss(palette(self._dark)))

    def add_page(self, key: str, widget: QWidget) -> None:
        self._pages[str(key)] = widget
        self.content.addWidget(widget)

    def show_page(self, key: str) -> None:
        widget = self._pages.get(str(key))
        if widget is not None:
            self.content.setCurrentWidget(widget)
            self.rail.set_current(key)

    def set_advanced(self, advanced: bool) -> None:
        self.rail.apply_mode(advanced=bool(advanced))

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()


__all__ = [
    "TITLE_BAR_HEIGHT",
    "WINDOW_BUTTON_SIZE",
    "NavEntry",
    "NavigationRail",
    "ShellWindow",
    "TitleBar",
]
