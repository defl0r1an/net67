"""Пересветка окна при смене темы: старый вид гаснет поверх нового.

Переключение светлой и тёмной темы происходило рывком, и рывок этот был
неаккуратным. Тема применяется не одним действием: qfluentwidgets
перекрашивает свои виджеты сразу, а локальные стили страниц пересчитывает
ThemeRefreshBinding — с задержкой в такт цикла событий и по отдельности
на каждую страницу. Между этими моментами окно успевает побывать
наполовину светлым, наполовину тёмным.

Снимок закрывает именно этот промежуток. Поверх окна кладётся картинка
того, как оно выглядело до переключения, и гаснет. Что бы ни творилось
под ней — перекраска идёт за кадром, а человек видит один плавный
переход.

Первую четверть снимок держится непрозрачным намеренно: к моменту, когда
он начнёт таять, перекраска уже прошла. Начни он гаснуть сразу — из-под
него проступила бы та самая полусобранная тема.

Задержка эта считается своей формулой, а не кривой Qt. Готовая кривая
растягивает и сжимает само время, и «держаться до 0.27» превращалось в
«держаться до первого кадра»: OutCubic успевает пройти четверть пути за
несколько миллисекунд. Здесь время идёт ровно, а форму задаёт функция
ниже — её и проверяют, без окна и без Qt.

Снимок не перехватывает мышь: под ним живое окно, и нажатие во время
перехода должно дойти до кнопки, а не пропасть.
"""

from __future__ import annotations

from log.log import log


#: Сколько живёт снимок старого вида.
#:
#: Вместе с задержкой ниже — чуть больше трети секунды. Короче видно
#: рывок, длиннее — окно кажется подвисшим.
CROSSFADE_MS = 340

#: Доля времени, которую снимок держится непрозрачным.
#:
#: Ровно затем, чтобы перекраска успела пройти под ним. Здесь это около
#: 90 мс — двух-трёх тактов цикла событий хватает с запасом.
CROSSFADE_HOLD = 0.27


def veil_opacity(progress: float) -> float:
    """Непрозрачность снимка в доле пути от 0 до 1.

    Сначала полка, потом спад с замедлением к концу: новая тема
    проступает быстро, а последние проценты снимка уходят мягко —
    резкий обрыв в конце заметен глазу как мигание.
    """
    value = max(0.0, min(1.0, float(progress)))
    if value <= CROSSFADE_HOLD:
        return 1.0
    left = 1.0 - (value - CROSSFADE_HOLD) / (1.0 - CROSSFADE_HOLD)
    return max(0.0, min(1.0, left * left))


def crossfade_theme_change(window) -> bool:
    """Кладёт поверх окна снимок текущего вида и гасит его.

    False — переход не понадобился или невозможен: окно не показано,
    анимации выключены, снимок не снялся. Во всех этих случаях тема
    просто применится как раньше, без картинки.
    """
    if window is None:
        return False

    try:
        from PyQt6.QtCore import Qt, QVariantAnimation
        from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel

        from ui.animation_policy import are_animations_enabled, start_managed_animation
    except Exception:
        return False

    if not are_animations_enabled():
        return False

    try:
        if not window.isVisible() or window.isMinimized():
            return False
        snapshot = window.grab()
        if snapshot.isNull():
            return False
    except Exception:
        return False

    _drop_previous_veil(window)

    try:
        veil = QLabel(window)
        veil.setObjectName("net67ThemeCrossfade")
        veil.setPixmap(snapshot)
        veil.setScaledContents(False)
        veil.setGeometry(window.rect())
        veil.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        effect = QGraphicsOpacityEffect(veil)
        effect.setOpacity(1.0)
        veil.setGraphicsEffect(effect)
        veil.raise_()
        veil.show()
    except Exception as exc:
        log(f"[THEME] снимок для перехода не лёг: {exc}", "DEBUG")
        return False

    window._net67_theme_veil = veil

    def _finish() -> None:
        _drop_previous_veil(window, only=veil)

    try:
        animation = QVariantAnimation(veil)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(CROSSFADE_MS)
        animation.valueChanged.connect(
            lambda value, target=effect: target.setOpacity(veil_opacity(value))
        )
        animation.finished.connect(_finish)
    except Exception as exc:
        log(f"[THEME] переход не запущен: {exc}", "DEBUG")
        _finish()
        return False

    veil._net67_animation = animation
    start_managed_animation(animation)
    if animation.duration() <= 0:
        _finish()
        return False
    return True


def _drop_previous_veil(window, *, only=None) -> None:
    """Снимает снимок с окна.

    ``only`` — снять именно этот и только если он ещё текущий. Без
    проверки быстрое переключение темы туда-обратно приводило бы к тому,
    что конец первого перехода убирает снимок второго, и второй переход
    обрывался бы на середине.
    """
    veil = getattr(window, "_net67_theme_veil", None)
    if veil is None:
        return
    if only is not None and veil is not only:
        return

    try:
        window._net67_theme_veil = None
    except Exception:
        pass

    try:
        veil.hide()
        veil.setParent(None)
        veil.deleteLater()
    except Exception:
        pass


__all__ = ["CROSSFADE_HOLD", "CROSSFADE_MS", "crossfade_theme_change", "veil_opacity"]
