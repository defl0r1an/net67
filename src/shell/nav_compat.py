"""Навигация новой оболочки с прежним программным интерфейсом.

Страниц в приложении сорок, и их список собирает `ui/navigation/`. Тот
код зовёт методы боковой панели qfluentwidgets: addItem, insertItem,
addItemHeader, setCurrentItem. Переписывать сборщик навигации ради смены
облика значило бы трогать маршрутизацию, поиск и режимы — то есть
ломать работающее ради оформления.

Поэтому здесь своя панель с теми же вызовами. Снаружи она отвечает как
прежняя, внутри рисует кнопки по разметке Nora: залитый акцентом
выбранный пункт, скруглённые углы, свои отступы.

Что сознательно НЕ повторяется: сворачивание панели в узкую полоску.
qfluentwidgets умеет прятать подписи, оставляя значки. У нас вместо
этого простой режим, который прячет лишние пункты целиком, — два разных
способа «сделать меньше» на одном экране только путали бы.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from shell.theme import RAIL_ITEM_GAP, RAIL_PADDING_BOTTOM, RAIL_PADDING_TOP, RAIL_WIDTH
from ui.accessibility import enable_keyboard_click, set_control_accessibility


#: Положения пунктов, как в qfluentwidgets: сверху, в прокручиваемой
#: середине и внизу. Значения не важны, важно совпадение имён.
POSITION_TOP = "top"
POSITION_SCROLL = "scroll"
POSITION_BOTTOM = "bottom"

#: Группа для пунктов, добавленных до первого заголовка.
#:
#: Сборщик панели идёт группами и перед каждой ставит заголовок — кроме
#: первой, «root»: над главной страницей режима подпись не нужна. Поэтому
#: всё, что пришло до первого заголовка, относится к ней.
DEFAULT_GROUP = "root"


def _merged(group: str) -> str:
    """Имя раздела с учётом слияния. Без Qt-зависимостей в импорте."""
    try:
        from shell.tabs import merge_group

        return merge_group(group)
    except Exception:
        return group


def _position_key(position) -> str:
    """Превращает NavigationItemPosition в наш ключ.

    Вызывающий код передаёт перечисление qfluentwidgets, и его имя —
    единственное, на что можно опереться, не завися от библиотеки.
    """
    name = str(getattr(position, "name", position) or "").strip().upper()
    if name.startswith("TOP"):
        return POSITION_TOP
    if name.startswith("BOTTOM"):
        return POSITION_BOTTOM
    return POSITION_SCROLL


class NavItemButton(QPushButton):
    """Пункт навигации. Снаружи выглядит как кнопка qfluentwidgets.

    Длинные названия обрезаются многоточием. QPushButton этого не умеет:
    текст, который не помещается, он просто рисует за краем кнопки —
    «Управление net67 v2» уезжало за правый край панели и обрывалось на
    полубукве. Полное название остаётся в подсказке и в имени для
    программ экранного доступа: обрезка касается только рисунка.
    """

    #: Запас под внутренние отступы пункта: 16 слева, 16 справа плюс
    #: внешние поля 10 с каждой стороны, заданные в theme.py.
    TEXT_PADDING = 52

    def __init__(self, route_key: str, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("net67NavItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.routeKey = str(route_key)
        self._full_text = str(text)
        set_control_accessibility(
            self, name=text, description=f"Открыть раздел «{text}»"
        )
        enable_keyboard_click(self)
        self._apply_elided_text()

    def setText(self, text) -> None:  # noqa: N802 (Qt override)
        self._full_text = str(text)
        self._apply_elided_text()

    def fullText(self) -> str:  # noqa: N802 (в тон остальному API)
        return self._full_text

    def resizeEvent(self, event):  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._apply_elided_text()

    def _apply_elided_text(self) -> None:
        from PyQt6.QtGui import QFontMetrics

        available = max(0, int(self.width()) - self.TEXT_PADDING)
        if available <= 0:
            super().setText(self._full_text)
            return

        metrics = QFontMetrics(self.font())
        shown = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, available)
        if shown != super().text():
            super().setText(shown)

    # qfluentwidgets зовёт эти методы у своих пунктов, и вызывающий код
    # местами обращается к ним напрямую.
    def setSelected(self, selected: bool) -> None:  # noqa: N802 (совместимость)
        self.setChecked(bool(selected))


class NavigationCompat(QWidget):
    """Боковая панель с интерфейсом NavigationInterface.

    Дополнительно панель знает, какому разделу принадлежит каждый пункт.
    Знание берётся из порядка вызовов: сборщик ставит заголовок группы, а
    следом её пункты. Это нужно вкладкам в полосе заголовка — они
    показывают по одной группе за раз, и без такой принадлежности им
    пришлось бы заново разбирать схему навигации.
    """

    #: Состав панели изменился: добавлен пункт или заголовок.
    structureChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("net67Rail")
        self.setFixedWidth(RAIL_WIDTH)

        self._items: dict[str, NavItemButton] = {}
        self._headers: list[QLabel] = []
        self._current_key: str | None = None

        self._current_group = DEFAULT_GROUP
        self._group_order: list[str] = [DEFAULT_GROUP]
        self._item_group: dict[str, str] = {}
        self._group_header: dict[str, QLabel] = {}
        self._visible_group: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, RAIL_PADDING_TOP, 0, RAIL_PADDING_BOTTOM)
        root.setSpacing(RAIL_ITEM_GAP)

        self._layouts: dict[str, QVBoxLayout] = {}
        for key in (POSITION_TOP, POSITION_SCROLL, POSITION_BOTTOM):
            box = QVBoxLayout()
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(RAIL_ITEM_GAP)
            self._layouts[key] = box
            root.addLayout(box)
            if key == POSITION_SCROLL:
                # Растяжение между серединой и низом: иначе нижние
                # пункты прилипают к верхним, а не к краю окна.
                root.addStretch(1)

    # ── интерфейс qfluentwidgets ──────────────────────────────────────

    def addItem(  # noqa: N802 (совместимость)
        self,
        routeKey: str,  # noqa: N803
        icon=None,
        text: str = "",
        onClick=None,  # noqa: N803
        selectable: bool = True,
        position=None,
        **_ignored,
    ) -> NavItemButton:
        return self.insertItem(
            -1,
            routeKey=routeKey,
            icon=icon,
            text=text,
            onClick=onClick,
            selectable=selectable,
            position=position,
        )

    def insertItem(  # noqa: N802 (совместимость)
        self,
        index: int,
        routeKey: str,  # noqa: N803
        icon=None,
        text: str = "",
        onClick=None,  # noqa: N803
        selectable: bool = True,
        position=None,
        **_ignored,
    ) -> NavItemButton:
        key = str(routeKey)
        existing = self._items.get(key)
        if existing is not None:
            return existing

        button = NavItemButton(key, str(text or key), self)
        button.setCheckable(bool(selectable))
        if callable(onClick):
            button.clicked.connect(lambda _checked=False, handler=onClick: handler())

        box = self._layouts[_position_key(position)]
        if index is None or int(index) < 0 or int(index) >= box.count():
            box.addWidget(button)
        else:
            box.insertWidget(int(index), button)

        self._items[key] = button
        self._item_group[key] = self._current_group
        if self._visible_group is not None and self._current_group != self._visible_group:
            button.hide()
        self.structureChanged.emit()
        return button

    def addItemHeader(  # noqa: N802
        self,
        text: str,
        position=None,
        *,
        group: str | None = None,
        **_ignored,
    ) -> QLabel:
        label = QLabel(str(text or ""), self)
        label.setObjectName("net67SectionLabel")
        label.setContentsMargins(26, 14, 26, 2)
        self._layouts[_position_key(position)].addWidget(label)
        self._headers.append(label)

        # Заголовок открывает новую группу: всё, что добавят следом,
        # принадлежит ей. Имя группы приходит от сборщика панели; если
        # его не передали, берём подпись — она хотя бы уникальна.
        #
        # Слитые разделы сводятся здесь же: «Настройки» показываются
        # внутри «Диагностики», и панель обязана считать их одним
        # разделом, иначе вкладок окажется две с одним названием.
        name = _merged(str(group or text or "").strip() or DEFAULT_GROUP)
        self._current_group = name
        if name not in self._group_order:
            self._group_order.append(name)
        self._group_header[name] = label
        self.structureChanged.emit()
        return label

    def addSeparator(self, position=None, **_ignored) -> QWidget:  # noqa: N802
        line = QWidget(self)
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255, 255, 255, 0.08);")
        self._layouts[_position_key(position)].addWidget(line)
        return line

    def setCurrentItem(self, routeKey: str) -> None:  # noqa: N802,N803
        key = str(routeKey)
        self._current_key = key
        for item_key, button in self._items.items():
            button.setChecked(item_key == key)

    def setMinimumExpandWidth(self, width: int) -> None:  # noqa: N802
        """Заглушка: панель не сворачивается, см. описание модуля."""

    def widget(self, routeKey: str):  # noqa: N802,N803
        return self._items.get(str(routeKey))

    # ── наше ──────────────────────────────────────────────────────────

    @property
    def items(self) -> dict[str, NavItemButton]:
        return dict(self._items)

    @property
    def headers(self) -> list[QLabel]:
        return list(self._headers)

    # ── разделы ───────────────────────────────────────────────────────

    def groups(self) -> tuple[str, ...]:
        """Разделы в порядке добавления, только непустые.

        Пустые отбрасываем: вкладка, за которой ничего нет, — это тупик.
        Спрятанные пункты не считаются: в простом виде почти все разделы
        пустеют, и вкладки обязаны исчезнуть вместе с ними.
        """
        filled: list[str] = []
        for name in self._group_order:
            if any(
                key
                for key, group in self._item_group.items()
                if group == name and not self._items[key].isHidden()
            ):
                filled.append(name)
        return tuple(filled)

    def group_of(self, route_key: str) -> str:
        return self._item_group.get(str(route_key), DEFAULT_GROUP)

    def keys_in_group(self, group: str) -> tuple[str, ...]:
        """Ключи пунктов группы в том порядке, в каком они добавлены."""
        name = str(group)
        return tuple(key for key in self._items if self._item_group.get(key) == name)

    @property
    def visible_group(self) -> str | None:
        return self._visible_group

    def show_only_group(self, group: str | None) -> None:
        """Запоминает, какой раздел открыт.

        Видимость пунктов при этом не трогается, и это важно. Панель с
        экрана убрана — всё показывают вкладки, — а `isHidden()` у её
        пунктов остался единственным признаком того, что страница
        спрятана простым режимом. Пряча пункты ещё и по разделу, мы
        затирали бы этот признак, и вкладки перестали бы исчезать в
        простом виде.
        """
        self._visible_group = None if group is None else str(group)

    @property
    def current_key(self) -> str | None:
        return self._current_key


__all__ = [
    "POSITION_BOTTOM",
    "POSITION_SCROLL",
    "POSITION_TOP",
    "NavItemButton",
    "NavigationCompat",
]
