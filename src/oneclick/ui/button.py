# oneclick/ui/button.py
"""Главная кнопка «Включить» с состояниями.

Оркестратор делает блокирующие вызовы — проверку целостности DNS и опрос
доменов по сети. Выполнять их в UI-потоке нельзя: окно замёрзнет на
десятки секунд. Поэтому вся работа уходит в QThread, а интерфейс
обновляется по сигналам.
"""

from __future__ import annotations

import time as _time

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, PrimaryPushButton

from log.log import log
from oneclick.state import OneClickState
from ui.accessibility import set_control_accessibility, set_state_text
from ui.theme import get_theme_tokens


# Текст кнопки. Он же читается программами экранного доступа, поэтому
# «Включить» без дополнения не годится: непонятно, что именно включаем.
_BUTTON_TEXT = {
    OneClickState.OFF: "Включить обход",
    OneClickState.PREPARING: "Подготовка...",
    OneClickState.CHECKING: "Проверка...",
    OneClickState.RUNNING: "Выключить обход",
    OneClickState.ERROR: "Повторить",
}

_STATE_TEXT = {
    OneClickState.OFF: "Обход выключен",
    OneClickState.PREPARING: "Запускаем...",
    OneClickState.CHECKING: "Проверяем доступность",
    OneClickState.RUNNING: "Обход работает",
    OneClickState.ERROR: "Не удалось запустить обход",
}

def _hero_icon(state=None):
    """Значок для круга. None — если библиотека значков недоступна.

    В работающем состоянии значка нет вовсе: там идёт отсчёт времени,
    и значок с цифрами в круге не уживается.
    """
    if state is OneClickState.RUNNING:
        return None
    try:
        from qfluentwidgets import FluentIcon

        return FluentIcon.POWER_BUTTON
    except Exception:
        return None


def _refresh_hero_icon(button, state) -> None:
    try:
        from PyQt6.QtGui import QIcon

        from ui.widgets.hero_control import _apply_contrasting_icon

        icon = _hero_icon(state)
        if icon is None:
            button.setIcon(QIcon())
            return
        _apply_contrasting_icon(button, icon)
    except Exception:
        # Значок — не единственный признак: под кругом крупная строка
        # состояния. Не получилось — кнопка остаётся рабочей.
        pass


#: Ширина колонки с подписями под кнопкой.
#:
#: Раскладка выровнена по центру, и метка без явной ширины сжимается до
#: ширины круга — 88 пикселей. Сообщение о переадресации в Telegram
#: рвалось там по два слова в строку. 420 — примерно шестьдесят знаков в
#: строке, то есть комфортная длина для чтения.
TEXT_COLUMN_WIDTH = 420


#: В этих состояниях кнопка занята и нажатие игнорируется.
_BUSY = (OneClickState.PREPARING, OneClickState.CHECKING)


class _OneClickWorker(QThread):
    """Выполняет включение или выключение вне UI-потока."""

    progress = pyqtSignal(object, str)
    finished_with = pyqtSignal(object, str)

    def __init__(self, *, enable: bool, runtime_feature, parent=None):
        super().__init__(parent)
        self._enable = bool(enable)
        self._runtime_feature = runtime_feature

    def run(self) -> None:
        try:
            from oneclick.deps import build_oneclick_deps
            from oneclick.runner import OneClickRunner
            from wizard.apply import build_request_from_settings

            deps = build_oneclick_deps(
                runtime_feature=self._runtime_feature,
                report=lambda state, message: self.progress.emit(state, message),
            )
            runner = OneClickRunner(deps)

            if self._enable:
                outcome = runner.enable(build_request_from_settings())
            else:
                outcome = runner.disable()

            self.finished_with.emit(outcome.state, outcome.message)
        except Exception as exc:
            log(f"Оркестратор «одной кнопки»: {exc}", "❌ ERROR")
            self.finished_with.emit(OneClickState.ERROR, f"{type(exc).__name__}: {exc}")


class OneClickButton(QWidget):
    """Крупная кнопка запуска с понятным состоянием под ней."""

    stateChanged = pyqtSignal(object)

    def __init__(self, parent=None, *, get_runtime_feature=None):
        super().__init__(parent)
        self._get_runtime_feature = get_runtime_feature
        self._state = OneClickState.OFF
        self._worker: _OneClickWorker | None = None

        # Главный экран: круг по центру, состояние крупной строкой под
        # ним. Раньше кнопка стояла слева, а состояние текстом справа, и
        # рядом жила ещё карточка «Статус работы» — три места про одно и
        # то же, которые регулярно расходились.
        from ui.widgets.hero_control import HERO_BUTTON_SIZE, make_round, make_round_button_class

        self._hero_size = HERO_BUTTON_SIZE

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 22, 0, 10)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        button_cls = make_round_button_class(PrimaryPushButton)
        self.button = button_cls(_BUTTON_TEXT[OneClickState.OFF])
        self.button.clicked.connect(self._on_clicked)
        make_round(self.button, size=HERO_BUTTON_SIZE, icon=_hero_icon())
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)

        # Ширина колонки под подписями. Раскладка выровнена по центру, и
        # без явной ширины метка сжимается до ширины круга — 88 пикселей.
        # Строка «Сейчас откроется Telegram и предложит включить прокси
        # net67 — подтвердите в его окне» рвалась там по два слова в
        # строку и вылезала за пределы колонки.
        self.state_label = BodyLabel(_STATE_TEXT[OneClickState.OFF])
        self.state_label.setWordWrap(True)
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.state_label.setFixedWidth(TEXT_COLUMN_WIDTH)
        layout.addWidget(self.state_label, 0, Qt.AlignmentFlag.AlignHCenter)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.detail_label.setFixedWidth(TEXT_COLUMN_WIDTH)
        layout.addWidget(self.detail_label, 0, Qt.AlignmentFlag.AlignHCenter)

        # Сколько защита уже работает. Отсчёт идёт от момента входа в
        # состояние RUNNING, а не от запуска программы: человека
        # интересует именно время работы обхода.
        #
        # Время рисуется внутри самого круга, а не строкой под ним:
        # просили «прям на кнопке». Пока обход работает, значок
        # уступает место цифрам — иначе в круге диаметром 88 пикселей
        # рядом не помещается ничего читаемого, а о том, что нажатие
        # выключает, говорит крупная строка состояния ниже.
        self.uptime_label = QLabel("", self.button)
        self.uptime_label.setObjectName("net67Uptime")
        self.uptime_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.uptime_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.uptime_label.setGeometry(0, 0, HERO_BUTTON_SIZE, HERO_BUTTON_SIZE)
        self.uptime_label.hide()

        self._running_since: float | None = None
        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(1000)
        self._uptime_timer.timeout.connect(self._refresh_uptime)

        # Отклик на нажатие: круг проседает и возвращается. Человек
        # просил чувствовать удар по кнопке — цвета для этого мало,
        # потому что цвет меняется уже по факту запуска, через секунды.
        self._hero_size = HERO_BUTTON_SIZE
        self._press_animation = None
        self.button.pressed.connect(lambda: self._pulse(HERO_BUTTON_SIZE - 8))
        self.button.pressed.connect(lambda: self._glow(1.0))
        self.button.released.connect(lambda: self._pulse(HERO_BUTTON_SIZE))
        self.button.released.connect(lambda: self._glow(0.0))
        self._spin_animation = None
        self._glow_animation = None

        self._apply_theme()
        self._apply_state(OneClickState.OFF, "")

    # ──────────────────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        tokens = get_theme_tokens()
        self.detail_label.setStyleSheet(
            f"QLabel {{ color: {tokens.fg_muted}; font-size: 12px; }}"
        )

    def refresh_theme(self) -> None:
        self._apply_theme()
        self._apply_state(self._state, self.detail_label.text())

    @property
    def state(self) -> OneClickState:
        return self._state

    @staticmethod
    def format_uptime(seconds: float) -> str:
        """Время работы словами часов, минут и секунд.

        Секунды показываем всегда: без них первые минуты выглядят
        застывшими, и человек не понимает, идёт ли отсчёт.
        """
        total = max(0, int(seconds))
        hours, rest = divmod(total, 3600)
        minutes, secs = divmod(rest, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def _refresh_uptime(self) -> None:
        if self._running_since is None:
            self.uptime_label.setText("")
            return
        self.uptime_label.setText(self.format_uptime(_time.monotonic() - self._running_since))

    def _pulse(self, target: int) -> None:
        """Плавно меняет диаметр круга под нажатием.

        Меняем именно фиксированный размер, а не геометрию: кнопка живёт
        в раскладке, и та немедленно вернула бы ей прежние координаты.
        Раскладка выровнена по центру, поэтому круг проседает симметрично.
        """
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation

        from ui.animation_policy import start_managed_animation

        target = int(target)
        if target == self._hero_size:
            return

        if self._press_animation is not None:
            self._press_animation.stop()

        animation = QVariantAnimation(self)
        animation.setStartValue(int(self._hero_size))
        animation.setEndValue(target)
        animation.setDuration(110)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(self._set_hero_size)
        self._press_animation = animation
        start_managed_animation(animation)
        # Если анимации выключены, длительность обнуляется и кадров не
        # будет вовсе — размер тогда ставим сами.
        if animation.duration() <= 0:
            self._set_hero_size(target)

    def _spin(self) -> None:
        """Проворот значка при переключении.

        Полный оборот, а не полповорота: обход либо включён, либо нет,
        и значок должен вернуться в то же положение. Половинчатый
        поворот оставлял бы кнопку в двух разных видах для одного и
        того же состояния.
        """
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation

        from ui.animation_policy import start_managed_animation

        if self._spin_animation is not None:
            self._spin_animation.stop()

        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(360.0)
        animation.setDuration(520)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.valueChanged.connect(
            lambda value: self.button.set_spin(float(value))
        )
        animation.finished.connect(lambda: self.button.set_spin(0.0))
        self._spin_animation = animation
        start_managed_animation(animation)
        if animation.duration() <= 0:
            self.button.set_spin(0.0)

    def _glow(self, target: float) -> None:
        """Вспышка кольца под нажатием и затухание после."""
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation

        from ui.animation_policy import start_managed_animation

        if self._glow_animation is not None:
            self._glow_animation.stop()

        current = float(getattr(self.button, "_net67_glow", 0.0))
        animation = QVariantAnimation(self)
        animation.setStartValue(current)
        animation.setEndValue(float(target))
        animation.setDuration(160 if target else 280)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(
            lambda value: self.button.set_glow(float(value))
        )
        self._glow_animation = animation
        start_managed_animation(animation)
        if animation.duration() <= 0:
            self.button.set_glow(float(target))

    def _set_hero_size(self, value) -> None:
        size = max(1, int(value))
        self._hero_size = size
        self.button.setFixedSize(size, size)
        self.uptime_label.setGeometry(0, 0, size, size)
        self._apply_button_colour(self._state, get_theme_tokens())

    def _sync_uptime_for_state(self, state: OneClickState) -> None:
        """Запускает и останавливает отсчёт вместе с обходом."""
        if state is OneClickState.RUNNING:
            if self._running_since is None:
                self._running_since = _time.monotonic()
            self._refresh_uptime()
            self.uptime_label.show()
            self.uptime_label.raise_()
            if not self._uptime_timer.isActive():
                self._uptime_timer.start()
            return

        self._running_since = None
        self._uptime_timer.stop()
        self.uptime_label.setText("")
        self.uptime_label.hide()

    def _apply_state(self, state: OneClickState, detail: str) -> None:
        tokens = get_theme_tokens()
        was_running = self._state is OneClickState.RUNNING
        self._state = state

        self.button.setText(_BUTTON_TEXT.get(state, "Включить обход"))
        self.button.setEnabled(state not in _BUSY)
        self.state_label.setText(_STATE_TEXT.get(state, ""))
        self.detail_label.setText(str(detail or ""))
        self.detail_label.setVisible(bool(detail))

        # Цвет самой кнопки зависит от состояния: выключено — приглушённая
        # поверхность, работает — акцент, ошибка — красный. Без этого
        # нажатие не читается вообще, а состояние приходится вычитывать
        # из подписи.
        self._apply_button_colour(state, tokens)
        self._sync_uptime_for_state(state)

        # Проворот на каждом переходе «работает — не работает»: именно
        # он сообщает, что нажатие сделало своё дело.
        if was_running != (state is OneClickState.RUNNING):
            try:
                self._spin()
            except Exception:
                pass

        color = {
            OneClickState.RUNNING: tokens.accent_hex,
            OneClickState.ERROR: tokens.fg_muted,
        }.get(state, tokens.fg)
        self.state_label.setStyleSheet(
            f"QLabel {{ color: {color}; font-weight: 600; font-size: 19px; }}"
        )
        # Значок меняется вместе с состоянием: круг с «пуском» при
        # выключенной защите и с «паузой» при работающей.
        _refresh_hero_icon(self.button, state)

        label = f"{_STATE_TEXT.get(state, '')}. {detail}".strip()
        set_state_text(self, label)
        set_control_accessibility(
            self.button,
            name=_BUTTON_TEXT.get(state, "Включить обход"),
            description=label,
        )
        self.stateChanged.emit(state)

    def _apply_button_colour(self, state: OneClickState, tokens) -> None:
        from shell.theme import palette

        try:
            colors = palette(not tokens.is_light)
        except Exception:
            return

        fill = {
            OneClickState.RUNNING: colors.accent,
            OneClickState.ERROR: "#c1121f",
        }.get(state, colors.surface_hover)
        ink = colors.on_accent if state is OneClickState.RUNNING else colors.text
        if state is OneClickState.ERROR:
            ink = "#ffffff"

        ring = colors.accent if state is OneClickState.RUNNING else colors.border_strong
        if state is OneClickState.ERROR:
            ring = "#ff6b6b"

        try:
            # Круг рисует себя сам, см. make_round_button_class. Таблица
            # стилей остаётся ради прозрачного текста: сам текст кнопки
            # читают программы экранного доступа, а показывать его внутри
            # круга нельзя — он туда не помещается.
            self.button.setStyleSheet(
                "QPushButton { border: none; background: transparent;"
                " color: transparent; padding: 0px; }"
            )
            self.button.set_hero_colors(fill=fill, ring=ring)
            self.uptime_label.setStyleSheet(
                f"QLabel#net67Uptime {{ color: {ink}; background: transparent;"
                " font-size: 19px; font-weight: 700; }"
            )
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────

    def _on_clicked(self) -> None:
        if self._state in _BUSY:
            return
        if self._worker is not None and self._worker.isRunning():
            return

        feature = None
        if callable(self._get_runtime_feature):
            try:
                feature = self._get_runtime_feature()
            except Exception as exc:
                log(f"Не удалось получить runtime для «одной кнопки»: {exc}", "❌ ERROR")

        if feature is None:
            self._apply_state(OneClickState.ERROR, "Подсистема запуска недоступна")
            return

        enable = self._state is not OneClickState.RUNNING
        self._apply_state(OneClickState.PREPARING, "")

        worker = _OneClickWorker(enable=enable, runtime_feature=feature, parent=self)
        worker.progress.connect(self._on_progress)
        worker.finished_with.connect(self._on_finished)
        # Какой именно поток завершился — обязательный параметр. Без него
        # опоздавший сигнал предыдущего потока удалял текущий, см.
        # _on_worker_done.
        worker.finished.connect(lambda finished=worker: self._on_worker_done(finished))
        self._worker = worker
        worker.start()

    def _on_progress(self, state, message: str) -> None:
        # Промежуточные состояния показываем, но кнопку не разблокируем.
        if state in _BUSY:
            self._apply_state(state, str(message or ""))

    def _on_finished(self, state, message: str) -> None:
        self._apply_state(state, str(message or ""))

    def _on_worker_done(self, worker) -> None:
        """Убирает завершившийся поток, не трогая текущий.

        Раньше метод брал self._worker вслепую: «завершился какой-то —
        значит, чистим то, что лежит в поле». Между кликами это разные
        объекты. Последовательность «Включить, Выключить, Включить» давала
        такую картину: поток выключения завершался уже после того, как
        стартовал третий поток, и его finished удалял ЭТОТ, работающий,
        поток. Дальше — Qt-фатал «QThread: Destroyed while thread is still
        running» в crashes.log, ни одного finished_with и кнопка,
        навсегда оставшаяся неактивной.
        """
        if self._worker is worker:
            self._worker = None
            # Поток умер, не сообщив результата: разблокируем кнопку сами,
            # иначе человеку останется только перезапустить программу.
            if self._state in _BUSY:
                log("Поток «одной кнопки» завершился без результата", "⚠ WARNING")
                self._apply_state(OneClickState.ERROR, "Операция прервана, попробуйте ещё раз")
        if worker is not None:
            worker.deleteLater()

    def stop_worker(self) -> None:
        """Аккуратно гасит поток при закрытии страницы."""
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        try:
            if worker.isRunning():
                worker.quit()
                worker.wait(3000)
        except Exception:
            pass


__all__ = ["OneClickButton"]
