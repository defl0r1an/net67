"""Карточки настроек в цвет оболочки.

Правая половина окна оставалась чужой по цвету, сколько бы стилей ей ни
задавали. Причина не в приоритете селекторов: `SettingCard`,
`CardWidget` и `SimpleCardWidget` из qfluentwidgets переопределяют
`paintEvent` и рисуют фон сами, кистью из своей палитры. Таблица стилей
до этой отрисовки не доходит вообще — она применяется к тому фону,
который виджет рисовал бы по умолчанию, а он его не рисует.

Замерено на пустой странице с одной карточкой:

    фон страницы  #212226   — наш
    карточка      #3a3c41   — их, при заданном #2f3137

Отсюда и ощущение, что правая часть «из другой программы»: она светлее
фона на треть тона и с другим подтоном.

Поэтому `paintEvent` заменяется целиком. Замена делает ровно одно —
заливает скруглённый прямоугольник цветом из нашей палитры, — и потому
переживает обновления библиотеки лучше, чем попытка подкрасить их
кисти: имена внутренних полей меняются от версии к версии, а
`paintEvent` есть всегда.

Наведение остаётся: у карточек-кнопок оно единственный признак того,
что по ним можно щёлкнуть.
"""

from __future__ import annotations


#: Классы, которые рисуют фон сами. Проверено обращением к __dict__:
#: остальные карточки библиотеки своего paintEvent не имеют и слушаются
#: обычной таблицы стилей.
_PAINTED_CLASSES = ("SettingCard", "CardWidget", "SimpleCardWidget")

#: Отметка на классе, чтобы не подменять отрисовку дважды.
_PATCH_FLAG = "_net67_card_paint"


def _card_colors():
    """Цвета карточки под текущую тему приложения."""
    from qfluentwidgets import isDarkTheme

    from shell.theme import palette

    return palette(bool(isDarkTheme()))


def _group_position(card) -> tuple[bool, bool, bool]:
    """Где карточка стоит в своей группе.

    Возвращает (в группе, первая, последняя). Не в группе — значит
    самостоятельная карточка, и рисуется она отдельным блоком.
    """
    try:
        import qfluentwidgets

        group_cls = qfluentwidgets.SettingCardGroup
    except Exception:
        return (False, True, True)

    parent = card.parent()
    while parent is not None and not isinstance(parent, group_cls):
        parent = parent.parent()
    if parent is None:
        return (False, True, True)

    # Соседей собираем по типу «карточка», а не по точному классу.
    #
    # Сравнение через type(card) разводило соседей по кучкам: строки с
    # кнопкой — PushSettingCard, строка с переключателем — другой класс,
    # и переключатель считал себя единственным в группе. На экране он
    # оказывался отдельной карточкой с зазором под общей — человек
    # ткнул стрелкой ровно в этот шов.
    painted = tuple(
        cls
        for cls in (getattr(qfluentwidgets, name, None) for name in _PAINTED_CLASSES)
        if cls is not None
    )

    try:
        siblings = [
            child
            for child in _cards_in_order(card.parent(), painted)
            if not child.isHidden()
        ]
        if card not in siblings:
            return (True, True, True)

        run = _adjacent_run(siblings, card)
        index = run.index(card)
        return (True, index == 0, index == len(run) - 1)
    except Exception:
        return (True, True, True)


#: Насколько строки могут отстоять друг от друга и всё ещё считаться
#: одной карточкой. Слитые строки стоят вплотную — раскладке задан
#: нулевой промежуток, — поэтому запас нужен только на округления.
BLOCK_GAP_PX = 6


def _adjacent_run(cards: list, card) -> list:
    """Строки, стоящие вплотную к этой — сверху и снизу.

    Одного родителя мало. В расширенном виде страница управления
    показывает у той же группы вторую пачку строк под своим заголовком
    «Дополнительные настройки». Родитель у них общий, и «Автозапуск
    net67» считал себя первой строкой из четырёх: низ не скруглялся, под
    ним рисовалась разделительная черта — и одинокая карточка выглядела
    обрезанной ровно по нижнему краю.

    Признак «одна карточка» — не родство, а отсутствие зазора: между
    слитыми строками его нет вовсе, а заголовок раздела разводит их на
    десятки пикселей.
    """
    index = cards.index(card)

    start = index
    while start > 0:
        upper = cards[start - 1]
        if cards[start].y() - (upper.y() + upper.height()) > BLOCK_GAP_PX:
            break
        start -= 1

    end = index
    while end < len(cards) - 1:
        lower = cards[end + 1]
        if lower.y() - (cards[end].y() + cards[end].height()) > BLOCK_GAP_PX:
            break
        end += 1

    return cards[start : end + 1]


def _cards_in_order(host, painted) -> list:
    """Карточки хозяина сверху вниз.

    Порядок берём по положению на экране, а не по раскладке. Раскладка у
    SettingCardGroup своя — ExpandLayout, — и обход её через itemAt
    отдавал пустоту: каждая строка считала себя единственной в группе и
    рисовалась отдельной карточкой. Положение же есть у любого виджета
    независимо от того, кто им управляет, и именно оно решает, какая
    строка первая и какая последняя.
    """
    if host is None:
        return []

    cards = [child for child in host.children() if isinstance(child, painted)]
    try:
        cards.sort(key=lambda widget: widget.y())
    except Exception:
        pass
    return cards


def _collapse_group_spacing(card) -> None:
    """Убирает промежутки между строками одной группы.

    Строки должны сливаться в одну карточку, а между ними по умолчанию
    стоит зазор. Раскладка группы правится один раз: повторные вызовы
    ничего не меняют, а проверять флаг дешевле, чем гадать, когда
    группа окончательно собрана.
    """
    parent = card.parent()
    if parent is None:
        return

    # Карточки лежат не в основной раскладке группы, а в отдельной
    # cardLayout — своей у qfluentwidgets. Правя только parent.layout(),
    # мы убирали не тот промежуток: замер показывал упрямые два пикселя
    # между строками, и шов светился фоном страницы.
    layouts = [parent.layout(), getattr(parent, "cardLayout", None)]
    for layout in layouts:
        if layout is None or getattr(layout, "_net67_tight", False):
            continue
        try:
            layout.setSpacing(0)
            layout._net67_tight = True
        except Exception:
            continue


def _make_paint_event():
    """Собирает обработчик отрисовки, общий для всех карточек.

    Строки внутри группы рисуются как одна карточка: скругление только у
    первой и последней, между ними тонкая черта. Раньше каждая строка
    была отдельным блоком с собственным фоном и зазором, и пять
    переключателей подряд читались как список без структуры.

    Заливаем строго по прямоугольнику виджета, без вылета за края.
    Первая попытка складывала путь из скруглённого прямоугольника и двух
    накладок по краям — на экране это дало светлые полосы под каждой
    строкой: накладки рисовались поверх соседей. Здесь вместо накладок
    обрезка: путь пересекается с собственным прямоугольником строки.
    """
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen

    from shell.theme import CARD_RADIUS

    def paintEvent(self, event) -> None:  # noqa: N802 (сигнатура Qt)
        colors = _card_colors()

        hovered = False
        try:
            hovered = bool(self.underMouse() and self.isEnabled())
        except Exception:
            hovered = False

        in_group, first, last = _group_position(self)
        if in_group:
            _collapse_group_spacing(self)

        radius = float(CARD_RADIUS)
        rect = QRectF(self.rect())

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.surface_hover if hovered else colors.surface))

        if not in_group or (first and last):
            painter.drawRoundedRect(rect, radius, radius)
        else:
            # Скругляем только внешние углы: на стыке строк засечки
            # выдали бы, что карточка собрана из кусков.
            #
            # Прямоугольник растягиваем за тот край, который скруглять не
            # надо, и обрезаем по своей области. Так заливка гарантированно
            # не выходит за пределы строки.
            grown = QRectF(rect)
            if not first:
                grown.setTop(rect.top() - radius)
            if not last:
                grown.setBottom(rect.bottom() + radius)

            path = QPainterPath()
            path.addRoundedRect(grown, radius, radius)
            clip = QPainterPath()
            clip.addRect(rect)
            painter.drawPath(path.intersected(clip))

        # Черта между строками. У последней её нет: она рисовалась бы по
        # самому краю карточки и читалась как обрезка.
        if in_group and not last:
            painter.setPen(QPen(QColor(colors.border), 1))
            inset = 16.0
            line_y = int(rect.bottom()) - 1
            painter.drawLine(
                int(rect.left() + inset), line_y, int(rect.right() - inset), line_y
            )
        painter.end()

    return paintEvent


def install_card_painting() -> tuple[str, ...]:
    """Подменяет отрисовку карточек. Возвращает имена изменённых классов.

    Вызывается один раз при запуске. Повторный вызов ничего не делает:
    классы помечаются, и накладывать обработчик поверх собственной же
    замены незачем.

    Сбой здесь не должен ронять приложение: без замены карточки просто
    останутся прежнего цвета, всё остальное будет работать.
    """
    try:
        import qfluentwidgets

        paint_event = _make_paint_event()
    except Exception:
        return ()

    patched: list[str] = []
    for name in _PAINTED_CLASSES:
        cls = getattr(qfluentwidgets, name, None)
        # Отметку ищем в самом классе, а не через getattr: у наследника
        # она нашлась бы у родителя, и он остался бы со своим paintEvent.
        # Именно так SimpleCardWidget проскакивал мимо замены —
        # он наследник CardWidget, но рисует себя сам.
        if cls is None or cls.__dict__.get(_PATCH_FLAG):
            continue
        try:
            cls.paintEvent = paint_event
            setattr(cls, _PATCH_FLAG, True)
        except Exception:
            continue
        patched.append(name)

    return tuple(patched)


__all__ = ["install_card_painting"]
