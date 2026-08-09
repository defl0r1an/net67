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
    переходом сверху вниз, кольцо по краю и значок, который
    проворачивается при переключении.
    """

    class _RoundButton(base_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._net67_spin = 0.0
            self._net67_fill = "#42454d"
            self._net67_ring = "#a8a8a8"
            self._net67_glow = 0.0

        def minimumSizeHint(self):
            from PyQt6.QtCore import QSize

            return QSize(centering_size_hint_width(), HERO_BUTTON_SIZE)

        # ── свойства для анимаций ────────────────────────────────────
        def set_spin(self, value: float) -> None:
            self._net67_spin = float(value)
            self.update()

        def set_hero_colors(self, *, fill: str, ring: str) -> None:
            self._net67_fill = str(fill)
            self._net67_ring = str(ring)
            self.update()

        def set_glow(self, value: float) -> None:
            """Насколько ярко светится кольцо: 0 — покой, 1 — вспышка."""
            self._net67_glow = max(0.0, min(1.0, float(value)))
            self.update()

        def paintEvent(self, event):  # noqa: N802 (сигнатура Qt)
            from PyQt6.QtCore import QPointF, QRectF, Qt
            from PyQt6.QtGui import QColor, QPainter, QPen, QRadialGradient

            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            rect = QRectF(self.rect()).adjusted(3.0, 3.0, -3.0, -3.0)
            base = QColor(self._net67_fill)

            # Заливка со смещённым бликом: круг перестаёт быть плоским
            # пятном и читается как объём.
            gradient = QRadialGradient(
                QPointF(rect.center().x(), rect.top() + rect.height() * 0.28),
                rect.width() * 0.95,
            )
            gradient.setColorAt(0.0, base.lighter(128))
            gradient.setColorAt(0.55, base)
            gradient.setColorAt(1.0, base.darker(125))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawEllipse(rect)

            # Кольцо по краю. При нажатии оно вспыхивает — это и есть
            # тот отклик, которого человек не находил.
            ring = QColor(self._net67_ring)
            ring.setAlphaF(0.35 + 0.65 * self._net67_glow)
            pen = QPen(ring, 2.0 + 2.0 * self._net67_glow)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(1.0, 1.0, -1.0, -1.0))

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
    "TITLE_BUSY",
    "TITLE_RUNNING",
    "TITLE_STOPPED",
    "HeroControlCard",
    "build_hero_control_card",
    "make_round",
    "state_title",
]
