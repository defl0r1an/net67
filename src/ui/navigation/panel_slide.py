"""Выезд панели разделов: раскрытие по размеру, а не сдвиг по месту.

Сторону выбирает panel_side, здесь — только движение. Разделение не
формальное: правило «слева панель приезжает справа налево» должно
проверяться без окна на экране, а анимация без окна не проверяется
никак.

## Почему не move()

Прежняя версия двигала панель методом move(). Это и была та поломка,
которую человек описывал словами «нажать расширенный, потом простой — и
всё ломается». Механика ошибки, замеренная, а не угаданная:

    старт             панель x = 0
    уходим в простой  панель x = -288   (анимация доехала)
    возвращаемся      панель x = -288   ожидалось 0

Панель лежит в QHBoxLayout окна. Раскладка расставляет виджеты сама, но
пропускает спрятанные — а панель как раз прячут сразу после
сворачивания. Позиция -288 остаётся на ней и при следующем раскрытии
становится новой точкой отсчёта: анимация честно едет «на 288 вправо от
-288», то есть опять в -288. В расширенном режиме слева получалась
пустая полоса в 288 пикселей без единого пункта.

Здесь анимируется размер, а не позиция. Ширину раскладка уважает: панель
раздвигает содержимое, вместо того чтобы наезжать на него, и накопить
смещение больше нечему.

## Почему не только размер

Одна ширина даёт эффект раздвигающейся шторки — движение есть, а жизни в
нём нет. Поэтому одновременно идут две вещи: ширина панели с ускорением
OutCubic и появление пунктов по очереди, с задержкой STAGGER_MS друг за
другом. Последнее и создаёт ощущение, что меню собирается на глазах.

Задержка маленькая намеренно: при двадцати пунктах общий хвост не должен
превышать длительность самого раскрытия, иначе последний пункт
проявляется, когда панель давно стоит на месте.

## Три вещи важнее красоты

Анимация обязана слушаться политики приложения: в Windows есть системный
переключатель «показывать анимацию», и людям, которые его выключили,
движение мешает. Поэтому старт идёт через start_managed_animation.

Панель обязана доезжать. Прерванная на середине, она оставит половину
интерфейса недоступной. Поэтому конечные значения выставляются и при
обрыве тоже.

Ссылку на анимацию нужно держать: локальная переменная соберётся
сборщиком мусора раньше, чем анимация доиграет, — классическая ловушка
Qt в Python.
"""

from __future__ import annotations

from ui.navigation.panel_side import get_side


#: Длительность раскрытия. 260 мс — движение читается как плавное, но не
#: воспринимается как задержка перед работой.
SLIDE_DURATION_MS = 260

#: Задержка между появлением соседних пунктов.
STAGGER_MS = 26

#: Сколько пунктов вступают по очереди. Дальше задержка перестаёт
#: читаться, а хвост анимации тянется дольше самого раскрытия.
STAGGER_LIMIT = 12

#: Длительность появления одного пункта.
ITEM_FADE_MS = 190

#: Где панель запоминает свой раскрытый размер.
_EXTENT_ATTR = "_net67_panel_extent"


def slide_property(side) -> bytes:
    """Что именно анимируем для этой стороны.

    Панель слева и справа раскрывается по ширине, сверху — по высоте.
    Свойство берём максимальное: минимальное правится отдельно, иначе
    setFixedWidth не даст размеру опуститься до нуля.
    """
    return b"maximumWidth" if get_side(side).axis == "x" else b"maximumHeight"


def compute_slide(side, *, width: int, height: int, expanding: bool):
    """Откуда и куда едет размер. Возвращает (начало, конец).

    Ноль — свёрнутое состояние, натуральный размер — раскрытое.
    """
    extent = int(width if get_side(side).axis == "x" else height)
    extent = max(0, extent)
    return (0, extent) if expanding else (extent, 0)


def _natural_extent(panel, side) -> int:
    """Размер панели в раскрытом виде.

    Запоминается на самой панели при первом сворачивании: после него
    ширина уже нулевая, и спросить её будет не у кого.
    """
    horizontal = get_side(side).axis == "x"

    stored = getattr(panel, _EXTENT_ATTR, None)
    if isinstance(stored, int) and stored > 0:
        return stored

    try:
        current = int(panel.width() if horizontal else panel.height())
    except Exception:
        current = 0

    if current <= 0:
        try:
            hint = panel.sizeHint()
            current = int(hint.width() if horizontal else hint.height())
        except Exception:
            current = 0

    if current > 0:
        setattr(panel, _EXTENT_ATTR, current)
    return current


def _release_size_constraint(panel, side) -> None:
    """Снимает жёсткий размер, иначе анимировать нечего.

    Панель задана через setFixedWidth, а он ставит и минимум, и максимум.
    Максимум мы анимируем, минимум не пустил бы размер ниже своего
    значения.
    """
    try:
        if get_side(side).axis == "x":
            panel.setMinimumWidth(0)
        else:
            panel.setMinimumHeight(0)
    except Exception:
        pass


def _restore_size_constraint(panel, side, extent: int) -> None:
    """Возвращает панели её постоянный размер после раскрытия."""
    try:
        if get_side(side).axis == "x":
            panel.setFixedWidth(int(extent))
        else:
            panel.setFixedHeight(int(extent))
    except Exception:
        pass


def _collapse_now(panel, side) -> None:
    """Ставит свёрнутое состояние без анимации."""
    try:
        if get_side(side).axis == "x":
            panel.setMinimumWidth(0)
            panel.setMaximumWidth(0)
        else:
            panel.setMinimumHeight(0)
            panel.setMaximumHeight(0)
    except Exception:
        pass


def apply_panel_state(panel, side, *, expanded: bool) -> None:
    """Ставит конечное состояние панели без анимации.

    Нужно на запуске окна: анимировать там нечего, а состояние выставить
    надо. Восстановление размера здесь обязательно — сворачивание
    оставляет панели нулевую ширину, и без этого она открылась бы пустой
    полосой.
    """
    if panel is None:
        return
    if expanded:
        _restore_size_constraint(panel, side, _natural_extent(panel, side))
    else:
        _collapse_now(panel, side)


def fade_items(panel, *, duration_ms: int = ITEM_FADE_MS):
    """Пункты меню вступают по очереди.

    Возвращает список запущенных анимаций. Вызывающему коду он нужен
    только для проверок: работать они будут и без него, ссылки лежат на
    самих пунктах.
    """
    from PyQt6.QtCore import QEasingCurve, QTimer, QVariantAnimation
    from PyQt6.QtWidgets import QGraphicsOpacityEffect

    from ui.animation_policy import are_animations_enabled, start_managed_animation

    if not are_animations_enabled():
        return []

    try:
        items = list(panel.items.values())
    except Exception:
        return []

    animations = []
    for order, item in enumerate(items):
        try:
            effect = QGraphicsOpacityEffect(item)
            effect.setOpacity(0.0)
            item.setGraphicsEffect(effect)

            animation = QVariantAnimation(item)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setDuration(int(duration_ms))
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.valueChanged.connect(
                lambda value, target=effect: target.setOpacity(float(value))
            )
            # Эффект снимаем после показа: он держит отдельный слой
            # отрисовки, и оставлять его на каждом пункте навсегда дорого.
            animation.finished.connect(lambda target=item: target.setGraphicsEffect(None))
        except Exception:
            continue

        item._net67_fade_animation = animation
        delay = min(order, STAGGER_LIMIT) * STAGGER_MS
        if delay <= 0:
            start_managed_animation(animation)
        else:
            QTimer.singleShot(
                delay, lambda target=animation: start_managed_animation(target)
            )
        animations.append(animation)

    return animations


def animate_panel(
    panel,
    side,
    *,
    expanding: bool,
    duration_ms: int = SLIDE_DURATION_MS,
    on_finished=None,
):
    """Раскрывает или сворачивает панель. Возвращает анимацию или None.

    None — не ошибка: панель просто окажется на месте сразу. Оформление
    не должно мешать работе программы.
    """
    if panel is None:
        return None

    try:
        from PyQt6.QtCore import QEasingCurve, QPropertyAnimation

        from ui.animation_policy import register_managed_animation, start_managed_animation
    except Exception:
        return None

    extent = _natural_extent(panel, side)
    if extent <= 0:
        return None

    start_value, end_value = compute_slide(
        side, width=extent, height=extent, expanding=expanding
    )
    prop = slide_property(side)

    def _settle() -> None:
        # Панель обязана доезжать даже при обрыве: застрявшая на
        # середине, она закроет половину содержимого навсегда.
        if expanding:
            _restore_size_constraint(panel, side, extent)
        else:
            _collapse_now(panel, side)
        if callable(on_finished):
            try:
                on_finished()
            except Exception:
                pass

    try:
        _release_size_constraint(panel, side)

        animation = QPropertyAnimation(panel, prop, panel)
        animation.setDuration(int(duration_ms))
        animation.setStartValue(int(start_value))
        animation.setEndValue(int(end_value))
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(_settle)
        # Ссылку держим на самой панели: локальная переменная соберётся
        # сборщиком мусора раньше, чем анимация доиграет.
        panel._net67_slide_animation = animation
        register_managed_animation(animation, int(duration_ms))

        if animation.duration() <= 0:
            # Анимации выключены человеком: ставим конечное состояние и
            # уходим, ничего не мигая.
            _settle()
            return animation

        start_managed_animation(animation)
        if expanding:
            fade_items(panel)
        return animation
    except Exception:
        _settle()
        return None


__all__ = [
    "ITEM_FADE_MS",
    "SLIDE_DURATION_MS",
    "STAGGER_LIMIT",
    "STAGGER_MS",
    "animate_panel",
    "apply_panel_state",
    "compute_slide",
    "fade_items",
    "slide_property",
]
