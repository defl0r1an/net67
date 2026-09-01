"""Блок, который разворачивается по нажатию на заголовок.

Нужен там, где содержимое требуется изредка, а места занимает много.
Первый такой случай — добавление подписки на странице VPN: поле ввода,
подсказка и две кнопки висели всегда, хотя ссылку вставляют один раз,
а потом только выбирают сервер из списка.

## Почему анимируется высота, а не прозрачность

Прозрачность прячет содержимое, но оставляет дыру в раскладке: блок
исчезает, а место под ним остаётся. Высота убирает и то, и другое,
причём соседние виджеты едут плавно, а не прыгают.

## Почему высота считается, а не задаётся

Содержимое у блоков разное, и число в коде пришлось бы править вслед за
каждым добавленным полем. `sizeHint` знает настоящую высоту, поэтому
она берётся у него — на каждом раскрытии заново, чтобы блок пережил и
смену шрифта, и перевод, и добавление строки.
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ui.accessibility import enable_keyboard_click, set_control_accessibility, set_state_text
from ui.theme_refresh import ThemeRefreshBinding


#: Сколько длится разворот. Меньше — движение не читается и выглядит
#: рывком, больше — человек успевает подумать, что интерфейс тормозит.
ANIMATION_MS = 180

#: Отступы карточки: внутренние поля и скругление.
CARD_PADDING = 14
CARD_RADIUS = 8


class CollapsibleSection(QWidget):
    """Заголовок-кнопка и содержимое, которое разворачивается под ним."""

    toggled = pyqtSignal(bool)

    def __init__(self, title: str, *, parent=None, expanded: bool = False):
        super().__init__(parent)

        self._expanded = bool(expanded)

        # Блок оформлен карточкой, а не голой строкой на фоне.
        #
        # Раньше заголовок и поле ввода висели прямо на странице, и было
        # непонятно, где блок начинается и где кончается: подсказка,
        # поле и две кнопки читались как отдельные, ничем не связанные
        # части страницы. Рамка со скруглением объединяет их в один
        # предмет, который сворачивается целиком.
        self.setObjectName("net67CollapsibleSection")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(CARD_PADDING, CARD_PADDING - 4, CARD_PADDING, CARD_PADDING - 4)
        root.setSpacing(0)

        self._header = _SectionHeader(title, parent=self)
        self._header.clicked.connect(self.toggle)
        root.addWidget(self._header)

        # Содержимое лежит в контейнере с обрезкой: во время анимации
        # виджеты не должны вылезать за пределы уменьшенной высоты.
        self._body = QFrame(self)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 8, 0, 0)
        self._body_layout.setSpacing(8)
        root.addWidget(self._body)

        self._animation = QPropertyAnimation(self._body, b"maximumHeight", self)
        self._animation.setDuration(ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.finished.connect(self._on_animation_finished)

        self._body.setMaximumHeight(16777215 if self._expanded else 0)
        self._header.set_expanded(self._expanded)
        self._sync_accessibility()

        self._apply_theme()
        # Карточка перекрашивается вместе с темой: цвета берутся из
        # токенов, и после смены темы их надо взять заново.
        self._theme_refresh = ThemeRefreshBinding(self, lambda *_a, **_kw: self._apply_theme())

    def _apply_theme(self) -> None:
        from ui.theme import get_theme_tokens

        tokens = get_theme_tokens()
        self.setStyleSheet(
            f"#net67CollapsibleSection {{"
            f" background: {tokens.surface_bg};"
            f" border: 1px solid {tokens.surface_border};"
            f" border-radius: {CARD_RADIUS}px;"
            f" }}"
        )
        self._header.apply_theme(tokens)

    # ── содержимое ────────────────────────────────────────────────────

    def add_widget(self, widget) -> None:
        self._body_layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._body_layout.addLayout(layout)

    @property
    def body(self) -> QFrame:
        return self._body

    def set_title(self, title: str) -> None:
        """Меняет заголовок. Нужен там, где блок один на несколько вкладок."""
        self._header.set_title(str(title))
        self._sync_accessibility()

    # ── состояние ─────────────────────────────────────────────────────

    def is_expanded(self) -> bool:
        return self._expanded

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool, *, animate: bool = True) -> None:
        expanded = bool(expanded)
        if expanded == self._expanded:
            return

        self._expanded = expanded
        self._header.set_expanded(expanded)
        self._sync_accessibility()

        target = self._content_height() if expanded else 0

        if not animate:
            self._animation.stop()
            self._body.setMaximumHeight(target if not expanded else 16777215)
            self.toggled.emit(expanded)
            return

        self._animation.stop()
        # Верхнюю границу снимаем только после разворота: пока она
        # стоит, содержимое обрезано, и это нужно для самой анимации.
        self._animation.setStartValue(self._body.maximumHeight() if expanded else self._content_height())
        self._animation.setEndValue(target)
        self._animation.start()
        self.toggled.emit(expanded)

    def _content_height(self) -> int:
        """Настоящая высота содержимого — вместе с отступами."""
        hint = self._body_layout.sizeHint().height()
        margins = self._body_layout.contentsMargins()
        return max(0, int(hint) + margins.top() + margins.bottom())

    def _on_animation_finished(self) -> None:
        if not self._expanded:
            return
        # Развёрнутый блок обязан подстраиваться под содержимое: если
        # оставить посчитанную высоту, добавленная позже строка окажется
        # обрезанной, а причину будут искать в самой строке.
        self._body.setMaximumHeight(16777215)

    def _sync_accessibility(self) -> None:
        state = "развёрнуто" if self._expanded else "свёрнуто"
        set_state_text(self._header, f"{self._header.title()}, {state}")


class _SectionHeader(QWidget):
    """Строка-заголовок: знак раскрытия и название."""

    clicked = pyqtSignal()

    def __init__(self, title: str, *, parent=None):
        super().__init__(parent)
        from qfluentwidgets import StrongBodyLabel

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._sign = StrongBodyLabel("▸", self)
        self._sign.setFixedWidth(14)
        self._sign.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._sign)

        self._title = StrongBodyLabel(str(title), self)
        layout.addWidget(self._title)
        layout.addStretch()

        # Подсказка справа: без неё непонятно, что строка нажимается.
        # «Развернуть» короче любого значка и не требует шрифта иконок.
        self._hint = StrongBodyLabel("Развернуть", self)
        layout.addWidget(self._hint)

        set_control_accessibility(
            self,
            name=str(title),
            description="Развернуть или свернуть блок",
        )
        enable_keyboard_click(self)

    def title(self) -> str:
        return self._title.text()

    def set_title(self, title: str) -> None:
        self._title.setText(str(title))
        set_control_accessibility(
            self,
            name=str(title),
            description="Развернуть или свернуть блок",
        )

    def set_expanded(self, expanded: bool) -> None:
        # Шеврон вместо плюса: он показывает не только «свёрнуто или
        # нет», но и куда поедет содержимое. Плюс со стороны читался
        # как «добавить ещё одну подписку», чего строка не делает.
        self._sign.setText("▾" if expanded else "▸")
        self._hint.setText("Свернуть" if expanded else "Развернуть")

    def apply_theme(self, tokens) -> None:
        """Приглушает значок и подсказку, оставляя название заметным."""
        muted = f"QLabel {{ color: {tokens.fg_muted}; background: transparent; }}"
        self._sign.setStyleSheet(muted)
        self._hint.setStyleSheet(
            f"QLabel {{ color: {tokens.fg_faint}; background: transparent;"
            f" font-size: 12px; font-weight: 400; }}"
        )
        self._title.setStyleSheet(f"QLabel {{ color: {tokens.fg}; background: transparent; }}")

    def enterEvent(self, event):  # noqa: N802 (Qt override)
        # Наведение подсвечивает подсказку — тот же приём, что у ссылок:
        # строка отвечает на курсор, значит на неё можно нажать.
        from ui.theme import get_theme_tokens

        tokens = get_theme_tokens()
        self._hint.setStyleSheet(
            f"QLabel {{ color: {tokens.accent_hex}; background: transparent;"
            f" font-size: 12px; font-weight: 400; }}"
        )
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 (Qt override)
        from ui.theme import get_theme_tokens

        self.apply_theme(get_theme_tokens())
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


__all__ = ["ANIMATION_MS", "CollapsibleSection"]
