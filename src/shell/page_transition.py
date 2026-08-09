"""Перелистывание страниц: уходящая улетает, приходящая проявляется.

Мгновенная подмена содержимого читается как мигание: глаз не успевает
понять, что сменилось, и каждый переход ощущается рывком. Здесь переход
занимает пятую долю секунды и показывает направление — вниз по меню
страница уходит вверх, вверх по меню уходит вниз, как при перелистывании.

## Почему снимок, а не сама страница

Двигать уходящую страницу нельзя: QStackedWidget прячет её сразу, а
раскладка всё равно вернула бы ей своё место. Поэтому с неё снимается
снимок (`grab()`) и кладётся отдельным слоем поверх стопки. Слой не в
раскладке, ему можно менять и позицию, и прозрачность — и он ничего не
пересчитывает при движении, в отличие от живых виджетов.

Это же решает вопрос стоимости. Прежняя попытка анимировать содержимое
напрямую упиралась в перерасчёт раскладки на каждом кадре: страницы
настроек тяжёлые, и переход шёл рывками. Снимок — одна картинка, её
перерисовка стоит примерно ничего.

## Почему приходящая только проявляется

Ей движение не нужно: снимок над ней уже едет и уносит взгляд. Две
одновременно движущиеся плоскости в разные стороны читаются как
неисправность, а не как переход.
"""

from __future__ import annotations


#: Длительность перехода. Короче 150 мс движение не читается, длиннее
#: 260 мс — начинает восприниматься как задержка перед работой.
TRANSITION_MS = 200

#: На сколько уезжает снимок уходящей страницы. Немного: он должен
#: намекнуть на направление, а не улететь за край экрана.
TRAVEL_PX = 26

#: Порог площади, выше которого снимок не делается.
#:
#: grab() рисует страницу целиком в картинку, и на очень больших окнах
#: это заметная пауза. Четыре мегапикселя — это примерно 2560×1600;
#: выше остаётся простое проявление без снимка.
MAX_GRAB_AREA = 4_000_000


def travel_offset(*, forward: bool, distance: int = TRAVEL_PX) -> int:
    """Куда уезжает снимок уходящей страницы, в пикселях по вертикали.

    Вперёд по списку разделов — страница уходит вверх, назад — вниз.
    Знак вынесен в функцию, чтобы правило проверялось без окна.
    """
    return -int(distance) if forward else int(distance)


def _snapshot(widget):
    """Снимок страницы или None, если снимать нечего или слишком дорого."""
    if widget is None:
        return None
    try:
        width, height = int(widget.width()), int(widget.height())
    except Exception:
        return None
    if width <= 0 or height <= 0 or width * height > MAX_GRAB_AREA:
        return None
    try:
        return widget.grab()
    except Exception:
        return None


def animate_page_change(container, outgoing, incoming, *, forward: bool = True):
    """Проводит переход между страницами внутри контейнера.

    Возвращает список запущенных анимаций — вызывающему коду он нужен
    только для проверок. Ошибка здесь ничего не ломает: страница уже
    переключена, речь только об оформлении.
    """
    from PyQt6.QtCore import (
        QEasingCurve,
        QPoint,
        QPropertyAnimation,
        Qt,
        QVariantAnimation,
    )
    from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel

    from ui.animation_policy import are_animations_enabled, start_managed_animation

    if container is None or incoming is None:
        return []
    if not are_animations_enabled():
        return []

    animations = []

    pixmap = _snapshot(outgoing) if outgoing is not incoming else None
    if pixmap is not None:
        ghost = QLabel(container)
        ghost.setPixmap(pixmap)
        ghost.setGeometry(outgoing.geometry())
        ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        ghost.show()
        ghost.raise_()

        ghost_effect = QGraphicsOpacityEffect(ghost)
        ghost_effect.setOpacity(1.0)
        ghost.setGraphicsEffect(ghost_effect)

        start = ghost.pos()
        end = QPoint(start.x(), start.y() + travel_offset(forward=forward))

        move = QPropertyAnimation(ghost, b"pos", ghost)
        move.setDuration(TRANSITION_MS)
        move.setStartValue(start)
        move.setEndValue(end)
        move.setEasingCurve(QEasingCurve.Type.OutCubic)

        fade_out = QVariantAnimation(ghost)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setDuration(TRANSITION_MS)
        fade_out.valueChanged.connect(
            lambda value, target=ghost_effect: target.setOpacity(float(value))
        )
        # Слой обязан исчезнуть в любом случае: застрявший снимок
        # перекроет живую страницу и она перестанет отвечать на мышь.
        fade_out.finished.connect(ghost.deleteLater)

        container._net67_page_ghost = ghost
        for animation in (move, fade_out):
            start_managed_animation(animation)
            animations.append(animation)

        if move.duration() <= 0:
            ghost.deleteLater()

    incoming_effect = QGraphicsOpacityEffect(incoming)
    incoming_effect.setOpacity(0.0)
    incoming.setGraphicsEffect(incoming_effect)

    fade_in = QVariantAnimation(incoming)
    fade_in.setStartValue(0.0)
    fade_in.setEndValue(1.0)
    fade_in.setDuration(TRANSITION_MS)
    fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
    fade_in.valueChanged.connect(
        lambda value, target=incoming_effect: target.setOpacity(float(value))
    )
    # Эффект снимаем после перехода: он рисует страницу в отдельный слой,
    # и оставленный навсегда он удорожает каждую последующую перерисовку.
    fade_in.finished.connect(lambda target=incoming: target.setGraphicsEffect(None))

    incoming._net67_page_fade = fade_in
    start_managed_animation(fade_in)
    animations.append(fade_in)

    if fade_in.duration() <= 0:
        incoming.setGraphicsEffect(None)

    return animations


__all__ = [
    "MAX_GRAB_AREA",
    "TRANSITION_MS",
    "TRAVEL_PX",
    "animate_page_change",
    "travel_offset",
]
