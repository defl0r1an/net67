# oneclick/ui/button.py
"""Главная кнопка «Включить» с состояниями.

Оркестратор делает блокирующие вызовы — проверку целостности DNS и опрос
доменов по сети. Выполнять их в UI-потоке нельзя: окно замёрзнет на
десятки секунд. Поэтому вся работа уходит в QThread, а интерфейс
обновляется по сигналам.

Вид — карточка, как у zapret (просьба владельца, 26 октября 2026): слева
сцена обхода (ui/widgets/bypass_scene.py) — логотип, стена блокировки с
кнопкой питания и сайты; справа крупная строка состояния, время работы и
пояснение. Раньше здесь был одинокий круг по центру: что именно он
включает и почему сайты не открываются, из него видно не было, а сцена
показывает это сама — пакеты бьются о стену или проходят сквозь неё.
"""

from __future__ import annotations

import time as _time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QBoxLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel

from log.log import log
from oneclick.autostart import initial_button_state
from oneclick.state import OneClickState
from oneclick.ui.oneclick_worker import _OneClickWorker
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

#: Цвета кнопки в стене по состоянию — те же, что у zapret: работает —
#: зелёный, запуск и остановка — янтарный, выключено и сбой — красный.
#: Красная стена при выключенном обходе — и есть блокировка: так её и видно.
SCENE_COLOR_RUNNING = "#6ccb5f"
SCENE_COLOR_BUSY = "#f5a623"
SCENE_COLOR_STOPPED = "#ff6b6b"


def scene_look(state: OneClickState, *, stopping: bool = False) -> tuple[str, str]:
    """(фаза сцены, цвет кнопки) для состояния «одной кнопки»."""
    if state is OneClickState.RUNNING:
        return "running", SCENE_COLOR_RUNNING
    if state in (OneClickState.PREPARING, OneClickState.CHECKING):
        return ("stopping" if stopping else "starting"), SCENE_COLOR_BUSY
    if state is OneClickState.ERROR:
        return "failed", SCENE_COLOR_STOPPED
    return "stopped", SCENE_COLOR_STOPPED


#: Через сколько после появления кнопки сверяемся с состоянием обхода.
#:
#: Не сразу: конструктор кнопки выполняется во время сборки страницы, и
#: обращаться к рантайму оттуда рано. Небольшая задержка даёт автозапуску
#: обхода уже подняться, чтобы кнопка сразу показала правильное «Обход
#: включён», а не «выключен».
AUTOSTART_DELAY_MS = 900

#: В этих состояниях кнопка занята и нажатие игнорируется.
_BUSY = (OneClickState.PREPARING, OneClickState.CHECKING)


class OneClickButton(QWidget):
    """Крупная кнопка запуска с понятным состоянием под ней."""

    stateChanged = pyqtSignal(object)

    def __init__(self, parent=None, *, get_runtime_feature=None, get_runtime_phase=None):
        super().__init__(parent)
        self._get_runtime_feature = get_runtime_feature
        # Живая фаза обхода из общего состояния, см. _catch_up_with_runtime.
        self._get_runtime_phase = get_runtime_phase
        self._runtime_phase = ""
        self._state = OneClickState.OFF
        self._stopping = False
        self._worker: _OneClickWorker | None = None
        from ui.one_shot_worker_runtime import OneShotWorkerRuntime
        self._availability_runtime = OneShotWorkerRuntime()
        self._closed = False

        # Карточка: сцена слева, справа состояние, время работы и пояснение.
        # В узком окне StatusHeroCard сама ставит сцену строкой над текстом.
        from presets.ui.control.status_hero_card import StatusHeroCard
        from oneclick.ui.uptime_pill import UptimePill
        from ui.widgets.bypass_scene import BypassScene

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 4)
        outer.setSpacing(0)

        self.card = StatusHeroCard(self)
        outer.addWidget(self.card)
        row = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.card)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(18)

        # Кнопка питания живёт в стене сцены. Имя ``button`` осталось от
        # круга: по нему тур подсвечивает главную кнопку, а метка в заголовке
        # узнаёт, ушла ли кнопка за край страницы (shell/launch_badge_handoff.py).
        self.button = BypassScene(self.card)
        self.button.set_clickable(True)
        self.button.clicked.connect(self._on_clicked)
        row.addWidget(self.button, 0, Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        self.state_label = BodyLabel(_STATE_TEXT[OneClickState.OFF])
        title_row.addWidget(self.state_label)
        # Сколько защита уже работает. Отсчёт идёт от момента входа в
        # состояние RUNNING, а не от запуска программы: человека
        # интересует именно время работы обхода.
        self.uptime_label = UptimePill(self.card)
        title_row.addWidget(self.uptime_label, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        text.addLayout(title_row)

        # Пояснение переносится по словам: сообщения бывают длинными —
        # «Сейчас откроется Telegram и предложит включить прокси net67 —
        # подтвердите в его окне».
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        text.addWidget(self.detail_label)
        row.addLayout(text, 1)

        self.card.set_stacking_layout(row)
        self.card.bind_scene(self.button)

        self._running_since: float | None = None
        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(1000)
        self._uptime_timer.timeout.connect(self._refresh_uptime)

        self._apply_theme()
        self._apply_state(OneClickState.OFF, "")

        # Сверка с реальным состоянием обхода. Автозапуск включает обход
        # ещё до появления кнопки, и без этой сверки под кругом висело бы
        # «Обход выключен», хотя он работает.
        QTimer.singleShot(AUTOSTART_DELAY_MS, self._sync_initial_state)

    # ──────────────────────────────────────────────────────────────────

    def _probe_bypass_running(self) -> bool | None:
        """Спрашивает движок напрямую: работает ли обход. None — спросить нечем.

        Это самый достоверный источник: не состояние из хранилища, которое
        может отставать или быть ещё не привязанным, а сам рантайм.
        """
        getter = self.__dict__.get("_get_runtime_feature")
        if not callable(getter):
            return None
        try:
            feature = getter()
        except Exception as exc:
            log(f"Кнопка обхода: подсистема недоступна: {exc}", "DEBUG")
            return None
        if feature is None:
            return None
        try:
            return bool(feature.is_any_running(silent=True))
        except TypeError:
            try:
                return bool(feature.is_any_running())
            except Exception:
                return None
        except Exception:
            return None

    def _sync_initial_state(self) -> None:
        """Показывает «Обход включён», если он уже работает.

        Не запускает ничего сама: обход на старте поднимает координатор
        (в том числе в свёрнутом окне). Кнопка лишь отражает факт.
        """
        if self._state in _BUSY or self._state is OneClickState.RUNNING:
            return

        running = bool(self._probe_bypass_running())
        if initial_button_state(bypass_running=running) is OneClickState.RUNNING:
            self._apply_state(OneClickState.RUNNING, "")

    def follow_runtime_phase(self, phase: str) -> None:
        """Отражает обход, включённый или выключенный не этой кнопкой.

        Кнопка смотрела на обход один раз — при сборке страницы. Автозапуск
        поднимал обход секундой позже, и кнопка так и стояла на «Обход
        выключен», пока метка в заголовке писала «Работает»: человек
        видел два противоречащих ответа на одном экране. Так же она не
        замечала выключение из метки или из трея.

        Пока идёт собственная цепочка шагов кнопки (подготовка,
        проверка) — не вмешиваемся: её итог она покажет сама.
        """
        normalized = str(phase or "").strip().lower()
        # Запоминаем и тогда, когда вмешиваться рано: к этой фазе кнопка
        # вернётся, когда закончит свои шаги.
        self._runtime_phase = normalized
        if self._state in _BUSY:
            return
        worker = self._worker
        if worker is not None and worker.isRunning():
            return
        if normalized == "running" and self._state is not OneClickState.RUNNING:
            self._apply_state(OneClickState.RUNNING, "")
        elif normalized == "stopped" and self._state is OneClickState.RUNNING:
            self._apply_state(OneClickState.OFF, "")

    def _catch_up_with_runtime(self) -> None:
        """Сверяет кнопку с обходом, когда её собственные шаги закончились.

        Пока кнопка занята, перемены обхода она пропускает — и после
        этого её никто не догонял. Выключили кругом, обход тут же подняли
        заново (перезапуск после первичной настройки) — шаги кнопки
        кончились позже, она написала «Обход выключен», а метка в
        заголовке — «Работает». Так и стояло, пока обход не трогали:
        новой перемены, которая поправила бы кнопку, не приходило.

        Фаза читается из общего состояния в эту секунду, а не из
        последней доставленной: доставка подписчикам идёт через очередь
        и может отставать от самого состояния.
        """
        phase = self.__dict__.get("_runtime_phase", "")
        getter = self.__dict__.get("_get_runtime_phase")
        if callable(getter):
            try:
                phase = str(getter() or "")
            except Exception as exc:
                log(f"Кнопка обхода: фаза обхода недоступна: {exc}", "DEBUG")
        # Состояние из хранилища бывает ненадёжным: при показе страницы оно
        # ещё не привязано (пусто), а обход, запущенный через плашку в
        # заголовке до первого показа главной, оставлял круг на «выключен».
        # Поэтому, когда хранилище не говорит «работает», спрашиваем сам
        # движок — он знает точно.
        if phase not in ("running", "starting", "stopping") and self._state not in _BUSY:
            running = self._probe_bypass_running()
            if running is True:
                phase = "running"
            elif running is False and not phase:
                phase = "stopped"
        if phase:
            self.follow_runtime_phase(phase)

    def showEvent(self, event):  # noqa: N802 — имя от Qt
        super().showEvent(event)
        # Страница могла быть спрятана, пока обход включали и выключали
        # из заголовка или трея.
        QTimer.singleShot(0, self._catch_up_with_runtime)

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
        """Время работы словами часов, минут и секунд."""
        from ui.launch_uptime import format_uptime

        return format_uptime(seconds)

    def _refresh_uptime(self) -> None:
        if self._running_since is None:
            self.uptime_label.setText("")
            return
        self.uptime_label.setText(self.format_uptime(_time.monotonic() - self._running_since))

    def _sync_uptime_for_state(self, state: OneClickState) -> None:
        """Запускает и останавливает отсчёт вместе с обходом."""
        if state is OneClickState.RUNNING:
            if self._running_since is None:
                # Общие часы обхода, если они уже идут: метка в заголовке
                # пишет то же время, и расходиться им нельзя
                # (ui/launch_uptime.py).
                from ui.launch_uptime import since as shared_since

                self._running_since = shared_since() or _time.monotonic()
            self._refresh_uptime()
            self.uptime_label.show()
            if not self._uptime_timer.isActive():
                self._uptime_timer.start()
            return

        self._running_since = None
        self._uptime_timer.stop()
        self.uptime_label.setText("")
        self.uptime_label.hide()

    def _apply_state(self, state: OneClickState, detail: str) -> None:
        tokens = get_theme_tokens()
        self._state = state

        if state not in _BUSY:
            self._stopping = False

        button_text = "Остановка..." if self._stopping and state is OneClickState.PREPARING else _BUTTON_TEXT.get(state, "Включить обход")
        state_text = "Останавливаем..." if self._stopping and state is OneClickState.PREPARING else _STATE_TEXT.get(state, "")

        self.button.set_click_enabled(state not in _BUSY)
        self.state_label.setText(state_text)
        self.detail_label.setText(str(detail or ""))
        self.detail_label.setVisible(bool(detail))

        # Сцена показывает состояние сама: пакеты бьются о красную стену,
        # трещит дуга запуска или ворота открыты и поток идёт к сайтам.
        phase, color = scene_look(state, stopping=self._stopping)
        self.button.set_color(color)
        self.button.set_phase(phase)
        self._sync_uptime_for_state(state)

        title_color = {
            OneClickState.RUNNING: SCENE_COLOR_RUNNING,
            OneClickState.ERROR: SCENE_COLOR_STOPPED,
        }.get(state, tokens.fg)
        self.state_label.setStyleSheet(
            f"QLabel {{ color: {title_color}; font-weight: 600; font-size: 19px; }}"
        )

        label = f"{state_text}. {detail}".strip()
        set_state_text(self, label)
        set_control_accessibility(
            self.button,
            name=button_text,
            description=label,
        )
        self.stateChanged.emit(state)

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

        self._cancel_availability()
        enable = self._state is not OneClickState.RUNNING
        self._start_worker(enable=enable, feature=feature)

    def _start_worker(self, *, enable: bool, feature) -> None:
        """Запускает включение или выключение в отдельном потоке.

        Общий путь для нажатия и для автозапуска: разными они были ровно
        до тех пор, пока автозапуск не начал делать не то же самое.
        """
        if feature is None:
            self._apply_state(OneClickState.ERROR, "Подсистема запуска недоступна")
            return
        if self._worker is not None and self._worker.isRunning():
            return

        self._stopping = not bool(enable)
        self._apply_state(OneClickState.PREPARING, "")

        worker = _OneClickWorker(enable=bool(enable), runtime_feature=feature, parent=self)
        worker.progress.connect(self._on_progress)
        worker.finished_with.connect(self._on_finished)
        # Какой именно поток завершился — обязательный параметр. Без него
        # опоздавший сигнал предыдущего потока удалял текущий, см.
        # _on_worker_done.
        worker.finished.connect(lambda finished=worker: self._on_worker_done(finished))
        self._worker = worker
        worker.start()

    def _on_progress(self, state, message: str) -> None:
        if state in _BUSY or state is OneClickState.RUNNING:
            self._apply_state(state, str(message or ""))
            # Настройки ещё применяются: две изменяющие систему команды
            # одновременно запускать нельзя. Проверка сайтов сюда не входит.
            self.button.set_click_enabled(False)

    def _on_finished(self, state, message: str) -> None:
        self._apply_state(state, str(message or ""))
        worker = self._worker
        if state is OneClickState.RUNNING and bool(getattr(worker, 'needs_selfcheck', False)):
            self._start_availability()

    def _start_availability(self) -> None:
        from oneclick.ui.oneclick_worker import AvailabilityWorker
        self._cancel_availability()
        self._availability_runtime.start_qthread_worker(
            worker_factory=AvailabilityWorker,
            on_loaded=self._on_availability,
        )
        self._apply_state(OneClickState.RUNNING, "Идёт проверка доступности")

    def _on_availability(self, request_id: int, message: str) -> None:
        if self._availability_runtime.is_current(request_id, cleanup_in_progress=self._closed) and self._state is OneClickState.RUNNING:
            self._apply_state(OneClickState.RUNNING, message)

    def _cancel_availability(self) -> None:
        runtime = self.__dict__.get('_availability_runtime')
        if runtime is not None:
            runtime.stop(blocking=False)
            runtime.cancel()

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
            else:
                self._catch_up_with_runtime()
        if worker is not None:
            worker.deleteLater()

    def stop_worker(self) -> None:
        """Аккуратно гасит поток при закрытии страницы."""
        self._closed = True
        self._cancel_availability()
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
