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
)

#: Где страница хранит исходные высоты отступов.
_SPACING_ATTR = "_simple_view_spacings"


def _set_visible(page, attr: str, visible: bool) -> None:
    widget = getattr(page, attr, None)
    if widget is None:
        return
    try:
        widget.setVisible(bool(visible))
    except Exception as exc:
        log(f"[SIMPLE] не удалось изменить видимость {attr}: {exc}", "DEBUG")


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


#: Длительность появления одного блока настроек.
REVEAL_MS = 220

#: Задержка между соседними блоками.
#:
#: Они проявляются сверху вниз, а не разом: очередь показывает, что
#: раскрылось именно то, что было спрятано, и куда смотреть.
REVEAL_STAGGER_MS = 55


def _reveal(widgets) -> None:
    """Проявляет блоки, которых на экране не было.

    Прозрачностью, а не движением. Блоки стоят в раскладке, и сдвиг
    пришлось бы делать отступами — а это пересчёт всей страницы на
    каждом кадре, и страница настроек для этого слишком тяжёлая.
    """
    try:
        from PyQt6.QtCore import QEasingCurve, QTimer, QVariantAnimation
        from PyQt6.QtWidgets import QGraphicsOpacityEffect

        from ui.animation_policy import are_animations_enabled, start_managed_animation
    except Exception:
        return

    if not are_animations_enabled():
        return

    for order, widget in enumerate(widgets):
        try:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)

            animation = QVariantAnimation(widget)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setDuration(REVEAL_MS)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.valueChanged.connect(
                lambda value, target=effect: target.setOpacity(float(value))
            )
            # Эффект снимаем после показа: он рисует блок в отдельный
            # слой, и оставленный навсегда удорожает каждую перерисовку.
            animation.finished.connect(
                lambda target=widget: target.setGraphicsEffect(None)
            )
        except Exception as exc:
            log(f"[SIMPLE] блок не проявлен: {exc}", "DEBUG")
            continue

        widget._simple_view_reveal = animation
        delay = order * REVEAL_STAGGER_MS
        if delay <= 0:
            start_managed_animation(animation)
        else:
            QTimer.singleShot(
                delay, lambda target=animation: start_managed_animation(target)
            )


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


def apply_simple_view(page, advanced: bool | None = None) -> None:
    """Показывает или прячет расширенные разделы страницы управления."""
    if advanced is None:
        try:
            from ui.navigation.schema import is_advanced_mode_enabled

            advanced = bool(is_advanced_mode_enabled())
        except Exception:
            advanced = True

    visible = bool(advanced)

    # Что именно появляется — нужно знать до показа: анимируем только
    # то, чего на экране не было. Уже видимое проявлять заново значит
    # моргать им на ровном месте.
    appearing = []
    if visible:
        for attr in (*HIDDEN_IN_SIMPLE_VIEW, *HIDDEN_SETTING_ROWS):
            widget = getattr(page, attr, None)
            if widget is not None and widget.isHidden():
                appearing.append(widget)

    for attr in HIDDEN_IN_SIMPLE_VIEW:
        _set_visible(page, attr, visible)
    for attr in HIDDEN_SETTING_ROWS:
        _set_visible(page, attr, visible)

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

    _collapse_dangling_spacings(page, visible)

    if appearing:
        _reveal(appearing)


__all__ = [
    "HIDDEN_IN_SIMPLE_VIEW",
    "HIDDEN_SETTING_ROWS",
    "apply_simple_view",
    "attach_advanced_button",
    "attach_theme_switch",
]
