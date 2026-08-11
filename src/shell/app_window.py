"""Главное окно net67 на своей оболочке.

Заменяет окно qfluentwidgets. Снаружи отвечает теми же четырьмя вещами,
которыми пользуется остальное приложение, — navigationInterface,
stackedWidget, addSubInterface, switchTo, — поэтому сорок страниц,
маршрутизация, поиск и трей продолжают работать без правок.

Так сделано намеренно. Переписывать сборщик навигации и все страницы
ради смены облика — это менять работающее ради оформления, а цена
ошибки здесь высокая: приложение просто не запустится. Совместимый слой
даёт новый вид сразу и оставляет возможность выкидывать старые вызовы
по одному, когда до них дойдут руки.

Окно без системной рамки: иначе поверх графитового заголовка остаётся
светлая полоса Windows, и приложение выглядит собранным из двух половин.

Но безрамочность взята у qframelesswindow, а не сделана руками. Первый
подход — обычный QWidget с флагом FramelessWindowHint — приводил к
падению: приложение закрывалось молча, а faulthandler показал
«Windows fatal exception: access violation» прямо внутри show().

Причина в том, что безрамочное окно на Windows требует своей обработки
сообщений WM_NCCALCSIZE и WM_NCHITTEST. Без неё DWM работает с окном,
у которого рамка объявлена, но не обслуживается. Библиотека
qframelesswindow это уже умеет, лежит в зависимостях qfluentwidgets и
проверена на тех же версиях Windows. Писать своё поверх её кода значило
бы повторить ту же ошибку второй раз.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qframelesswindow import FramelessWindow

from branding import APP_NAME
from config.build_info import APP_VERSION
from shell.nav_compat import NavigationCompat

#: Ключ переключателя простого и расширенного вида.
#:
#: Повторён здесь, а не импортирован из ui.navigation: оболочка не
#: должна зависеть от слоя приложения, иначе её нельзя поднять в тесте
#: без половины программы.
ADVANCED_TOGGLE_ROUTE_KEY = "__advanced_mode_toggle__"

#: Запас по ширине кнопки режима: внутренние отступы плюс воздух.
#:
#: Кнопка переключаемая, и подписи у состояний разной длины. Без запаса
#: она сжималась под короткую и обрезала длинную.
ADVANCED_BUTTON_PADDING = 34
from shell.theme import palette, shell_qss
from shell.window import TitleBar


FULLSCREEN_SLACK_PX = 24

#: Размер, к которому возвращаемся, если возвращаться некуда — окно ни
#: разу не было в обычном состоянии, и Qt не запомнил прежнюю рамку.
RESTORED_SIZE = (1120, 780)


def _looks_maximized(window) -> bool:
    """Занимает ли окно весь экран — по любому признаку.

    Одного `isMaximized()` мало. Приложение открывает окно, задавая ему
    размер рабочей области, а не вызывая showMaximized: с точки зрения
    Qt оно при этом обычное. Кнопка разворота попадала в ветку «развернуть»
    и разворачивала уже растянутое окно — то есть не делала ничего
    видимого. Нажатие второй раз повторяло то же самое.
    """
    try:
        if window.isMaximized() or window.isFullScreen():
            return True
    except Exception:
        return False

    try:
        screen = window.screen()
        if screen is None:
            return False
        available = screen.availableGeometry()
        frame = window.frameGeometry()
    except Exception:
        return False

    return (
        frame.width() >= available.width() - FULLSCREEN_SLACK_PX
        and frame.height() >= available.height() - FULLSCREEN_SLACK_PX
    )


def _restore_window(window) -> None:
    """Возвращает окно к обычному размеру.

    showNormal у растянутого, но не развёрнутого окна не делает ничего:
    оно и так «обычное». Поэтому размер задаём сами и ставим окно по
    центру экрана — иначе оно останется прижатым к левому верхнему углу.
    """
    window.showNormal()

    try:
        screen = window.screen()
        available = screen.availableGeometry()
    except Exception:
        return

    # Не больше четырёх пятых экрана. Иначе на маленьком мониторе
    # «обычный» размер упирается в тот же порог, по которому мы считаем
    # окно развёрнутым, и кнопка перестаёт переключать: замер на экране
    # 800x800 давал 776x776 — то есть снова «развёрнуто».
    width = min(RESTORED_SIZE[0], int(available.width() * 0.8))
    height = min(RESTORED_SIZE[1], int(available.height() * 0.8))
    if window.width() >= available.width() - FULLSCREEN_SLACK_PX or (
        window.height() >= available.height() - FULLSCREEN_SLACK_PX
    ):
        window.resize(width, height)
        window.move(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 2,
        )


class AppShellWindow(FramelessWindow):
    """Окно приложения: свой заголовок, своя навигация, стопка страниц."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("net67Window")
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1180, 760)

        self._dark = True
        self._custom_background: QColor | None = None

        # Свою полосу заголовка отдаём библиотеке: она сама держит её
        # поверх окна и обслуживает перетаскивание нативными
        # сообщениями. Раскладка ниже начинается под ней.
        self.setTitleBar(TitleBar(f"{APP_NAME} v{APP_VERSION}", self))
        self.titleBar.minimizeRequested.connect(self.showMinimized)
        self.titleBar.maximizeRequested.connect(self._toggle_maximized)
        self.titleBar.closeRequested.connect(self.close)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, self.titleBar.height(), 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Боковая панель остаётся как источник знаний о навигации —
        # какие есть разделы, какие в них страницы, — но на экране её
        # больше нет. Всё, что она показывала, переехало в две строки
        # вкладок под заголовком. Убирать её из кода значило бы
        # переписывать сборщик навигации, поиск и маршрутизацию.
        self.navigationInterface = NavigationCompat(self)
        self.navigationInterface.hide()

        self.stackedWidget = QStackedWidget(self)
        self.stackedWidget.setObjectName("net67Content")

        # Строка вкладок и стопка страниц лежат в одном столбце: строка
        # сверху, страницы под ней во всю оставшуюся высоту.
        self._install_group_tabs()
        body.addWidget(self.pageTabsHost, 1)

        # Свечение лежит под всем окном, поэтому создаётся последним и
        # опускается вниз стопки. В раскладке его нет намеренно: слой
        # занимает всё окно целиком и не должен на неё влиять.
        from shell.ambient import AmbientLayer

        self.ambient = AmbientLayer(self, dark=True)
        self.ambient.lower()

        root.addLayout(body, 1)

        # Уголка для растягивания нет намеренно: размер окна меняется по
        # краям, этим занимается qframelesswindow.
        self.titleBar.raise_()

        # Карточки настроек рисуют фон сами, в обход таблицы стилей, —
        # из-за этого правая половина окна оставалась чужой по цвету.
        try:
            from shell.card_paint import install_card_painting

            install_card_painting()
        except Exception:
            pass

        self._apply_window_border_colour()
        self._subscribe_to_theme_changes()
        self.apply_shell_theme(dark=self._current_theme_is_dark())

    def _apply_window_border_colour(self) -> None:
        """Гасит светлую рамку, которую Windows 11 рисует вокруг окна.

        Обводку рисует не приложение, а сама система: DWM обводит каждое
        окно линией в цвет акцента, а при выключенном акценте — светлой.
        На тёмном окне она читается как чужая белая рамка.

        Задаём цвет сами — тот же, что у фона окна. Отменить обводку
        нельзя, но слить её с окном можно.

        Работает только на Windows 11 и только через DWM: на десятке и
        на других системах вызов молча ничего не делает, и это правильно
        — там этой рамки и нет.
        """
        try:
            from qframelesswindow.utils.win32_utils import isGreaterEqualWin11
        except Exception:
            return

        try:
            if not isGreaterEqualWin11():
                return

            effect = getattr(self, "windowEffect", None)
            if effect is None:
                return

            from shell.theme import palette

            colours = palette(self._current_theme_is_dark())
            effect.setBorderAccentColor(self.winId(), QColor(colours.window))
        except Exception:
            # Рамка — мелочь оформления. Ронять из-за неё запуск нельзя.
            pass

    # ── вкладки разделов ──────────────────────────────────────────────

    def _install_group_tabs(self) -> None:
        """Ставит строку вкладок в полосу заголовка.

        Вкладки пересобираются вслед за панелью, а не один раз: сборщик
        навигации добавляет группы по мере готовности страниц, и на
        момент создания окна панель ещё пуста.

        Пересборка отложена на следующий оборот цикла событий. Пунктов
        десятка полтора, сигнал приходит на каждый, и без отсрочки строка
        вкладок перестраивалась бы пятнадцать раз подряд.
        """
        from PyQt6.QtCore import QTimer

        from shell.tabs import GroupTabBar

        from shell.tabs import PageTabBar

        self.groupTabs = GroupTabBar(self.titleBar)
        self.groupTabs.groupSelected.connect(self._on_group_selected)

        # Вторая строка живёт над содержимым, а не в заголовке: в
        # заголовке она соперничала бы с поиском за ширину.
        from PyQt6.QtWidgets import QVBoxLayout, QWidget

        self.pageTabsHost = QWidget(self)
        host_layout = QVBoxLayout(self.pageTabsHost)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)

        self.pageTabs = PageTabBar(self.pageTabsHost)
        self.pageTabs.pageSelected.connect(self._on_page_selected)
        host_layout.addWidget(self.pageTabs)
        host_layout.addWidget(self.stackedWidget, 1)

        title_bar_layout = getattr(self.titleBar, "hBoxLayout", None)
        buttons_host = getattr(self.titleBar, "buttons_host", None)
        if title_bar_layout is not None:
            index = title_bar_layout.count()
            if buttons_host is not None:
                found = title_bar_layout.indexOf(buttons_host)
                if found >= 0:
                    index = found
            title_bar_layout.insertWidget(index, self.groupTabs)

        self._tabs_refresh_scheduled = False

        def _schedule() -> None:
            if self._tabs_refresh_scheduled:
                return
            self._tabs_refresh_scheduled = True
            QTimer.singleShot(0, self._refresh_group_tabs)

        self.navigationInterface.structureChanged.connect(_schedule)

        # Переключатель простого и расширенного вида. Раньше он жил
        # внизу страницы управления — единственной страницы, на которой
        # его было видно. Наверху он доступен отовсюду.
        from PyQt6.QtWidgets import QPushButton

        from ui.accessibility import enable_keyboard_click, set_control_accessibility

        self.advancedButton = QPushButton("Расширенные настройки", self.titleBar)
        self.advancedButton.setObjectName("net67AdvancedToggle")
        self.advancedButton.setCheckable(True)
        self.advancedButton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.advancedButton.clicked.connect(self._on_advanced_clicked)
        self.advancedButton.pressed.connect(lambda: self._press_button(self.advancedButton, True))
        self.advancedButton.released.connect(lambda: self._press_button(self.advancedButton, False))
        set_control_accessibility(
            self.advancedButton,
            name="Расширенные настройки",
            description="Показать или скрыть остальные разделы",
        )
        enable_keyboard_click(self.advancedButton)
        self.advancedButton.hide()
        if title_bar_layout is not None:
            title_bar_layout.insertWidget(
                title_bar_layout.indexOf(self.groupTabs) + 1, self.advancedButton
            )

    #: Насколько кнопка проседает под нажатием.
    #:
    #: Два пикселя. Меньше не замечается, больше читается как дефект
    #: раскладки: кнопка стоит в строке заголовка, и соседи не должны
    #: шевелиться вместе с ней.
    PRESS_SHIFT_PX = 2

    #: Длительность проседания.
    PRESS_MS = 90

    def _press_button(self, button, pressed: bool) -> None:
        """Отклик на нажатие: кнопка проседает и возвращается.

        Двигаем нижний внутренний отступ, а не позицию: позицию вернёт
        раскладка при первом же пересчёте, а отступ она уважает.

        Анимация короткая намеренно. Отклик должен успеть за пальцем: то,
        что длится дольше сотни миллисекунд, воспринимается уже не как
        нажатие, а как задержка.
        """
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation

        from ui.animation_policy import are_animations_enabled, start_managed_animation

        target = self.PRESS_SHIFT_PX if pressed else 0

        def apply(value) -> None:
            shift = max(0, int(value))
            button.setContentsMargins(0, shift, 0, -shift)

        if not are_animations_enabled():
            apply(target)
            return

        current = button.contentsMargins().top()
        animation = QVariantAnimation(button)
        animation.setStartValue(int(current))
        animation.setEndValue(int(target))
        animation.setDuration(self.PRESS_MS)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(apply)
        # Ссылку держим на кнопке: локальная соберётся сборщиком мусора
        # раньше, чем анимация доиграет.
        button._net67_press = animation
        start_managed_animation(animation)

    def _on_advanced_clicked(self) -> None:
        """Зовёт тот же переключатель, что и прежняя кнопка внизу страницы.

        Через пункт панели, а не напрямую: у пункта уже подключён
        обработчик со всей логикой — сохранение настройки, пересборка
        видимости, возврат на главную.
        """
        item = self.navigationInterface.items.get(ADVANCED_TOGGLE_ROUTE_KEY)
        if item is not None:
            item.click()

    def _refresh_group_tabs(self) -> None:
        self._tabs_refresh_scheduled = False
        tabs = getattr(self, "groupTabs", None)
        if tabs is None:
            return

        # Состав вкладок берём по видимым пунктам панели. На первом
        # заходе панель собирается по частям, и часть пунктов ещё не
        # успела получить скрытость от простого режима — вкладки
        # показывались все, хотя режим простой. Поэтому в простом виде
        # оставляем только раздел открытой страницы.
        groups = list(self.navigationInterface.groups())
        if not self._advanced_mode_enabled():
            current = self.navigationInterface.current_key
            open_group = (
                self.navigationInterface.group_of(current) if current else None
            )
            allowed = open_group if open_group in groups else (groups[0] if groups else None)
            groups = [allowed] if allowed else []

        tabs.set_groups(groups)

        # Переключатель вида показываем, только когда он вообще есть:
        # его добавляет сборщик навигации, и до этого момента кнопка
        # вела бы в никуда.
        button = getattr(self, "advancedButton", None)
        if button is not None:
            item = self.navigationInterface.items.get(ADVANCED_TOGGLE_ROUTE_KEY)
            button.setVisible(item is not None)
            self._sync_advanced_button()

    @staticmethod
    def _advanced_mode_enabled() -> bool:
        """Расширенный ли сейчас вид. Сбой настроек трактуем как простой.

        Простой вид беднее, и ошибиться в его пользу безопаснее: человек
        нажмёт кнопку и получит остальное. Ошибка в другую сторону
        вываливает на него весь интерфейс без спроса.
        """
        try:
            from settings.store import get_advanced_mode

            return bool(get_advanced_mode())
        except Exception:
            return False

    def _sync_advanced_button(self) -> None:
        """Приводит кнопку к текущему режиму.

        Кнопка переключаемая: нажата — расширенный вид, и написано на
        ней «Простой режим», то есть куда она ведёт, а не где мы сейчас.
        Так же устроены все переключатели в программе.
        """
        button = getattr(self, "advancedButton", None)
        if button is None:
            return
        advanced = self._advanced_mode_enabled()

        button.setChecked(advanced)
        button.setText("Простой режим" if advanced else "Расширенные настройки")

        # Ширину держим по самой длинной из двух подписей. Кнопка
        # переключаемая, и без этого она подстраивалась под текущий
        # текст: «Простой режим» короче, кнопка сжималась, а при
        # обратном переключении длинная подпись в неё уже не влезала и
        # обрезалась на первой букве.
        metrics = button.fontMetrics()
        widest = max(
            metrics.horizontalAdvance("Простой режим"),
            metrics.horizontalAdvance("Расширенные настройки"),
        )
        button.setMinimumWidth(widest + ADVANCED_BUTTON_PADDING)

    def refresh_after_mode_change(self) -> None:
        """Пересобирает вкладки после смены простого и расширенного вида.

        Состав разделов зависит от режима, а сигнал об изменении состава
        панель не шлёт: пункты не добавляются и не удаляются, у них
        меняется видимость.
        """
        self._refresh_group_tabs()
        current = getattr(self, "groupTabs", None)
        if current is not None and current.current is not None:
            self._on_group_selected(current.current)

    def _on_page_selected(self, route_key: str) -> None:
        page = self._page_for_route(route_key)
        if page is not None:
            self.switchTo(page)
            return
        item = self.navigationInterface.items.get(route_key)
        if item is not None:
            item.click()

    def _refresh_page_tabs(self, group: str) -> None:
        """Наполняет вторую строку страницами раздела.

        Подписи берём у пунктов панели: они уже переведены и уже
        обрезаны до полного имени. Собственный список названий стал бы
        вторым источником правды.
        """
        nav = self.navigationInterface
        pages = []
        for key in nav.keys_in_group(group):
            # Переключатель вида — не страница: он живёт отдельной
            # кнопкой наверху и в списке страниц был бы лишним пунктом,
            # который ничего не открывает.
            if key == ADVANCED_TOGGLE_ROUTE_KEY:
                continue
            item = nav.items.get(key)
            # Спрятанные простым режимом страницы во вкладки не идут.
            if item is None or item.isHidden():
                continue
            title = item.fullText() if hasattr(item, "fullText") else item.text()
            pages.append((key, title))
        self.pageTabs.set_pages(pages)

    def _on_group_selected(self, group: str) -> None:
        """Показывает раздел: фильтрует панель и открывает его страницу.

        На страницу переходим только если открытая относится к другому
        разделу. Иначе нажатие на вкладку раздела, в котором уже
        находишься, сбрасывало бы человека на первую страницу.
        """
        nav = self.navigationInterface
        nav.show_only_group(group)
        self._refresh_page_tabs(group)

        current = nav.current_key
        if current is not None and nav.group_of(current) == group:
            return

        for key in nav.keys_in_group(group):
            item = nav.items.get(key)
            if item is None or item.isHidden():
                continue
            page = self._page_for_route(key)
            if page is not None:
                self.switchTo(page)
            else:
                item.click()
            return

    def _page_for_route(self, route_key: str):
        for index in range(self.stackedWidget.count()):
            page = self.stackedWidget.widget(index)
            if page is not None and page.objectName() == str(route_key):
                return page
        return None

    # ── совместимость с прежним окном ─────────────────────────────────

    def addSubInterface(  # noqa: N802 (совместимость)
        self,
        interface: QWidget,
        icon=None,
        text: str = "",
        position=None,
        **_ignored,
    ):
        """Добавляет страницу и пункт меню к ней.

        Ключ маршрута — objectName страницы, как и в qfluentwidgets:
        на него опирается setCurrentItem во всём остальном коде.
        """
        route_key = interface.objectName() or str(text)
        if self.stackedWidget.indexOf(interface) < 0:
            self.stackedWidget.addWidget(interface)
        return self.navigationInterface.addItem(
            routeKey=route_key,
            icon=icon,
            text=str(text or route_key),
            onClick=lambda page=interface: self.switchTo(page),
            selectable=True,
            position=position,
        )

    def switchTo(self, interface: QWidget) -> None:  # noqa: N802 (совместимость)
        if self.stackedWidget.indexOf(interface) < 0:
            self.stackedWidget.addWidget(interface)

        previous = self.stackedWidget.currentWidget()
        # Направление берём из порядка страниц в стопке, а он повторяет
        # порядок пунктов в панели: вниз по меню страница уходит вверх.
        forward = self.stackedWidget.indexOf(interface) >= self.stackedWidget.indexOf(previous)

        self.stackedWidget.setCurrentWidget(interface)
        route_key = interface.objectName()
        if route_key:
            self.navigationInterface.setCurrentItem(route_key)
            # Страницу открывают и мимо вкладок — поиском, кнопкой на
            # другой странице, возвратом в простой вид. Вкладка обязана
            # догнать, иначе подчёркнут один раздел, а открыт другой.
            tabs = getattr(self, "groupTabs", None)
            if tabs is not None:
                group = self.navigationInterface.group_of(route_key)
                if group in tabs.tabs and tabs.current != group:
                    tabs.select(group, notify=False)
                    self.navigationInterface.show_only_group(group)
                    self._refresh_page_tabs(group)
            page_tabs = getattr(self, "pageTabs", None)
            if page_tabs is not None and route_key in page_tabs.tabs:
                page_tabs.select(route_key, notify=False)

        if previous is not None and previous is not interface:
            try:
                from shell.page_transition import animate_page_change

                animate_page_change(
                    self.stackedWidget, previous, interface, forward=forward
                )
            except Exception:
                # Переход — оформление. Страница уже переключена.
                pass

    def setCustomBackgroundColor(self, light, dark) -> None:  # noqa: N802
        """Принимает цвет фона от страницы оформления.

        Прежнее окно умело подмешивать цвет под эффект Mica. Своё окно
        рисует фон само, поэтому цвет просто запоминается и уходит в
        стиль. Молча игнорировать вызов нельзя: человек выбрал бы цвет и
        не увидел изменений.
        """
        self._custom_background = QColor(dark if self._dark else light)
        self.apply_shell_theme(dark=self._dark)

    def setMicaEffectEnabled(self, enabled: bool) -> None:  # noqa: N802
        """Заглушка: Mica — эффект окна qfluentwidgets, его здесь нет."""

    def isMicaEffectEnabled(self) -> bool:  # noqa: N802
        return False

    # ── своё ──────────────────────────────────────────────────────────

    @staticmethod
    def _current_theme_is_dark() -> bool:
        try:
            from qfluentwidgets import isDarkTheme

            return bool(isDarkTheme())
        except Exception:
            return True

    def _subscribe_to_theme_changes(self) -> None:
        """Переписывает оболочку при смене темы.

        Без этого светлая тема была сломана целиком, и это не
        преувеличение: виджеты qfluentwidgets светлели сами, а оболочка
        оставалась с тёмной таблицей стилей — светлый текст на светлом
        фоне, графитовая панель рядом с белым содержимым. Прежнее окно
        было окном библиотеки и перекрашивалось само; своё обязано
        подписаться.

        Подписка идёт через ThemeRefreshBinding, а не напрямую на
        qconfig.themeChanged. Это требование архитектуры, и оно
        обосновано: в сборке Nuitka PyQt не разрывает подписки qconfig
        при удалении C++-объекта, и смена темы после закрытия окна падала
        бы с RuntimeError. Binding отписывается сам по destroyed.
        """
        try:
            from ui.theme_refresh import ThemeRefreshBinding

            self._theme_binding = ThemeRefreshBinding(self, self._on_theme_changed)
        except Exception:
            self._theme_binding = None

    def _on_theme_changed(self, *_args, **_kwargs) -> None:
        dark = self._current_theme_is_dark()
        ambient = getattr(self, "ambient", None)
        if ambient is not None:
            ambient.set_dark(dark)
        self.apply_shell_theme(dark=dark)

    def apply_shell_theme(self, *, dark: bool) -> None:
        self._dark = bool(dark)
        colors = palette(self._dark)
        qss = shell_qss(colors)
        if self._custom_background is not None and self._custom_background.isValid():
            qss += f"\n#net67Window {{ background: {self._custom_background.name()}; }}"
        self.setStyleSheet(qss)

        # Рамка окна красится вслед за темой: в светлой она должна
        # оставаться светлой, иначе окно получит тёмный кант.
        self._apply_window_border_colour()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Полоса заголовка лежит поверх раскладки, ширину ей задаём сами.
        self.titleBar.resize(self.width(), self.titleBar.height())
        ambient = getattr(self, "ambient", None)
        if ambient is not None:
            ambient.setGeometry(self.rect())

#: Насколько окно может не дотягивать до краёв экрана и всё ещё
#: считаться развёрнутым. Запас на тень и на округление при масштабе
#: интерфейса, отличном от ста процентов.
    def _toggle_maximized(self) -> None:
        if _looks_maximized(self):
            _restore_window(self)
        else:
            self.showMaximized()

__all__ = ["AppShellWindow"]
