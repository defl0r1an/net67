"""Главный экран: крупная кнопка по центру и состояние под ней.

Раньше управление было строкой кнопок в левом верхнем углу, а состояние —
отдельной карточкой ниже. Человек читал их по очереди и складывал сам, и
на скриншотах регулярно выходило расхождение: кнопка предлагает
«Включить», а карточка пишет «net67 работает».

Здесь состояние одно и на виду: круглая кнопка в центре, под ней крупная
строка «Обход работает» или «Обход выключен», ниже — подробности мелким.
Складывать нечего.

Почему кнопок всё-таки две, а видно одну. Запуск и остановка — разные
действия с разными обработчиками, и остановка ещё делится на «только
движок» и «движок и программа». Сливать их в один виджет значило бы
переписывать всю логику страницы ради внешнего вида. Вместо этого обе
кнопки круглые, стоят в одном месте, и в каждый момент показана та, что
соответствует состоянию.

Заголовок состояния берётся из видимости кнопок, а не из отдельного
источника. Два независимых источника правды о том, работает ли обход, —
это ровно тот баг, от которого экран и переделывался.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget


#: Диаметр главной кнопки. Достаточно крупная, чтобы читаться с двух
#: метров, и не настолько, чтобы вытеснить всё остальное с экрана.
HERO_BUTTON_SIZE = 88

#: Заголовки состояния. Держим здесь, а не в вызывающем коде: строка под
#: кнопкой и есть главный ответ экрана на вопрос «работает или нет».
TITLE_RUNNING = "Обход работает"
TITLE_STOPPED = "Обход выключен"
TITLE_BUSY = "Меняем состояние…"


def state_title(*, start_visible: bool, stop_visible: bool) -> str:
    """Заголовок по видимости кнопок.

    Обе спрятаны — идёт переключение: показывать в этот момент любое из
    двух устойчивых состояний значит соврать на секунду.
    """
    if stop_visible and not start_visible:
        return TITLE_RUNNING
    if start_visible and not stop_visible:
        return TITLE_STOPPED
    return TITLE_BUSY


#: События, по которым пересчитывается заголовок.
#:
#: ShowToParent и HideToParent здесь обязательны, и это не перестраховка.
#: Qt шлёт Show только тогда, когда виджет действительно появился на
#: экране, — а у ребёнка ещё не показанного окна этого не происходит.
#: Hide при этом приходит всегда, и получалась асимметрия: спрятать
#: кнопку заголовок замечал, показать соседнюю — нет, и он навсегда
#: застревал на «Меняем состояние…». ToParent-события приходят на каждый
#: вызов show() и hide() независимо от состояния окна.
_VISIBILITY_EVENTS = (
    QEvent.Type.Show,
    QEvent.Type.Hide,
    QEvent.Type.ShowToParent,
    QEvent.Type.HideToParent,
)


class _VisibilityWatcher(QObject):
    """Следит за показом и скрытием кнопок и обновляет заголовок."""

    def __init__(self, on_change, parent=None):
        super().__init__(parent)
        self._on_change = on_change

    def eventFilter(self, obj, event):
        if event.type() in _VISIBILITY_EVENTS:
            try:
                self._on_change()
            except Exception:
                pass
        return False


class HeroControlCard(QWidget):
    """Карточка главного действия: кнопка, состояние, подробности."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_btn = None
        self._stop_btn = None
        self._title_label = None
        self._subtitle_label = None
        self._watcher = None

    def bind_buttons(self, start_btn, stop_btn) -> None:
        self._start_btn = start_btn
        self._stop_btn = stop_btn
        self._watcher = _VisibilityWatcher(self.refresh_state, self)
        for button in (start_btn, stop_btn):
            if button is not None:
                button.installEventFilter(self._watcher)
        self.refresh_state()

    def set_labels(self, title_label, subtitle_label) -> None:
        self._title_label = title_label
        self._subtitle_label = subtitle_label

    def refresh_state(self) -> None:
        if self._title_label is None:
            return
        # isHidden(), а не isVisible(). Второй отвечает «нет» у любого
        # виджета, чьё окно ещё не показано, — и на этапе сборки экрана
        # обе кнопки выглядели бы спрятанными, а заголовок навсегда
        # застревал на «Меняем состояние…».
        title = state_title(
            start_visible=bool(self._start_btn is not None and not self._start_btn.isHidden()),
            stop_visible=bool(self._stop_btn is not None and not self._stop_btn.isHidden()),
        )
        if self._title_label.text() != title:
            self._title_label.setText(title)

    def set_subtitle(self, text: str) -> None:
        if self._subtitle_label is not None:
            self._subtitle_label.setText(str(text or ""))


#: Размер значка внутри круглой кнопки.
HERO_ICON_SIZE = 32

#: Сколько едет цвет круга при смене состояния.
#:
#: Короче оборота значка (520 мс) намеренно: цвет должен договорить
#: раньше, чем закончится проворот, иначе два движения спорят за
#: внимание и переключение выглядит суетливым.
HERO_COLOR_MS = 280

#: Полный цикл «дыхания» круга, пока обход работает.
#:
#: Медленно намеренно. Быстрая пульсация на главном элементе экрана
#: читается как тревога, а нужно противоположное — «всё идёт, ничего
#: делать не надо».
HERO_PULSE_MS = 2600

#: Насколько должно измениться дыхание, чтобы перерисовывать круг.
#:
#: Дыхание идёт всё время работы обхода — часами. Без порога кнопка
#: перерисовывалась бы шестьдесят раз в секунду ради разницы, которой
#: на глаз нет.
HERO_PULSE_STEP = 0.02


def centering_size_hint_width(*, size: int = HERO_BUTTON_SIZE, icon_size: int = HERO_ICON_SIZE) -> int:
    """Ширина подсказки размера, при которой значок встаёт по центру.

    qfluentwidgets рисует значок по формуле x = 12 + (ширина - mw) // 2,
    где mw — minimumSizeHint().width(). С текстом «Запустить net67»
    подсказка шире круга, разность отрицательная, и значок уезжает за
    левый край: круг оставался пустым.

    Нам нужен x = (размер - значок) / 2. Подставляем и решаем:
    mw = значок + 24.
    """
    return int(icon_size) + 24


def make_round_button_class(base_cls):
    """Круглая кнопка на основе обычной: своя отрисовка и поворот значка.

    Подкласс, а не правка экземпляра: minimumSizeHint и paintEvent
    вызываются из C++, и присвоение метода объекту в PyQt туда не
    доходит.

    Рисуем сами, а не таблицей стилей. Плоский круг одного цвета человек
    назвал монотонным, и он прав: главный элемент экрана не отличался от
    обычной кнопки ничем, кроме размера. Здесь у круга есть заливка с
    переходом сверху вниз, светящийся кант по верхней кромке, кольцо по
    краю, ореол за кольцом, медленное дыхание на работающем обходе и
    значок, который проворачивается при переключении — вместе с бликом,
    обегающим кольцо.
    """

    class _RoundButton(base_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._net67_spin = 0.0
            self._net67_fill = "#42454d"
            self._net67_ring = "#a8a8a8"
            self._net67_glow = 0.0
            self._net67_pulse = 0.0
            # Показываемый цвет отдельно от заданного.
            #
            # `_net67_fill` — куда идём, `_shown` — где сейчас. Раньше
            # они были одним значением, и смена состояния меняла круг
            # мгновенно: только что серый, уже синий. Кадра перехода не
            # было, и главная кнопка экрана переключалась беднее, чем
            # тумблер в настройках.
            #
            # Разделение нужно ещё и для проверок: они читают заданный
            # цвет сразу после смены состояния и ждать анимацию не должны.
            self._net67_fill_shown = None
            self._net67_ring_shown = None
            self._net67_color_animation = None
            self._net67_color_target = None
            self._net67_pulse_animation = None
            self._net67_pulse_wanted = False

        def minimumSizeHint(self):
            from PyQt6.QtCore import QSize

            return QSize(centering_size_hint_width(), HERO_BUTTON_SIZE)

        # ── свойства для анимаций ────────────────────────────────────
        def set_spin(self, value: float) -> None:
            self._net67_spin = float(value)
            self.update()

        def set_hero_colors(self, *, fill: str, ring: str) -> None:
            """Задаёт цвет круга. Показываемый доезжает до него плавно."""
            from PyQt6.QtGui import QColor

            self._net67_fill = str(fill)
            self._net67_ring = str(ring)

            target_key = (self._net67_fill, self._net67_ring)
            if (
                target_key == self._net67_color_target
                and self._net67_color_animation is not None
            ):
                # Тот же цвет во время перехода к нему. Приходит на каждом
                # кадре просадки круга под нажатием: она пересчитывает
                # цвет заново. Перезапуск здесь растягивал бы переход
                # бесконечно, пока палец на кнопке.
                return
            self._net67_color_target = target_key

            target_fill = QColor(self._net67_fill)
            target_ring = QColor(self._net67_ring)
            start_fill = self._net67_fill_shown or target_fill
            start_ring = self._net67_ring_shown or target_ring

            def _snap() -> None:
                self._net67_fill_shown = target_fill
                self._net67_ring_shown = target_ring
                self._net67_color_animation = None
                self.update()

            if start_fill == target_fill and start_ring == target_ring:
                _snap()
                return

            try:
                from PyQt6.QtCore import QEasingCurve, QVariantAnimation

                from ui.animation_policy import (
                    are_animations_enabled,
                    start_managed_animation,
                )
            except Exception:
                _snap()
                return

            if not are_animations_enabled():
                _snap()
                return

            previous = self._net67_color_animation
            if previous is not None:
                # Второе переключение до конца первого: старую анимацию
                # надо снять, иначе два обработчика тянут цвет в разные
                # стороны и круг мерцает.
                try:
                    previous.stop()
                except Exception:
                    pass

            def _mix(first, second, ratio):
                return QColor(
                    int(round(first.red() + (second.red() - first.red()) * ratio)),
                    int(round(first.green() + (second.green() - first.green()) * ratio)),
                    int(round(first.blue() + (second.blue() - first.blue()) * ratio)),
                )

            def _step(value):
                ratio = float(value)
                self._net67_fill_shown = _mix(start_fill, target_fill, ratio)
                self._net67_ring_shown = _mix(start_ring, target_ring, ratio)
                self.update()

            animation = QVariantAnimation(self)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setDuration(HERO_COLOR_MS)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.valueChanged.connect(_step)
            animation.finished.connect(_snap)
            self._net67_color_animation = animation
            start_managed_animation(animation)
            if animation.duration() <= 0:
                _snap()

        def set_glow(self, value: float) -> None:
            """Насколько ярко светится кольцо: 0 — покой, 1 — вспышка."""
            self._net67_glow = max(0.0, min(1.0, float(value)))
            self.update()

        # ── дыхание работающего обхода ───────────────────────────────
        def set_pulse(self, value: float) -> None:
            self._net67_pulse = max(0.0, min(1.0, float(value)))
            self.update()

        def start_pulse(self) -> None:
            """Круг начинает медленно дышать: обход работает.

            Статичная кнопка одинаково выглядит и когда обход поднят, и
            когда программа зависла на полпути. Живое движение — самый
            дешёвый способ показать, что всё идёт.
            """
            self._net67_pulse_wanted = True
            self._sync_pulse()

        def stop_pulse(self) -> None:
            self._net67_pulse_wanted = False
            self._sync_pulse()

        def _sync_pulse(self) -> None:
            """Держит анимацию дыхания в согласии с состоянием и видимостью."""
            running = self._net67_pulse_animation is not None
            wanted = bool(self._net67_pulse_wanted) and not self.isHidden()

            if wanted and not running:
                self._start_pulse_animation()
            elif not wanted and running:
                self._stop_pulse_animation()

        def _start_pulse_animation(self) -> None:
            try:
                from PyQt6.QtCore import QEasingCurve, QVariantAnimation

                from ui.animation_policy import (
                    are_animations_enabled,
                    start_managed_animation,
                )
            except Exception:
                return

            if not are_animations_enabled():
                return

            animation = QVariantAnimation(self)
            animation.setStartValue(0.0)
            animation.setKeyValueAt(0.5, 1.0)
            animation.setEndValue(0.0)
            animation.setDuration(HERO_PULSE_MS)
            animation.setEasingCurve(QEasingCurve.Type.InOutSine)
            # Бесконечно: дыхание живёт ровно столько, сколько работает
            # обход, и останавливается сменой состояния, а не таймером.
            animation.setLoopCount(-1)
            animation.valueChanged.connect(self._on_pulse_value)
            self._net67_pulse_animation = animation
            start_managed_animation(animation)
            if animation.duration() <= 0:
                self._stop_pulse_animation()

        def _stop_pulse_animation(self) -> None:
            animation = self._net67_pulse_animation
            self._net67_pulse_animation = None
            if animation is not None:
                try:
                    animation.stop()
                except Exception:
                    pass
            if self._net67_pulse:
                self._net67_pulse = 0.0
                self.update()

        def _on_pulse_value(self, value) -> None:
            target = max(0.0, min(1.0, float(value)))
            if abs(target - self._net67_pulse) < HERO_PULSE_STEP:
                return
            self._net67_pulse = target
            self.update()

        def showEvent(self, event):  # noqa: N802 (сигнатура Qt)
            super().showEvent(event)
            self._sync_pulse()

        def hideEvent(self, event):  # noqa: N802 (сигнатура Qt)
            # Дышать за свёрнутым окном — греть процессор впустую.
            # Состояние при этом не теряется: вернут окно — вернётся
            # и дыхание, потому что решение хранится отдельно от
            # самой анимации.
            super().hideEvent(event)
            self._sync_pulse()

        # ── отрисовка ────────────────────────────────────────────────
        def paintEvent(self, event):  # noqa: N802 (сигнатура Qt)
            from PyQt6.QtCore import QPointF, QRectF, Qt
            from PyQt6.QtGui import (
                QBrush,
                QColor,
                QConicalGradient,
                QPainter,
                QPen,
                QRadialGradient,
            )

            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            rect = QRectF(self.rect()).adjusted(3.0, 3.0, -3.0, -3.0)
            # Рисуем показываемый цвет, а не заданный: между ними и живёт
            # переход. До первой смены состояния показываемого ещё нет.
            base = QColor(self._net67_fill_shown or QColor(self._net67_fill))
            ring_color = QColor(self._net67_ring_shown or QColor(self._net67_ring))
            breath = self._net67_pulse
            glow = self._net67_glow

            # Ореол за кольцом. Узкий — шире негде, круг занимает виджет
            # почти целиком, — но он снимает ощущение наклейки: у кнопки
            # появляется край, а не вырезанная граница.
            halo = QColor(ring_color)
            halo.setAlphaF(min(1.0, 0.10 + 0.18 * breath + 0.30 * glow))
            transparent = QColor(halo.red(), halo.green(), halo.blue(), 0)
            aura = QRadialGradient(rect.center(), rect.width() * 0.5 + 3.0)
            aura.setColorAt(0.86, transparent)
            aura.setColorAt(0.94, halo)
            aura.setColorAt(1.0, transparent)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QRectF(self.rect()))

            # Заливка со смещённым бликом: круг перестаёт быть плоским
            # пятном и читается как объём. Дыхание подмешивается в силу
            # блика, а не в цвет — иначе на работающем обходе менялся бы
            # сам акцент приложения.
            gradient = QRadialGradient(
                QPointF(rect.center().x(), rect.top() + rect.height() * 0.28),
                rect.width() * 0.95,
            )
            gradient.setColorAt(0.0, base.lighter(122 + int(round(20 * breath))))
            gradient.setColorAt(0.55, base)
            gradient.setColorAt(1.0, base.darker(125))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawEllipse(rect)

            # Светлый кант по верхней кромке изнутри. Одна дуга, а круг
            # из нарисованного пятна становится похож на предмет.
            rim = QColor(255, 255, 255)
            rim.setAlphaF(0.14 + 0.12 * breath)
            painter.setPen(QPen(rim, 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(rect.adjusted(2.4, 2.4, -2.4, -2.4), 35 * 16, 110 * 16)

            # Кольцо по краю. При нажатии оно вспыхивает — это и есть
            # тот отклик, которого человек не находил.
            ring = QColor(ring_color)
            ring.setAlphaF(min(1.0, 0.35 + 0.12 * breath + 0.53 * glow))
            ring_rect = rect.adjusted(1.0, 1.0, -1.0, -1.0)
            painter.setPen(QPen(ring, 2.0 + 2.0 * glow))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ring_rect)

            # Блик, обегающий кольцо вместе с проворотом значка. Своей
            # анимации у него нет — он берёт угол у прокрута, поэтому
            # появляется ровно на переключении и гаснет вместе с ним.
            spin = self._net67_spin % 360.0
            if spin:
                sweep = QConicalGradient(ring_rect.center(), -spin)
                spark = QColor(255, 255, 255, 200)
                faded = QColor(255, 255, 255, 0)
                sweep.setColorAt(0.0, spark)
                sweep.setColorAt(0.16, faded)
                sweep.setColorAt(0.84, faded)
                sweep.setColorAt(1.0, spark)
                painter.setPen(QPen(QBrush(sweep), 2.6))
                painter.drawEllipse(ring_rect)

            icon = self.icon()
            if icon is not None and not icon.isNull():
                painter.save()
                painter.translate(rect.center())
                painter.rotate(self._net67_spin)
                half = HERO_ICON_SIZE / 2.0
                icon.paint(
                    painter,
                    int(-half),
                    int(-half),
                    HERO_ICON_SIZE,
                    HERO_ICON_SIZE,
                )
                painter.restore()
            painter.end()

    _RoundButton.__name__ = f"Round{base_cls.__name__}"
    return _RoundButton


def make_round(button, *, size: int = HERO_BUTTON_SIZE, icon=None) -> None:
    """Делает кнопку круглой, не трогая её обработчики и текст.

    Текст остаётся у кнопки: его читают программы экранного доступа и
    им же пользуется существующая логика страницы. Скрыт он только
    визуально — иначе внутри круга оказалась бы обрезанная надпись.

    Прячем текст прозрачным цветом, а не нулевым кеглем: на
    `font-size: 0px` Qt ругается «Pixel size <= 0» на каждую перерисовку
    и засоряет вывод.
    """
    if button is None:
        return
    try:
        from PyQt6.QtCore import QSize

        button.setFixedSize(size, size)
        button.setIconSize(QSize(32, 32))
        button.setStyleSheet(
            button.styleSheet()
            + f"\nQPushButton {{ border-radius: {size // 2}px; padding: 0px;"
            " color: transparent; }"
        )
        _apply_contrasting_icon(button, icon)
    except Exception:
        pass


def _apply_contrasting_icon(button, icon) -> None:
    """Ставит значок цвета, противоположного цвету кнопки.

    Тонкость, которая стоила пустого белого круга. qfluentwidgets рисует
    значки по текущей теме: в тёмной — белыми. Но главная кнопка в
    тёмной теме сама почти белая, потому что тема осветляет акцент. Белый
    значок на белой кнопке не виден вовсе.

    Значит значку нужна тема, обратная теме приложения: в тёмной —
    светлая (значок чёрный), в светлой — тёмная (значок белый).
    """
    if icon is None:
        return
    try:
        from qfluentwidgets import Theme, isDarkTheme

        opposite = Theme.LIGHT if isDarkTheme() else Theme.DARK
        button.setIcon(icon.icon(opposite))
    except Exception:
        # Значок — не единственный признак кнопки: рядом крупная строка
        # состояния. Не получилось — кнопка остаётся рабочей.
        pass


def build_hero_control_card(
    *,
    start_btn,
    stop_winws_btn,
    stop_and_exit_btn,
    progress_bar,
    loading_label,
    title_label_cls,
    caption_label_cls,
    subtitle_text: str = "",
    parent=None,
) -> HeroControlCard:
    """Собирает главный экран вокруг уже созданных кнопок.

    Кнопки приходят готовыми снаружи: их обработчики, доступность и
    состояния уже настроены страницей, и пересоздавать их здесь значило
    бы дублировать логику, которая и так работает.
    """
    card = HeroControlCard(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 26, 16, 22)
    layout.setSpacing(10)
    layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

    buttons_row = QHBoxLayout()
    buttons_row.setSpacing(10)
    buttons_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    try:
        from qfluentwidgets import FluentIcon

        icons = {id(start_btn): FluentIcon.POWER_BUTTON, id(stop_winws_btn): FluentIcon.PAUSE}
    except Exception:
        icons = {}

    for button in (start_btn, stop_winws_btn):
        if button is not None:
            make_round(button, icon=icons.get(id(button)))
            buttons_row.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
    layout.addLayout(buttons_row)

    title_label = title_label_cls("")
    title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    layout.addWidget(title_label)

    subtitle_label = caption_label_cls(subtitle_text)
    subtitle_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    subtitle_label.setWordWrap(True)
    layout.addWidget(subtitle_label)

    if progress_bar is not None:
        layout.addWidget(progress_bar)
    if loading_label is not None:
        loading_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(loading_label)

    if stop_and_exit_btn is not None:
        extra_row = QHBoxLayout()
        extra_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        extra_row.addWidget(stop_and_exit_btn)
        layout.addLayout(extra_row)

    card.set_labels(title_label, subtitle_label)
    card.bind_buttons(start_btn, stop_winws_btn)
    return card


__all__ = [
    "HERO_BUTTON_SIZE",
    "HERO_COLOR_MS",
    "HERO_PULSE_MS",
    "TITLE_BUSY",
    "TITLE_RUNNING",
    "TITLE_STOPPED",
    "HeroControlCard",
    "build_hero_control_card",
    "make_round",
    "state_title",
]
