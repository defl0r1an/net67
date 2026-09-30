"""Появление блоков волной: подъём и проявление одним эффектом.

## Почему не отступами

Сдвинуть виджет в раскладке можно только через отступы или move(), и оба
способа заставляют Qt пересчитывать геометрию на каждом кадре. Страница
настроек для этого слишком тяжёлая: там пять карточек с полутора
десятками строк, и пересчёт съедает кадры ровно тогда, когда мы обещаем
плавность.

Поэтому движение живёт в QGraphicsEffect. Эффект получает готовую
картинку виджета и рисует её со смещением — раскладка про это не знает
и не пересчитывается. Цена одна: отдельный слой отрисовки, и он снимается
сразу после показа.

## Почему один эффект, а не два

Прозрачность и сдвиг — это одно движение, а не два совпавших. Раздельные
QGraphicsOpacityEffect и анимация позиции дают два слоя и две анимации на
виджет; здесь одно свойство `progress`, из которого считается и то и
другое. Меньше объектов, и рассинхрону взяться неоткуда.

## Про волну

Волна получается не длительностью, а перекрытием: следующий блок
трогается с места раньше, чем предыдущий доехал. Поэтому задержка между
соседями заметно меньше длительности одного появления. Разница в
несколько десятков миллисекунд решает, читается это как волна или как
очередь.

## Про уход

Уход — не появление, пущенное задом наперёд. Волна идёт снизу вверх, а
не сверху вниз: тот же порядок читался бы как повтор, а не как
сворачивание. Кривая тоже другая — блок трогается медленно и уходит
быстро, потому что разглядывать уезжающее незачем.

Главное же в другом: прятать блок нужно в конце его собственного пути, а
не в конце всей волны. Иначе доехавшие блоки висят на экране лишние
полтораста миллисекунд, и пауза перед тем, как страница сомкнётся,
читается как подвисание.
"""

from __future__ import annotations

from log.log import log


#: Сколько длится появление одного блока.
#:
#: Заметно дольше прежних 220 мс. На коротком движении глаз видит
#: смену состояния, а не само движение, и «плавно» не получается.
REVEAL_MS = 320

#: Задержка между соседними блоками.
#:
#: Меньше длительности примерно в семь раз — за счёт этого блоки едут
#: внахлёст. Уравняй их, и волна распадётся на очередь.
REVEAL_STAGGER_MS = 45

#: Сколько блоков успевают встать в очередь.
#:
#: Дальше задержка не растёт. Десяток блоков по 45 мс — это почти
#: полсекунды до последнего, за которые человек уже отвёл взгляд и
#: увидит, как строка возникает на пустом месте посреди готовой страницы.
REVEAL_STAGGER_LIMIT = 8

#: На сколько пикселей блок поднимается, пока проявляется.
#:
#: Маленькая величина намеренно. Смысл сдвига — задать направление
#: движения, а не переместить блок; на большом расстоянии список
#: начинает прыгать, и вместо плавности получается суета.
REVEAL_RISE_PX = 14


#: Сколько длится уход одного блока.
#:
#: Чуть короче появления. Появление человек читает — он ждёт, что
#: покажут; уход он уже не разглядывает, и та же длительность
#: превращается в ожидание.
CONCEAL_MS = 280

#: Наименьшая длительность подхваченного движения.
#:
#: Остаток пути бывает в несколько процентов, и пропорциональная
#: длительность превращается в мигание. Ниже этого порога движение уже
#: не читается как движение.
MIN_TAKEOVER_MS = 90

#: Готовый класс эффекта, см. _effect_class.
_EFFECT_CLASS = None


def _effect_class():
    """Класс эффекта. Собирается лениво: наверху модуля QtWidgets не нужен.

    Модуль читают проверки, которым окно ни к чему, а QtWidgets тянет за
    собой графические библиотеки системы и падает там, где их нет.

    И собирается один раз. Новый класс на каждый вызов означал бы, что
    isinstance не узнаёт слой, поставленный прошлым движением, — а
    именно по нему подхват понимает, откуда продолжать.
    """
    global _EFFECT_CLASS
    if _EFFECT_CLASS is not None:
        return _EFFECT_CLASS

    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtWidgets import QGraphicsEffect

    class SlideFadeEffect(QGraphicsEffect):
        """Рисует виджет со сдвигом и прозрачностью по одному `progress`.

        Сдвиг задаётся вектором, а не числом: вверх уезжают строки
        настроек, вбок — экраны мастера, и разводить под это два похожих
        эффекта незачем.
        """

        def __init__(self, parent=None, dx: int = 0, dy: int = REVEAL_RISE_PX):
            super().__init__(parent)
            self._progress = 0.0
            self._dx = float(dx)
            self._dy = float(dy)

        def progress(self) -> float:
            return self._progress

        def setProgress(self, value: float) -> None:
            value = max(0.0, min(1.0, float(value)))
            if value != self._progress:
                self._progress = value
                self.update()

        def boundingRectFor(self, rect):
            # Запас с той стороны, откуда блок едет: пока он не доехал,
            # он нарисован мимо своего места, и без запаса Qt его обрежет.
            pad = 1.0
            left = min(0.0, self._dx) - pad
            right = max(0.0, self._dx) + pad
            top = min(0.0, self._dy) - pad
            bottom = max(0.0, self._dy) + pad
            return rect.adjusted(left, top, right, bottom)

        def draw(self, painter) -> None:
            result = self.sourcePixmap(
                Qt.CoordinateSystem.LogicalCoordinates,
                QGraphicsEffect.PixmapPadMode.PadToEffectiveBoundingRect,
            )
            # PyQt возвращает пару, но подстраховаться дешевле, чем
            # разбираться потом, почему экран пустой.
            if isinstance(result, tuple):
                pixmap, offset = result
            else:
                pixmap, offset = result, QPoint(0, 0)
            if pixmap.isNull():
                return

            left = 1.0 - self._progress
            painter.save()
            painter.setOpacity(self._progress)
            painter.drawPixmap(
                offset + QPoint(int(round(left * self._dx)), int(round(left * self._dy))),
                pixmap,
            )
            painter.restore()

    _EFFECT_CLASS = SlideFadeEffect
    return SlideFadeEffect


def _takeover(widget, effect_cls, *, dx: int, dy: int, default: float):
    """Готовит слой движения, подхватывая начатое.

    Возвращает (слой, откуда ехать, подхват ли это).

    Главное правило прерывания: новое движение начинается с того
    значения, которое сейчас на экране. Поэтому уже стоящий слой не
    снимается, а переиспользуется вместе со своим прогрессом — снять
    его значит вернуть блок в начало пути, то есть сделать ровно тот
    рывок, от которого всё и затевалось.
    """
    animation = getattr(widget, "_reveal_animation", None)
    # Поле обнуляем до остановки: по нему отложенный старт понимает, что
    # его уже не ждут.
    try:
        widget._reveal_animation = None
    except Exception:
        pass
    if animation is not None:
        try:
            animation.stop()
        except Exception:
            pass

    existing = None
    try:
        existing = widget.graphicsEffect()
    except Exception:
        existing = None

    if isinstance(existing, effect_cls):
        try:
            return existing, float(existing.progress()), True
        except Exception:
            pass

    effect = effect_cls(widget, dx, dy)
    effect.setProgress(default)
    widget.setGraphicsEffect(effect)
    return effect, float(default), False


def _takeover_duration(full_ms: int, distance: float) -> int:
    """Длительность на оставшийся кусок пути.

    Пропорция, а не полная длительность: иначе подхваченный на девяти
    десятых блок ползёт последние пиксели столько же, сколько ехал бы
    весь путь. Скорость при этом остаётся примерно прежней, и шва на
    месте подхвата не видно.
    """
    remaining = max(0.0, min(1.0, float(distance)))
    return max(int(MIN_TAKEOVER_MS), int(round(int(full_ms) * remaining)))


def _start_if_current(widget, animation) -> None:
    """Запускает отложенную анимацию, если её ещё ждут.

    Между постановкой таймера и его срабатыванием движение могли снять:
    человек переключил вид обратно, страница пересобралась. Слой к этому
    моменту уже удалён, и запуск бьёт по удалённому объекту — Qt роняет
    процесс с «wrapped C/C++ object has been deleted».

    Признак «ещё ждут» — та же анимация всё ещё числится за блоком.
    Снятие движения обнуляет это поле первым делом.
    """
    try:
        from ui.animation_policy import start_managed_animation
    except Exception:
        return

    try:
        if getattr(widget, "_reveal_animation", None) is not animation:
            return
    except Exception:
        # Блок удалён вместе со страницей — запускать нечего.
        return

    start_managed_animation(animation)


def order_by_position(widgets):
    """Расставляет блоки сверху вниз по их месту на экране.

    Порядок объявления к расположению отношения не имеет, и волна,
    пущенная по нему, идёт зигзагом. Координаты спрашиваем после того,
    как раскладка отработала: у только что показанного виджета они ещё
    нулевые.
    """
    measured = []
    for index, widget in enumerate(widgets):
        try:
            point = widget.mapTo(widget.window(), widget.rect().topLeft())
            measured.append(((point.y(), point.x(), index), widget))
        except Exception:
            measured.append(((0, 0, index), widget))

    measured.sort(key=lambda item: item[0])
    return [widget for _, widget in measured]


def reveal_widgets(
    widgets,
    *,
    duration_ms: int = REVEAL_MS,
    stagger_ms: int = REVEAL_STAGGER_MS,
    stagger_limit: int = REVEAL_STAGGER_LIMIT,
    distance: int = REVEAL_RISE_PX,
) -> None:
    """Проявляет блоки волной сверху вниз.

    Молча ничего не делает, если человек отключил анимации: блоки к
    этому моменту уже видимы, и без эффекта они просто на месте.
    """
    widgets = [w for w in (widgets or ()) if w is not None]
    if not widgets:
        return

    try:
        from PyQt6.QtCore import QEasingCurve, QTimer, QVariantAnimation

        from ui.animation_policy import are_animations_enabled, start_managed_animation
    except Exception:
        return

    if not are_animations_enabled():
        return

    try:
        effect_cls = _effect_class()
    except Exception as exc:
        log(f"[REVEAL] эффект недоступен: {exc}", "DEBUG")
        return

    for order, widget in enumerate(order_by_position(widgets)):
        try:
            effect, start, caught = _takeover(
                widget, effect_cls, dx=0, dy=distance, default=0.0
            )
            if start >= 1.0:
                # Блок уже на месте: ехать некуда, слой только мешает.
                widget.setGraphicsEffect(None)
                continue

            animation = QVariantAnimation(widget)
            animation.setStartValue(start)
            animation.setEndValue(1.0)
            animation.setDuration(_takeover_duration(duration_ms, 1.0 - start))
            # OutCubic тормозит к концу: блок подъезжает к месту, а не
            # прилетает в него. Пружинящие кривые пробовать не стоит —
            # на списке настроек перелёт читается как дрожь.
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.valueChanged.connect(
                lambda value, target=effect: target.setProgress(float(value))
            )
            # Слой снимаем после показа: оставленный навсегда, он
            # удорожает каждую последующую перерисовку виджета.
            animation.finished.connect(
                lambda target=widget: target.setGraphicsEffect(None)
            )
        except Exception as exc:
            log(f"[REVEAL] блок не проявлен: {exc}", "DEBUG")
            continue

        widget._reveal_animation = animation
        # Подхваченный блок в очередь не встаёт. Он уже в движении, и
        # задержка означала бы, что он замирает в воздухе и ждёт своей
        # очереди — пауза посреди движения заметнее, чем сбитая волна.
        delay = 0 if caught else min(order, int(stagger_limit)) * int(stagger_ms)
        if delay <= 0:
            start_managed_animation(animation)
        else:
            QTimer.singleShot(
                delay,
                lambda target=animation, owner=widget: _start_if_current(owner, target),
            )


def stop_motion(widget) -> None:
    """Снимает незаконченное движение с блока, ничего не пряча.

    Нужно на повторном переключении. Остановленная анимация Qt не шлёт
    finished, а значит не сработает и то, что подвешено на её конец:
    блок остался бы полупрозрачным навсегда, а уход — недоведённым.
    """
    if widget is None:
        return

    animation = getattr(widget, "_reveal_animation", None)
    # Поле обнуляем первым: по нему отложенный старт понимает, что его
    # уже не ждут. Сделай это после удаления слоя — и таймер, вставший
    # в очередь секунду назад, запустит анимацию поверх пустоты.
    try:
        widget._reveal_animation = None
    except Exception:
        pass
    if animation is not None:
        try:
            animation.stop()
        except Exception:
            pass
    try:
        widget.setGraphicsEffect(None)
    except Exception:
        pass


def conceal_widgets(
    widgets,
    *,
    on_finished=None,
    duration_ms: int = CONCEAL_MS,
    stagger_ms: int = REVEAL_STAGGER_MS,
    stagger_limit: int = REVEAL_STAGGER_LIMIT,
    distance: int = REVEAL_RISE_PX,
) -> bool:
    """Убирает блоки волной снизу вверх и прячет каждый в конце его пути.

    Возвращает False, если ухода не будет: блоков нет, анимации
    отключены, эффект не собрался. Тогда прятать обязан вызывающий, и
    сразу — молча оставить блоки на экране хуже, чем убрать их рывком.

    ``on_finished`` зовётся один раз, когда последний блок уже спрятан.
    Там смыкается раскладка, и делать это раньше нельзя: группы
    схлопнулись бы под ещё уезжающими строками.
    """
    widgets = [w for w in (widgets or ()) if w is not None]
    if not widgets:
        return False

    try:
        from PyQt6.QtCore import QEasingCurve, QTimer, QVariantAnimation

        from ui.animation_policy import are_animations_enabled, start_managed_animation
    except Exception:
        return False

    if not are_animations_enabled():
        return False

    try:
        effect_cls = _effect_class()
    except Exception as exc:
        log(f"[REVEAL] эффект недоступен: {exc}", "DEBUG")
        return False

    ordered = list(reversed(order_by_position(widgets)))
    started = 0
    last_delay = 0

    for order, widget in enumerate(ordered):
        try:
            effect, start, caught = _takeover(
                widget, effect_cls, dx=0, dy=distance, default=1.0
            )
            if start <= 0.0:
                # Блок уже уехал: остаётся только спрятать.
                _finish_conceal(widget)
                started += 1
                continue

            animation = QVariantAnimation(widget)
            animation.setStartValue(start)
            animation.setEndValue(0.0)
            animation.setDuration(_takeover_duration(duration_ms, start))
            # InCubic — зеркало появления: трогается медленно, уходит
            # быстро. OutCubic здесь давал бы долгий хвост у самого
            # исчезновения, и блок словно залипал бы на месте.
            animation.setEasingCurve(QEasingCurve.Type.InCubic)
            animation.valueChanged.connect(
                lambda value, target=effect: target.setProgress(float(value))
            )
            animation.finished.connect(
                lambda target=widget: _finish_conceal(target)
            )
        except Exception as exc:
            log(f"[REVEAL] блок не убран: {exc}", "DEBUG")
            continue

        widget._reveal_animation = animation
        # Подхваченный блок в очередь не встаёт, см. появление выше.
        delay = 0 if caught else min(order, int(stagger_limit)) * int(stagger_ms)
        last_delay = max(last_delay, delay)
        started += 1
        if delay <= 0:
            start_managed_animation(animation)
        else:
            QTimer.singleShot(
                delay,
                lambda target=animation, owner=widget: _start_if_current(owner, target),
            )

    if not started:
        return False

    if on_finished is not None:
        # Своим таймером, а не по finished последней анимации.
        #
        # Остановленная анимация finished не шлёт, и на повторном
        # переключении смыкание раскладки не случилось бы никогда.
        # Таймер приходит при любом исходе, а сомкнуть раскладку дважды
        # безвредно.
        try:
            QTimer.singleShot(last_delay + int(duration_ms) + 16, on_finished)
        except Exception:
            on_finished()

    return True


def _finish_conceal(widget) -> None:
    """Убирает слой и прячет блок, доехавший до конца."""
    if widget is None:
        return
    try:
        widget._reveal_animation = None
    except Exception:
        pass
    try:
        widget.setGraphicsEffect(None)
    except Exception:
        pass
    try:
        widget.setVisible(False)
    except Exception:
        pass


def slide_in(
    widget,
    *,
    dx: int = 0,
    dy: int = 0,
    duration_ms: int = REVEAL_MS,
) -> None:
    """Проявляет один виджет с приездом из заданной стороны.

    Тем же эффектом, что и волна. Разница только в том, что здесь один
    блок и очереди нет.
    """
    if widget is None:
        return

    try:
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation

        from ui.animation_policy import are_animations_enabled, start_managed_animation
    except Exception:
        return

    if not are_animations_enabled():
        return

    try:
        effect = _effect_class()(widget, dx, dy)
        effect.setProgress(0.0)
        widget.setGraphicsEffect(effect)

        animation = QVariantAnimation(widget)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(int(duration_ms))
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(
            lambda value, target=effect: target.setProgress(float(value))
        )
        animation.finished.connect(lambda target=widget: target.setGraphicsEffect(None))
    except Exception as exc:
        log(f"[REVEAL] экран не проявлен: {exc}", "DEBUG")
        return

    widget._reveal_animation = animation
    start_managed_animation(animation)

    if animation.duration() <= 0:
        # Анимации отключены человеком: показываем сразу и начисто.
        effect.setProgress(1.0)
        widget.setGraphicsEffect(None)


__all__ = [
    "CONCEAL_MS",
    "MIN_TAKEOVER_MS",
    "REVEAL_MS",
    "REVEAL_RISE_PX",
    "REVEAL_STAGGER_LIMIT",
    "REVEAL_STAGGER_MS",
    "conceal_widgets",
    "order_by_position",
    "reveal_widgets",
    "slide_in",
    "stop_motion",
]
