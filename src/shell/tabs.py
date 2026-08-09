"""Вкладки разделов в полосе заголовка.

Раньше все разделы лежали одним столбцом слева: пять заголовков групп и
под ними полтора десятка пунктов. Столбец приходилось делать широким —
288 пикселей, — иначе названия не помещались и обрывались на полубукве,
и всё равно он занимал четверть окна ради списка, в который человек
заглядывает раз в неделю.

Здесь верхний уровень поднят наверх строкой: раздел выбирается вкладкой,
а слева остаются только страницы выбранного раздела. Экономия не в
пикселях, а во внимании — на глазах у человека одновременно пять слов
вместо двадцати.

## Откуда берутся вкладки

Из самой панели. Она знает, какому разделу принадлежит каждый пункт, —
сборщик добавляет заголовок группы, а следом её пункты. Придумывать
вкладкам отдельный источник значило бы завести второе описание
навигации, которое рано или поздно разойдётся с первым.

Пустые разделы во вкладки не попадают: в простом виде их почти не
остаётся, и вкладка, за которой ничего нет, — это тупик.

## Почему подчёркивание, а не заливка

Залитая вкладка спорит с залитым пунктом панели: два выделения одного
веса на экране заставляют глаз выбирать, какое из них главное. Полоска
в два пикселя под активной вкладкой такого спора не создаёт.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from ui.accessibility import enable_keyboard_click, set_control_accessibility


#: Названия разделов. Ключи — имена групп из схемы навигации.
#:
#: «root» назван «Обходом», а не «Главной»: там живёт кнопка включения, и
#: слово должно совпадать с тем, что написано на самой кнопке.
GROUP_TITLES: dict[str, str] = {
    "root": "Обход",
    "settings": "Пресеты",
    "system": "Инструменты",
    "diagnostics": "Диагностика",
}

#: Разделы, слитые в один.
#:
#: «Настройки» и «Диагностика» разъехались исторически: в первом были
#: логи и конфигурации, во втором BlockCheck и разбор лога winws. Для
#: человека это одно и то же занятие — посмотреть, что происходит и
#: почему не работает. Слито по просьбе.
#:
#: Слияние живёт здесь, а не в схеме навигации: схема описывает, из чего
#: собрана панель, и правка там задела бы порядок сборки страниц. Здесь
#: же меняется только то, как разделы показаны.
GROUP_MERGE: dict[str, str] = {
    "appearance": "diagnostics",
}


def merge_group(group: str) -> str:
    """Приводит имя раздела к тому, под которым он показывается."""
    key = str(group or "").strip()
    return GROUP_MERGE.get(key, key)

#: Высота полоски под активной вкладкой.
UNDERLINE_HEIGHT = 2

#: Отступ полоски от краёв вкладки. Она короче подписи — так она
#: читается как подчёркивание слова, а не как граница ячейки.
UNDERLINE_INSET = 10


def group_title(group: str) -> str:
    """Название раздела для вкладки. Незнакомое имя отдаём как есть."""
    key = merge_group(group)
    return GROUP_TITLES.get(key, key)


#: Длительность выезда одной вкладки.
TAB_REVEAL_MS = 220

#: Задержка между соседними вкладками.
#:
#: Они выезжают по очереди, а не разом: очередь читается как «раздел за
#: разделом становится доступен», одновременное появление — как рывок.
TAB_STAGGER_MS = 45


def reveal_tabs(tabs):
    """Проявляет появившиеся вкладки по очереди.

    Возвращает запущенные анимации. Ссылки на них лежат на самих
    вкладках: локальная переменная соберётся сборщиком мусора раньше,
    чем анимация доиграет.
    """
    from PyQt6.QtCore import QEasingCurve, QTimer, QVariantAnimation
    from PyQt6.QtWidgets import QGraphicsOpacityEffect

    from ui.animation_policy import are_animations_enabled, start_managed_animation

    if not are_animations_enabled():
        return []

    animations = []
    for order, tab in enumerate(tabs or ()):
        try:
            effect = QGraphicsOpacityEffect(tab)
            effect.setOpacity(0.0)
            tab.setGraphicsEffect(effect)

            animation = QVariantAnimation(tab)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setDuration(TAB_REVEAL_MS)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.valueChanged.connect(
                lambda value, target=effect: target.setOpacity(float(value))
            )
            # Эффект снимаем: он держит отдельный слой отрисовки, и
            # оставленный навсегда удорожает каждую перерисовку строки.
            animation.finished.connect(lambda target=tab: target.setGraphicsEffect(None))
        except Exception:
            continue

        tab._net67_reveal = animation
        delay = order * TAB_STAGGER_MS
        if delay <= 0:
            start_managed_animation(animation)
        else:
            QTimer.singleShot(delay, lambda target=animation: start_managed_animation(target))
        animations.append(animation)
    return animations


class GroupTab(QPushButton):
    """Одна вкладка. Активная подчёркнута полоской."""

    def __init__(self, group: str, parent=None):
        super().__init__(group_title(group), parent)
        self.setObjectName("net67GroupTab")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.group = str(group)
        set_control_accessibility(
            self,
            name=group_title(group),
            description=f"Открыть раздел «{group_title(group)}»",
        )
        enable_keyboard_click(self)

    def paintEvent(self, event):  # noqa: N802 (Qt override)
        super().paintEvent(event)
        if not self.isChecked():
            return

        from shell.theme import palette

        try:
            from qfluentwidgets import isDarkTheme

            colors = palette(bool(isDarkTheme()))
        except Exception:
            colors = palette(True)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.accent))
        painter.drawRoundedRect(
            UNDERLINE_INSET,
            self.height() - UNDERLINE_HEIGHT,
            max(0, self.width() - UNDERLINE_INSET * 2),
            UNDERLINE_HEIGHT,
            1.0,
            1.0,
        )
        painter.end()


class GroupTabBar(QWidget):
    """Строка вкладок. Пересобирается вслед за составом панели."""

    groupSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("net67GroupTabs")

        self._tabs: dict[str, GroupTab] = {}
        self._current: str | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(0)
        self._layout = layout

    # ── состав ────────────────────────────────────────────────────────

    @property
    def tabs(self) -> dict[str, GroupTab]:
        return dict(self._tabs)

    @property
    def current(self) -> str | None:
        return self._current

    def set_groups(self, groups) -> None:
        """Приводит строку вкладок к списку разделов.

        Существующие вкладки не пересоздаются: панель дособирается по
        частям, и полная пересборка на каждое добавление мигала бы.

        Появившиеся вкладки выезжают. В простом виде их три из четырёх
        нет, и при переходе в расширенный они возникали разом — человек
        попросил, чтобы «дополнительные вкладки сверху плавно выезжали».
        """
        wanted = [str(name) for name in (groups or ())]
        appeared = [name for name in wanted if name not in self._tabs]

        for name in list(self._tabs):
            if name not in wanted:
                tab = self._tabs.pop(name)
                self._layout.removeWidget(tab)
                tab.deleteLater()

        for index, name in enumerate(wanted):
            tab = self._tabs.get(name)
            if tab is None:
                tab = GroupTab(name, self)
                tab.clicked.connect(lambda _checked=False, key=name: self.select(key))
                self._tabs[name] = tab
            self._layout.insertWidget(index, tab)

        if self._current not in self._tabs:
            self._current = None
        if self._current is None and wanted:
            self.select(wanted[0], notify=False)

        if appeared:
            reveal_tabs([self._tabs[name] for name in appeared])

    def select(self, group: str, *, notify: bool = True) -> None:
        name = str(group)
        if name not in self._tabs:
            return
        self._current = name
        for key, tab in self._tabs.items():
            tab.setChecked(key == name)
            set_control_accessibility(
                tab,
                name=group_title(key),
                description=(
                    f"Раздел «{group_title(key)}», "
                    + ("открыт" if key == name else "не открыт")
                ),
            )
        if notify:
            self.groupSelected.emit(name)


class PageTab(QPushButton):
    """Вкладка страницы во второй строке.

    Выглядит иначе, чем вкладка раздела: не подчёркивание, а скруглённая
    заливка. Два одинаковых ряда подчёркиваний друг под другом
    невозможно прочитать — глаз не понимает, какой из них главнее.
    """

    def __init__(self, route_key: str, text: str, parent=None):
        super().__init__(str(text), parent)
        self.setObjectName("net67PageTab")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.routeKey = str(route_key)
        set_control_accessibility(
            self, name=str(text), description=f"Открыть страницу «{text}»"
        )
        enable_keyboard_click(self)


class PageTabBar(QWidget):
    """Вторая строка: страницы выбранного раздела.

    Заменяет боковую панель целиком. Панель занимала 288 пикселей по
    ширине на всю высоту окна ради списка из двух-четырёх строк; строка
    занимает 34 пикселя по высоте и ничего не отнимает у содержимого.

    Строка прячется сама, когда страниц меньше двух: выбирать не из
    чего, и пустая полоса читалась бы как поломка.
    """

    pageSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("net67PageTabs")

        self._tabs: dict[str, PageTab] = {}
        self._current: str | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(30, 4, 30, 4)
        layout.setSpacing(4)
        self._layout = layout
        self._layout.addStretch(1)

    @property
    def tabs(self) -> dict[str, PageTab]:
        return dict(self._tabs)

    @property
    def current(self) -> str | None:
        return self._current

    def set_pages(self, pages) -> None:
        """Приводит строку к списку пар (ключ маршрута, подпись)."""
        wanted = [(str(key), str(title)) for key, title in (pages or ())]
        keys = [key for key, _title in wanted]

        for key in list(self._tabs):
            if key not in keys:
                tab = self._tabs.pop(key)
                self._layout.removeWidget(tab)
                tab.deleteLater()

        for index, (key, title) in enumerate(wanted):
            tab = self._tabs.get(key)
            if tab is None:
                tab = PageTab(key, title, self)
                tab.clicked.connect(
                    lambda _checked=False, route=key: self.select(route)
                )
                self._tabs[key] = tab
            elif tab.text() != title:
                tab.setText(title)
            self._layout.insertWidget(index, tab)

        if self._current not in self._tabs:
            self._current = None

        # Одна страница — выбирать не из чего.
        self.setVisible(len(wanted) > 1)

    def select(self, route_key: str, *, notify: bool = True) -> None:
        key = str(route_key)
        if key not in self._tabs:
            return
        self._current = key
        for route, tab in self._tabs.items():
            tab.setChecked(route == key)
        if notify:
            self.pageSelected.emit(key)


__all__ = [
    "GROUP_MERGE",
    "TAB_REVEAL_MS",
    "TAB_STAGGER_MS",
    "reveal_tabs",
    "GROUP_TITLES",
    "PageTabBar",
    "merge_group",
    "UNDERLINE_HEIGHT",
    "UNDERLINE_INSET",
    "GroupTab",
    "GroupTabBar",
    "PageTab",
    "group_title",
]
