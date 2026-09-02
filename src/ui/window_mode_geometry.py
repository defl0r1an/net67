"""Размер окна под простой и расширенный вид.

В простом виде в боковой панели два пункта, а на странице — кнопка
«Включить», статус и настройки программы. В окне расширенного режима под
этим оставалась половина экрана пустоты.

Модуль меняет только размер: ничего в интерфейс не добавляется.

## Почему размер едет, а не прыгает

Смена режима — единственное место, где окно меняет размер само, без
руки человека. Мгновенный скачок на четыреста пикселей читается как сбой
отрисовки: только что окно было одно, стало другое, промежутка не было.

## Про минимальный размер и порядок

Минимум и текущий размер нельзя ставить в одном порядке для роста и для
сжатия, и это не мелочь.

Растущему окну минимум ставим в конце. Поставь его первым — Qt тут же
растянет окно до него, и анимировать станет нечего: она отработает по
уже готовому размеру.

Сжимающемуся, наоборот, в начале. Минимум прежнего режима обрезал бы
каждый кадр, и окно застряло бы на ширине простого вида плюс старый
минимум.
"""

from __future__ import annotations

from config.window_metrics import get_min_size_for_mode, get_window_size_for_mode
from log.log import log


#: Сколько едет окно при смене режима.
#:
#: Короче волны блоков: в простой вид окно сжимается уже после того, как
#: они уехали, и держать человека ещё треть секунды не за чем.
RESIZE_MS = 260


def _apply_min_size(window, min_width: int, min_height: int) -> bool:
    try:
        window.setMinimumSize(int(min_width), int(min_height))
        return True
    except Exception as exc:
        log(f"[WINDOW] не удалось задать минимальный размер: {exc}", "DEBUG")
        return False


def animate_window_size_for_mode(window, advanced: bool, *, on_finished=None) -> bool:
    """Плавно подгоняет размер окна под режим.

    False — движения не будет: окно развёрнуто, анимации отключены,
    размер уже нужный. Тогда размер ставит apply_window_size_for_mode,
    как раньше, и вызывающий обязан её позвать: молча оставить окно
    прежнего размера хуже, чем поменять его рывком.
    """
    if window is None:
        return False

    advanced = bool(advanced)

    # Развёрнутое окно не трогаем: пользователь сам его развернул.
    try:
        if bool(window.isMaximized()) or bool(window.isFullScreen()):
            return False
    except Exception:
        pass

    try:
        from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSize

        from ui.animation_policy import are_animations_enabled, start_managed_animation
    except Exception:
        return False

    if not are_animations_enabled():
        return False

    min_width, min_height = get_min_size_for_mode(advanced)
    width, height = get_window_size_for_mode(advanced)

    try:
        current = window.size()
    except Exception:
        return False

    target = QSize(int(width), int(height))
    if current == target:
        # Ехать некуда, но минимум мог остаться от прежнего режима.
        _apply_min_size(window, min_width, min_height)
        if on_finished is not None:
            on_finished()
        return True

    growing = target.width() > current.width() or target.height() > current.height()
    if not growing and not _apply_min_size(window, min_width, min_height):
        return False

    previous = getattr(window, "_net67_mode_resize", None)
    if previous is not None:
        # Второе переключение до конца первого: старую анимацию надо
        # снять, иначе две тянут размер в разные стороны.
        try:
            previous.stop()
        except Exception:
            pass

    settled = []

    def _settle() -> None:
        if settled:
            return
        settled.append(True)
        try:
            window._net67_mode_resize = None
        except Exception:
            pass
        if growing:
            _apply_min_size(window, min_width, min_height)
        if on_finished is not None:
            on_finished()

    try:
        animation = QPropertyAnimation(window, b"size", window)
        animation.setStartValue(current)
        animation.setEndValue(target)
        animation.setDuration(RESIZE_MS)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(_settle)
    except Exception as exc:
        log(f"[WINDOW] размер окна не анимирован: {exc}", "DEBUG")
        return False

    try:
        window._net67_mode_resize = animation
    except Exception:
        pass

    start_managed_animation(animation)

    if animation.duration() <= 0:
        # Анимации выключили между проверкой и запуском.
        try:
            window.resize(target)
        except Exception:
            pass
        _settle()

    log(f"[WINDOW] размер под режим advanced={advanced}: {width}x{height}", "DEBUG")
    return True


def apply_window_size_for_mode(window, advanced: bool, *, resize: bool = True) -> None:
    """Ставит минимальный и текущий размер окна под режим.

    resize=False на старте: там размер восстанавливает
    WindowGeometryRuntime из сохранённой геометрии, и перебивать его
    сразу после запуска — значит терять размер, который пользователь
    выставил руками.
    """
    if window is None:
        return

    advanced = bool(advanced)
    min_width, min_height = get_min_size_for_mode(advanced)

    if not _apply_min_size(window, min_width, min_height):
        return

    if not resize:
        return

    # Развёрнутое окно не трогаем: пользователь сам его развернул.
    try:
        if bool(window.isMaximized()) or bool(window.isFullScreen()):
            return
    except Exception:
        pass

    width, height = get_window_size_for_mode(advanced)
    try:
        window.resize(width, height)
        log(f"[WINDOW] размер под режим advanced={advanced}: {width}x{height}", "DEBUG")
    except Exception as exc:
        log(f"[WINDOW] не удалось изменить размер окна: {exc}", "DEBUG")


__all__ = ["RESIZE_MS", "animate_window_size_for_mode", "apply_window_size_for_mode"]
