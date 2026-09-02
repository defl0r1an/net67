"""Простой вид главной страницы.

Человеку нужна одна кнопка. Ручная остановка winws, автоперезапуск
Discord, --wssize, сброс сети Windows, блокировка государственных СМИ —
всё это живёт в расширенных настройках и в простом виде только пугает.

Боковая панель в простом виде тоже скрыта: в ней оставались два пункта
и половина пустоты. Вернуться к полному интерфейсу можно кнопкой внизу
страницы — без неё скрытая панель стала бы ловушкой.

Виджеты не удаляются, а скрываются: их читают обновление переводов,
применение темы и синхронизация настроек, и None там привёл бы к падению.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt

from log.log import log


#: Атрибуты страницы, которые прячем в простом виде.
#:
#: Кнопка «Включить», плашка состояния и карточка автозапуска остаются:
#: это ровно то, ради чего человек открывает приложение.
HIDDEN_IN_SIMPLE_VIEW: tuple[str, ...] = (
    # Ручное управление движком.
    "control_section_label",
    "control_card_card",
    # Служебные разделы.
    "additional_settings_section_label",
    "additional_settings_card",
    "last_status_message_card",
    "extra_section_label",
    "extra_card",
)

#: Строки карточки «Настройки программы», которые не нужны в простом виде.
#: Сама карточка остаётся ради автозапуска.
HIDDEN_SETTING_ROWS: tuple[str, ...] = (
    "auto_dpi_toggle",
    "tray_close_mode_combo",
    "defender_toggle",
    "max_block_toggle",
    "state_media_block_toggle",
    # Прокси Telegram — настройка для тех, кто им пользуется, и в
    # простом виде она лишняя: там оставлены кнопка, состояние и
    # автозапуск, всё остальное убрано.
    "telegram_proxy_toggle",
)

#: Где страница хранит исходные высоты отступов.
_SPACING_ATTR = "_simple_view_spacings"


#: Группы настроек, чьи строки прячет простой вид.
#:
#: Держим списком, а не ищем по дереву: страница знает свои карточки по
#: имени, и явный перечень честнее обхода родителей — при переименовании
#: он сломается заметно, а не тихо перестанет находить группу.
_SETTING_GROUPS: tuple[str, ...] = (
    "program_settings_card",
    "additional_settings_card",
    "extra_card",
)


def _set_visible(page, attr: str, visible: bool) -> None:
    widget = getattr(page, attr, None)
    if widget is None:
        return
    try:
        widget.setVisible(bool(visible))
    except Exception as exc:
        log(f"[SIMPLE] не удалось изменить видимость {attr}: {exc}", "DEBUG")


def _refresh_setting_group_heights(page) -> None:
    """Пересчитывает высоту групп после смены видимости их строк."""
    try:
        from ui.fluent_widgets import refresh_setting_card_group_height
    except Exception as exc:
        log(f"[SIMPLE] пересчёт высоты групп недоступен: {exc}", "DEBUG")
        return

    for attr in _SETTING_GROUPS:
        group = getattr(page, attr, None)
        if group is None:
            continue
        try:
            refresh_setting_card_group_height(group)
        except Exception as exc:
            log(f"[SIMPLE] не удалось пересчитать высоту {attr}: {exc}", "DEBUG")


def _collapse_dangling_spacings(page, advanced: bool) -> None:
    """Схлопывает отступы, оставшиеся от скрытых разделов.

    add_spacing() кладёт в раскладку QSpacerItem фиксированной высоты. Он
    не виджет, скрыть его нельзя, и после скрытия соседних карточек на
    странице оставались пустые полосы по 16 пикселей подряд — именно они
    и выглядели как «дырки» между блоками.
    """
    layout = getattr(page, "vBoxLayout", None)
    if layout is None:
        return

    original = getattr(page, _SPACING_ATTR, None)
    if original is None:
        original = {}
        setattr(page, _SPACING_ATTR, original)

    try:
        count = layout.count()
    except Exception:
        return

    def _next_widget_visible(start: int) -> bool:
        """Виден ли ближайший виджет ниже отступа."""
        for index in range(start + 1, count):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            try:
                return bool(widget.isVisible())
            except Exception:
                return True
        return False

    from PyQt6.QtWidgets import QSizePolicy

    last_index = count - 1
    for index in range(count):
        item = layout.itemAt(index)
        if item is None or item.widget() is not None or item.layout() is not None:
            continue

        # Замыкающее растяжение не трогаем. Оно тоже отступ, но живёт по
        # своим правилам — им распоряжается BasePage, — и стоит всегда
        # последним. Сбросить ему политику значило бы отобрать у страницы
        # единственное, что прижимает содержимое к верху.
        if index == last_index:
            continue

        height = original.get(index)
        if height is None:
            try:
                height = int(item.sizeHint().height())
            except Exception:
                height = 16
            original[index] = height

        keep = advanced or _next_widget_visible(index)
        try:
            # Политику задаём явно. Без последних двух доводов Qt ставит
            # отступу Minimum по обеим осям вместо Fixed по вертикали, и
            # отступ перестаёт быть отступом: он получает право расти и
            # начинает делить с остальными лишнюю высоту окна.
            item.changeSize(
                0,
                height if keep else 0,
                QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Fixed,
            )
        except Exception:
            continue

    try:
        layout.invalidate()
        layout.activate()
    except Exception:
        pass

    # Пересчёт замыкающего растяжения. Состав страницы только что
    # изменился, а решение «нужно ли растяжение» принимается по составу:
    # без пересчёта оно остаётся от прежнего режима.
    sync = getattr(page, "_sync_trailing_stretch", None)
    if callable(sync):
        try:
            sync()
        except Exception:
            pass

    if not advanced:
        _pin_content_to_top(page)


def _pin_content_to_top(page) -> None:
    """В простом виде содержимое стоит вплотную сверху. Без исключений.

    Это не дублирование логики BasePage, а её ужесточение для одного
    случая. BasePage решает судьбу замыкающего растяжения по составу
    страницы: если на ней есть виджет, который сам забирает высоту,
    растяжение выключается, иначе оно поделило бы высоту с ним пополам.

    В простом виде такого виджета нет и быть не может — там кнопка,
    строка состояния, три плитки и одна карточка. Но карточки настроек
    объявляют вертикальную политику Expanding, и правило срабатывало
    против нас: растяжение выключалось, лишняя высота расходилась по
    промежуткам, и всё разъезжалось. Человек описал это словами «все
    разьедется в разные стороны и будут большие пробелы».

    Поэтому здесь растяжение включается принудительно и последним
    действием — после того как BasePage уже сказал своё слово.
    """
    from PyQt6.QtWidgets import QSizePolicy

    layout = getattr(page, "vBoxLayout", None)
    if layout is None or not getattr(page, "_trailing_stretch_added", False):
        return

    try:
        index = layout.count() - 1
        item = layout.itemAt(index)
        if item is None or item.widget() is not None or item.layout() is not None:
            return
        item.changeSize(
            0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )
        layout.setStretch(index, 1)
        page._trailing_stretch_expands = True
        layout.invalidate()
        layout.activate()
    except Exception as exc:
        log(f"[SIMPLE] не удалось прижать содержимое к верху: {exc}", "DEBUG")


def _reveal(widgets) -> None:
    """Проявляет блоки, которых на экране не было.

    Само движение живёт в ui/reveal.py и одинаково для всех мест, где
    что-то появляется. Раньше здесь была своя анимация — только
    прозрачность, без сдвига, и очередь по порядку объявления списков,
    а не по расположению на экране. Волна из этого не складывалась.
    """
    from ui.reveal import reveal_widgets

    reveal_widgets(widgets)


def _conceal(widgets, on_finished) -> bool:
    """Убирает блоки волной. False — ухода не будет, прячьте сами.

    Само движение живёт в ui/reveal.py, рядом с появлением: это одна
    пара, и разводить её по двум местам значит однажды поменять только
    половину.
    """
    try:
        from ui.reveal import conceal_widgets

        return bool(conceal_widgets(widgets, on_finished=on_finished))
    except Exception as exc:
        log(f"[SIMPLE] уход блоков не запущен: {exc}", "DEBUG")
        return False


def _stop_pending_motion(page) -> None:
    """Снимает незаконченные появления и уходы со всех переключаемых блоков.

    Без этого быстрое переключение туда-обратно оставляло следы: уход,
    начатый в прошлый раз, доводил дело до конца и прятал строку,
    которую только что показали.
    """
    try:
        from ui.reveal import stop_motion
    except Exception:
        return

    for attr in (*HIDDEN_IN_SIMPLE_VIEW, *HIDDEN_SETTING_ROWS):
        stop_motion(getattr(page, attr, None))


def attach_theme_switch(page) -> None:
    """Выбор темы в простом виде убран.

    Механизм смены темы в приложении работает ненадёжно: переключатель
    подсвечивал выбор, но окно оставалось прежним. Показывать управление,
    которое не работает, хуже, чем не показывать вовсе. Тема осталась в
    расширенных настройках, в разделе «Оформление».
    """
    _ = page


def attach_advanced_button(page, window) -> None:
    """Больше ничего не добавляет.

    Кнопка «Расширенные настройки» переехала в полосу заголовка и стала
    переключателем: нажата — расширенный вид. Внизу страницы она была
    единственным входом в полный интерфейс, пока не было верхней строки;
    теперь это второй орган управления для одного и того же действия, и
    человек попросил его убрать.

    Функция оставлена пустой, а не удалена: её зовут обе страницы
    управления, v1 и v2, и удаление потребовало бы правок в двух местах
    ради ничего.
    """
    _ = (page, window)
    return


def _attach_advanced_button_disabled(page, window) -> None:
    if getattr(page, "_simple_view_advanced_btn", None) is not None:
        return

    try:
        from qfluentwidgets import FluentIcon, PushButton
    except Exception:
        return

    def _toggle() -> None:
        try:
            from ui.navigation.advanced_toggle import toggle_advanced_mode

            toggle_advanced_mode(window)
        except Exception as exc:
            log(f"[SIMPLE] переход в расширенный вид не удался: {exc}", "⚠ WARNING")

    try:
        button = PushButton("Расширенные настройки", icon=FluentIcon.SETTING)
        button.clicked.connect(_toggle)
        page.add_spacing(16)
        page.add_widget(button)
    except Exception as exc:
        log(f"[SIMPLE] не удалось добавить кнопку расширенных настроек: {exc}", "DEBUG")
        return

    page._simple_view_advanced_btn = button

    try:
        from ui.accessibility import set_control_accessibility

        set_control_accessibility(
            button,
            name="Расширенные настройки",
            description="Открывает полный интерфейс с боковым меню.",
        )
    except Exception:
        pass


def _switch_extra_controls(page, visible: bool) -> list:
    """Показывает то, что нужно только в простом виде, и правит сводку.

    Возвращает то, что этим переключением появилось, — чтобы вызывающий
    показал его тем же движением, что и остальное. Возникающая из ничего
    кнопка «Расширенный вид» посреди только что улёгшейся страницы
    выглядит как недорисованный кадр.
    """
    extras = []
    for attr in (
        "_simple_view_advanced_btn",
        "_simple_view_theme_card",
        "_simple_view_theme_title",
    ):
        widget = getattr(page, attr, None)
        if widget is not None and widget.isHidden() and not visible:
            extras.append(widget)

    # Выбор темы и кнопка перехода нужны только там, где нет панели.
    _set_visible(page, "_simple_view_advanced_btn", not visible)
    _set_visible(page, "_simple_view_theme_card", not visible)
    _set_visible(page, "_simple_view_theme_title", not visible)

    # Плитки сводки ведут на страницы, которых в простом виде нет:
    # клик по «Профили» открывал бы раздел, спрятанный из панели.
    summary = getattr(page, "top_summary", None)
    for attr in ("preset_item", "profiles_item", "mode_item"):
        item = getattr(summary, attr, None)
        if item is None:
            continue
        try:
            # Реакция на клик и клавиши завязана на _clickable внутри
            # ControlTopSummaryItem — его и переключаем.
            item._clickable = bool(visible)
            item.setCursor(
                Qt.CursorShape.PointingHandCursor if visible else Qt.CursorShape.ArrowCursor
            )
        except Exception as exc:
            log(f"[SIMPLE] плитка сводки {attr}: {exc}", "DEBUG")

    return extras


def _activate_layout(page) -> None:
    """Даёт раскладке отработать до замера координат.

    setVisible() только помечает виджет видимым, а место ему Qt выделяет
    следующим проходом раскладки. Спросить координаты раньше — получить
    нули у всех и произвольную очередь вместо волны.
    """
    try:
        layout = getattr(page, "vBoxLayout", None) or page.layout()
        if layout is not None:
            layout.activate()
    except Exception as exc:
        log(f"[SIMPLE] раскладка не пересчитана перед показом: {exc}", "DEBUG")


def _close_up_layout(page, visible: bool) -> None:
    """Смыкает раскладку после того, как видимость строк устоялась.

    Показать строку мало — группе надо пересчитать высоту.

    SettingCardGroup держит фиксированную высоту, посчитанную по своим
    строкам. Пересчёт запускает фильтр событий, но он висит на самой
    группе и ловит только её события: добавление и удаление детей да
    собственный Show. Смена видимости строки — событие ребёнка, до
    группы оно не доходит.

    Отсюда и жалоба «при первом переходе в расширенный вид съедается
    настройка»: строки уже видимы, а группа осталась ростом с простой
    вид и просто обрезает их снизу. Возврат на вкладку показывает
    группу заново, Show доходит до фильтра, высота пересчитывается —
    и всё «чинится само».
    """
    _refresh_setting_group_heights(page)
    extras = _switch_extra_controls(page, visible)
    _collapse_dangling_spacings(page, visible)

    if extras:
        _activate_layout(page)
        _reveal(extras)


def apply_simple_view(page, advanced: bool | None = None, *, on_settled=None) -> None:
    """Показывает или прячет расширенные разделы страницы управления.

    ``on_settled`` зовётся, когда вид улёгся: блоки уехали, раскладка
    сомкнулась. Через него окно меняет размер — после волны, а не до
    неё. Раньше окно схлопывалось первым, и волна доигрывала уже внутри
    маленького окна, за его краем.
    """
    if advanced is None:
        try:
            from ui.navigation.schema import is_advanced_mode_enabled

            advanced = bool(is_advanced_mode_enabled())
        except Exception:
            advanced = True

    visible = bool(advanced)

    # Незаконченное движение снимаем первым делом: уход, начатый прошлым
    # переключением, иначе доведёт дело до конца и спрячет строку,
    # которую это переключение только что показало.
    _stop_pending_motion(page)

    # Что именно появляется или уходит — нужно знать до смены видимости:
    # анимируем только то, что на экране меняется. Уже видимое проявлять
    # заново значит моргать им на ровном месте.
    changing = []
    for attr in (*HIDDEN_IN_SIMPLE_VIEW, *HIDDEN_SETTING_ROWS):
        widget = getattr(page, attr, None)
        if widget is None:
            continue
        if bool(widget.isHidden()) == visible:
            changing.append(widget)

    def _settled() -> None:
        _close_up_layout(page, visible)
        if on_settled is not None:
            try:
                on_settled()
            except Exception as exc:
                log(f"[SIMPLE] шаг после укладки вида не выполнен: {exc}", "DEBUG")

    # Волну показываем только на видимой странице.
    #
    # Переход в простой вид уводит на главную, и страница управления
    # может быть не той, что на экране. Анимировать невидимое незачем, а
    # ждать её конца — значит на полсекунды отложить то, что подвешено
    # на on_settled: размер окна менялся бы с необъяснимой задержкой.
    try:
        on_screen = bool(page.isVisible())
    except Exception:
        on_screen = False

    if not visible:
        # Уход. Прячет каждый блок сам, в конце его пути, и только потом
        # смыкает раскладку — иначе группы схлопнутся под ещё уезжающими
        # строками, и красивого ухода никто не увидит.
        if on_screen and _conceal(changing, _settled):
            return

        for attr in (*HIDDEN_IN_SIMPLE_VIEW, *HIDDEN_SETTING_ROWS):
            _set_visible(page, attr, visible)
        _settled()
        return

    for attr in (*HIDDEN_IN_SIMPLE_VIEW, *HIDDEN_SETTING_ROWS):
        _set_visible(page, attr, visible)
    _settled()

    if changing and on_screen:
        _activate_layout(page)
        _reveal(changing)


__all__ = [
    "HIDDEN_IN_SIMPLE_VIEW",
    "HIDDEN_SETTING_ROWS",
    "apply_simple_view",
    "attach_advanced_button",
    "attach_theme_switch",
]
